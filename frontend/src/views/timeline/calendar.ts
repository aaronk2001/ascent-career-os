import { api } from "../../api";
import { $, $$, esc } from "../../ui";
import { type Board, type Item, type Lane, LANE_META } from "./data";

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const isAnchor = (i: Item) => i.lane === "milestones" && (i.meta as { anchor?: boolean }).anchor;
const rank = (i: Item) => (isAnchor(i) ? 0 : i.lane === "learning" ? 1 : 2);
const isEditableEvent = (i: Item) => i.source === "timeline" && (i.meta as { kind?: string }).kind === "event";

/** Month-calendar mode. Consumes the shared board; reload() refetches after edits. */
export function mountCalendar(host: HTMLElement, board: Board, hidden: Set<Lane>, reload: () => Promise<void>) {
  const today = new Date();
  let view = { y: today.getFullYear(), m: today.getMonth() };
  let selected: string | null = iso(today);
  let form: { id: string | null; label: string } | null = null;

  const visible = () => board.items.filter((i) => !hidden.has(i.lane));

  function byDate(): Map<string, Item[]> {
    const map = new Map<string, Item[]>();
    for (const i of visible()) (map.get(i.date) ?? map.set(i.date, []).get(i.date)!).push(i);
    return map;
  }

  function draw() {
    const map = byDate();
    const todayIso = iso(today);
    const first = new Date(view.y, view.m, 1);
    const startDow = (first.getDay() + 6) % 7;
    const daysInMonth = new Date(view.y, view.m + 1, 0).getDate();

    let cells = "";
    for (let i = 0; i < 42; i++) {
      const dayNum = i - startDow + 1;
      const inMonth = dayNum >= 1 && dayNum <= daysInMonth;
      const d = new Date(view.y, view.m, dayNum);
      const dIso = iso(d);
      const evs = (map.get(dIso) ?? []).slice().sort((a, b) => rank(a) - rank(b));
      const isSel = dIso === selected;
      const isToday = dIso === todayIso;
      const chips = evs.slice(0, 3).map((e) => {
        const anc = isAnchor(e);
        const text = anc ? "text-goal font-semibold" : e.done ? "text-fg-faint line-through" : "text-fg-muted";
        return `<div class="flex items-center gap-1 text-[10px] leading-tight" title="${esc(e.label)}"><span class="h-1.5 w-1.5 rounded-full ${LANE_META[e.lane].dot} shrink-0"></span><span class="truncate ${text}">${anc ? "★ " : ""}${esc(e.label)}</span></div>`;
      }).join("");
      const more = evs.length > 3 ? `<div class="text-[9px] text-fg-faint">+${evs.length - 3}</div>` : "";
      cells += `<button data-day="${dIso}" class="relative text-left rounded-xl p-2 min-h-[88px] border transition-colors ${inMonth ? "border-line bg-ink-900/40 hover:border-line-strong" : "border-transparent opacity-30"} ${isSel ? "!border-[color-mix(in_oklab,var(--accent)_60%,transparent)]" : ""}">
        ${isToday
          ? `<div class="relative inline-grid"><span class="absolute inset-0 rounded-full accent-bg opacity-60 animate-ping"></span><div class="relative grid place-items-center h-5 w-5 rounded-full accent-bg text-white text-xs font-semibold">${d.getDate()}</div></div>`
          : `<div class="text-xs text-fg-faint">${d.getDate()}</div>`}
        <div class="mt-1 space-y-0.5 overflow-hidden">${chips}${more}</div></button>`;
    }

    host.innerHTML = `
      <div class="flex items-center gap-2 mb-3">
        <h2 class="text-lg font-semibold tracking-tight">${MONTHS[view.m]} ${view.y}</h2>
        <button id="prev" class="rounded-lg bg-ink-800 hover:bg-ink-700 h-7 w-7 grid place-items-center text-fg-muted">‹</button>
        <button id="next" class="rounded-lg bg-ink-800 hover:bg-ink-700 h-7 w-7 grid place-items-center text-fg-muted">›</button>
        <button id="today" class="rounded-lg bg-ink-800 hover:bg-ink-700 px-2.5 py-1 text-xs text-fg-muted">Today</button>
      </div>
      <div class="card p-3">
        <div class="grid grid-cols-7 gap-1.5 mb-1.5">${DOW.map((d) => `<div class="text-center text-[10px] uppercase tracking-wide text-fg-faint">${d}</div>`).join("")}</div>
        <div class="grid grid-cols-7 gap-1.5">${cells}</div>
      </div>
      <div id="day-detail" class="mt-4"></div>`;

    $(host, "#prev")?.addEventListener("click", () => { view = step(-1); draw(); });
    $(host, "#next")?.addEventListener("click", () => { view = step(1); draw(); });
    $(host, "#today")?.addEventListener("click", () => { view = { y: today.getFullYear(), m: today.getMonth() }; selected = iso(today); draw(); });
    $$(host, "[data-day]").forEach((b) => b.addEventListener("click", () => { selected = b.dataset.day!; form = null; draw(); }));
    drawDay();
  }

  function step(delta: number) {
    const d = new Date(view.y, view.m + delta, 1);
    return { y: d.getFullYear(), m: d.getMonth() };
  }

  function drawDay() {
    const detail = $(host, "#day-detail");
    if (!detail || !selected) return;
    const evs = visible().filter((e) => e.date === selected).sort((a, b) => rank(a) - rank(b));
    const rows = evs.map((e) => {
      const editable = isEditableEvent(e);
      const anc = isAnchor(e);
      return `<div class="group flex items-center gap-2 py-1.5 text-sm">
        <span class="h-2 w-2 rounded-full ${LANE_META[e.lane].dot} shrink-0"></span>
        <span class="flex-1 ${anc ? "text-goal font-semibold" : e.done ? "text-fg-muted line-through" : ""}">${anc ? "★ " : ""}${esc(e.label)}</span>
        ${editable ? `<span class="opacity-0 group-hover:opacity-100 flex gap-2"><button data-edit data-id="${esc(e.source_id)}" data-label="${esc(e.label)}" class="text-fg-faint hover:text-fg text-xs">edit</button><button data-del data-id="${esc(e.source_id)}" class="text-fg-faint hover:text-danger text-xs">✕</button></span>` : `<span class="text-[10px] text-fg-faint">${e.lane}</span>`}</div>`;
    }).join("");
    const formHtml = form ? `<div class="mt-3 flex flex-wrap gap-2">
        <input id="f-label" placeholder="What's happening?" value="${esc(form.label)}" class="flex-1 min-w-48 bg-ink-800 rounded-lg px-3 py-2 text-sm" />
        <button id="f-save" class="btn-accent rounded-lg px-3 py-1.5 text-sm">Save</button>
        <button id="f-cancel" class="rounded-lg bg-ink-800 hover:bg-ink-700 px-3 py-1.5 text-sm">Cancel</button></div>` : "";

    detail.innerHTML = `<div class="card p-4">
      <div class="flex items-center justify-between mb-2">
        <div class="text-sm font-medium">${new Date(selected + "T00:00:00").toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" })}</div>
        <button id="day-add" class="btn-accent rounded-lg px-2.5 py-1 text-xs">+ Add event</button>
      </div>
      ${rows || '<div class="text-sm text-fg-faint">Nothing on this day.</div>'}
      ${formHtml}</div>`;

    $(detail, "#day-add")?.addEventListener("click", () => { form = { id: null, label: "" }; drawDay(); });
    $(detail, "#f-cancel")?.addEventListener("click", () => { form = null; drawDay(); });
    $(detail, "#f-save")?.addEventListener("click", async () => {
      const label = ($(detail, "#f-label") as HTMLInputElement).value.trim();
      if (!label) return;
      const id = form?.id;
      form = null;
      if (id) await api(`/timeline/${id}`, { method: "PUT", body: JSON.stringify({ label }) }).catch(() => {});
      else await api("/timeline", { method: "POST", body: JSON.stringify({ date: selected, label, kind: "event" }) }).catch(() => {});
      await reload();
    });
    $$(detail, "[data-edit]").forEach((b) => b.addEventListener("click", () => { form = { id: b.dataset.id!, label: b.dataset.label! }; drawDay(); }));
    $$(detail, "[data-del]").forEach((b) => b.addEventListener("click", async () => { await api(`/timeline/${b.dataset.id}`, { method: "DELETE" }).catch(() => {}); await reload(); }));
  }

  draw();
}
