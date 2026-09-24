import { api, tryApi } from "../api";
import type { View } from "../router";
import { $, $$, esc, progressBar } from "../ui";
import { ring, mountRings } from "../visuals";

type Block = {
  id: string; date: string; start: string; end: string; cat: string;
  title: string | null; detail: string | null; deep_link: string | null;
  status: "planned" | "done" | "skipped"; actual_min: number; pos: number;
};
type Cat = { label: string; color: string };
type Day = {
  date: string; template: string; blocks: Block[]; cats: Record<string, Cat>;
  wake: string; hard_stop: string; planned_min: number; actual_min: number; done: number;
};
type CatTotals = { planned: number; actual: number; done: number; blocks: number };
type Week = { start: string; end: string; days: Record<string, Record<string, CatTotals>>; totals: Record<string, CatTotals> };
type Anchors = {
  offer_date: string | null; stretch_date: string | null; runway_end: string | null; bridge_gate: string | null;
  bridge_mode: boolean; runway_days: number | null; offer_days: number | null; next_exam: string | null; next_exam_title: string | null;
};

const EMPTY_ANCHORS: Anchors = {
  offer_date: null, stretch_date: null, runway_end: null, bridge_gate: null, bridge_mode: false,
  runway_days: null, offer_days: null, next_exam: null, next_exam_title: null,
};
const CHECK = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"><path d="M5 13l4 4L19 7"/></svg>';

export default function today(): View {
  let iso = localIso(new Date());
  let day: Day | undefined;
  let week: Week | undefined;
  let anchors: Anchors = EMPTY_ANCHORS;
  let tick: number | undefined;
  let rootEl: HTMLElement | null = null;
  let adding = false;

  return {
    cleanup() {
      if (tick) clearInterval(tick);
      tick = undefined;
    },
    async render(root) {
      rootEl = root;
      root.innerHTML = `<div class="p-2 text-fg-muted">Loading today…</div>`;
      await load();
      draw();
    },
  };

  async function load() {
    [day, week, anchors] = await Promise.all([
      api<Day>(`/day?date=${iso}`),
      api<Week>(`/day/week?start=${weekStart(iso)}`).catch(() => undefined),
      api<Anchors>("/anchors").catch(() => EMPTY_ANCHORS),
    ]);
  }

  function draw() {
    if (!rootEl || !day) return;
    const d = day;
    const blocks = [...d.blocks].sort((a, b) => (a.start < b.start ? -1 : a.start > b.start ? 1 : a.pos - b.pos));
    const isToday = iso === localIso(new Date());
    const work = blocks.filter((b) => b.cat !== "break");
    const doneMin = work.filter((b) => b.status === "done").reduce((a, b) => a + mins(b.start, b.end), 0);
    const pct = d.planned_min ? Math.min(100, (doneMin / d.planned_min) * 100) : 0;

    const chip = (label: string, n: number | null, tone = "text-goal") =>
      n == null ? "" : `<span class="rounded-full glass px-2.5 py-1 text-xs ${n < 0 ? "text-fg-faint" : tone} font-medium nums">${esc(label)} ${n < 0 ? "✓" : `${n} d`}</span>`;
    const chips = [
      chip("Offer", anchors.offer_days),
      chip("Stretch", days(anchors.stretch_date), "text-fg"),
      chip("Runway", anchors.runway_days, (anchors.runway_days ?? 99) <= 21 ? "text-warn" : "text-fg"),
      chip("Bridge gate", days(anchors.bridge_gate), "text-fg"),
      anchors.bridge_mode ? `<span class="rounded-full border border-warn/50 text-warn px-2.5 py-1 text-xs">Bridge mode</span>` : "",
    ].join("");

    const blockCard = (b: Block, n: number) => {
      const c = d.cats[b.cat] ?? { label: b.cat, color: "var(--accent)" };
      const isBreak = b.cat === "break";
      const done = b.status === "done";
      const skipped = b.status === "skipped";
      const len = mins(b.start, b.end);
      const link = b.deep_link
        ? `<a href="${esc(b.deep_link)}" ${b.deep_link.startsWith("http") ? 'target="_blank" rel="noopener"' : ""} class="shrink-0 rounded-lg btn-accent px-2.5 py-1 text-[11px]">Go →</a>`
        : "";
      const state = done ? "opacity-60" : skipped ? "opacity-40" : "";
      return `<div data-block="${esc(b.id)}" class="card border-line ${state} flex gap-3 p-3 relative overflow-hidden ${isBreak ? "py-2" : ""}">
        <div class="absolute left-0 top-0 bottom-0 w-1" style="background:${esc(c.color)}"></div>
        <div class="w-[46px] shrink-0 pl-2 pt-0.5">
          <div class="text-sm font-medium nums ${done ? "text-fg-faint" : "text-fg-muted"}">${isBreak ? "·" : n}</div>
          <div class="text-[11px] text-fg-faint nums">${len}m</div>
        </div>
        <div class="min-w-0 flex-1">
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0">
              <div class="flex items-center gap-2 flex-wrap">
                <span class="rounded-full border border-line px-2 py-0.5 text-[10px] text-fg-faint">${esc(c.label)}</span>
                <span class="text-sm font-medium ${done ? "line-through text-fg-muted" : ""}">${esc(b.title ?? c.label)}</span>
              </div>
              ${b.detail ? `<p class="mt-1 text-xs text-fg-muted">${esc(b.detail)}</p>` : ""}
            </div>
            ${link}
          </div>
          ${isBreak ? "" : `<div class="mt-2.5 flex items-center gap-1.5 flex-wrap">
            <button data-act="done" class="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[11px] ${done ? "accent-bg text-white" : "border border-line text-fg-muted hover:text-fg"}">${CHECK}<span>${done ? "Done" : "Mark done"}</span></button>
            <button data-act="skip" class="rounded-lg border border-line px-2 py-1 text-[11px] ${skipped ? "text-warn border-warn/50" : "text-fg-muted hover:text-fg"}">${skipped ? "Skipped" : "Skip"}</button>
            <span class="mx-1 h-4 w-px bg-line"></span>
            <span class="text-[11px] text-fg-faint">actual</span>
            <button data-act="actual" data-min="-15" class="rounded-lg border border-line px-1.5 py-1 text-[11px] text-fg-muted hover:text-fg nums">−</button>
            <span class="text-[11px] nums text-fg min-w-[34px] text-center">${b.actual_min || 0}m</span>
            <button data-act="actual" data-min="15" class="rounded-lg border border-line px-1.5 py-1 text-[11px] text-fg-muted hover:text-fg nums">+</button>
            <button data-act="actual" data-min="${len}" data-set="1" class="rounded-lg border border-line px-2 py-1 text-[11px] text-fg-muted hover:text-fg" title="Log the full planned length">= planned</button>
            <button data-act="del" class="ml-auto rounded-lg px-2 py-1 text-[11px] text-fg-faint hover:text-danger" title="Remove block">×</button>
          </div>`}
        </div>
      </div>`;
    };

    const targets = work.filter((b) => ["apps", "controls", "ml", "clips", "portfolio", "outreach"].includes(b.cat));
    const seen = new Set<string>();
    const targetRows = targets.filter((b) => (seen.has(b.cat) ? false : (seen.add(b.cat), true))).map((b) => {
      const c = d.cats[b.cat] ?? { label: b.cat, color: "var(--accent)" };
      return `<div class="flex items-start gap-2 py-1.5">
        <span class="mt-1.5 h-2 w-2 rounded-full shrink-0" style="background:${esc(c.color)}"></span>
        <div class="min-w-0"><div class="text-xs font-medium">${esc(b.title ?? c.label)}</div>${b.detail ? `<div class="text-[11px] text-fg-faint line-clamp-2">${esc(b.detail)}</div>` : ""}</div>
      </div>`;
    }).join("") || `<div class="text-xs text-fg-faint">No work blocks today.</div>`;

    const weekRows = week ? Object.entries(week.totals)
      .sort((a, b) => b[1].planned - a[1].planned)
      .map(([cat, t]) => {
        const c = d.cats[cat] ?? { label: cat, color: "var(--accent)" };
        const p = t.planned ? Math.min(100, (t.actual / t.planned) * 100) : 0;
        return `<div class="py-1">
          <div class="flex items-center justify-between text-[11px]"><span class="text-fg-muted">${esc(c.label)}</span><span class="nums text-fg-faint">${(t.actual / 60).toFixed(1)}h / ${(t.planned / 60).toFixed(1)}h</span></div>
          <div class="mt-1">${progressBar(p, "")}</div>
        </div>`.replace('class="bar-fill h-full "', `class="bar-fill h-full" style="background:${esc(c.color)};width:${Math.round(p)}%"`);
      }).join("") : "";
    const weekPlanned = week ? Object.values(week.totals).reduce((a, t) => a + t.planned, 0) : 0;
    const weekActual = week ? Object.values(week.totals).reduce((a, t) => a + t.actual, 0) : 0;

    const addForm = adding ? `<div class="card p-3 flex flex-wrap items-end gap-2">
        <label class="flex flex-col gap-1 text-[11px] text-fg-muted">Minutes<input id="td-add-min" type="number" min="5" step="5" value="60" class="w-20 bg-ink-800 rounded-lg px-2 py-1.5 text-sm"/></label>
        <label class="flex flex-col gap-1 text-[11px] text-fg-muted">Category<select id="td-add-cat" class="bg-ink-800 rounded-lg px-2 py-1.5 text-sm">${Object.entries(d.cats).map(([k, c]) => `<option value="${esc(k)}">${esc(c.label)}</option>`).join("")}</select></label>
        <label class="flex flex-col gap-1 text-[11px] text-fg-muted flex-1 min-w-[180px]">Title<input id="td-add-title" placeholder="e.g. Phone screen — Acme Robotics" class="bg-ink-800 rounded-lg px-2 py-1.5 text-sm"/></label>
        <button id="td-add-save" class="rounded-lg btn-accent px-3 py-1.5 text-sm">Add</button>
        <button id="td-add-cancel" class="rounded-lg border border-line px-3 py-1.5 text-sm text-fg-muted">Cancel</button>
      </div>` : "";

    rootEl.innerHTML = `
      <div class="space-y-4 pb-6">
        <div class="flex flex-wrap items-center justify-between gap-3 px-2">
          <div class="flex items-center gap-3">
            <h1 class="text-2xl font-semibold tracking-tight">Today</h1>
            <div class="flex rounded-lg overflow-hidden border border-line">
              <button id="td-prev" class="px-2.5 py-1 text-xs text-fg-muted hover:text-fg">◀</button>
              <button id="td-today" class="px-2.5 py-1 text-xs ${isToday ? "accent-bg text-white" : "text-fg-muted hover:text-fg"}">${esc(fmtDate(iso))}</button>
              <button id="td-next" class="px-2.5 py-1 text-xs text-fg-muted hover:text-fg">▶</button>
            </div>
            <span class="text-[11px] text-fg-faint">${esc(d.template.replace("_", " "))} template · goals in order, no fixed times</span>
          </div>
          <div class="flex flex-wrap items-center gap-2">${chips}</div>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-[1fr_300px] gap-4">
          <div class="space-y-2">
            <div class="flex items-center justify-between px-1">
              <div class="text-xs text-fg-faint">${blocks.length ? `${d.done} of ${work.length} goals done · ${(doneMin / 60).toFixed(1)} of ${(d.planned_min / 60).toFixed(1)} h` : "No goals — rest day or template empty."}</div>
              <div class="flex items-center gap-2">
                <button id="td-add" class="rounded-lg border border-line px-3 py-1.5 text-xs text-fg-muted hover:text-fg hover:border-line-strong">+ Goal</button>
                <button id="td-regen" class="rounded-lg border border-line px-3 py-1.5 text-xs text-fg-muted hover:text-fg hover:border-line-strong" title="Rebuild from the template with fresh data; done blocks are kept">Regenerate</button>
              </div>
            </div>
            ${addForm}
            <div id="td-list" class="space-y-2">${numbered(blocks)}</div>
            <div id="td-msg" class="px-1 text-xs text-fg-faint"></div>
          </div>

          <div class="space-y-3">
            <div class="card p-4 flex items-center gap-4">
              ${ring(pct, { size: 64, stroke: 6, color: "var(--color-goal)", label: `${Math.round(pct)}%` })}
              <div>
                <div class="text-xs text-fg-faint">Day progress</div>
                <div class="text-lg font-semibold nums">${(doneMin / 60).toFixed(1)}<span class="text-sm text-fg-muted"> / ${(d.planned_min / 60).toFixed(1)} h</span></div>
                <div class="text-[11px] text-fg-faint nums">${d.actual_min} min logged · ${d.done} done</div>
              </div>
            </div>
            <div class="card p-4">
              <div class="text-sm font-medium mb-1">Targets today</div>
              ${targetRows}
            </div>
            <div class="card p-4">
              <div class="flex items-center justify-between mb-1">
                <div class="text-sm font-medium">This week</div>
                <div class="text-[11px] text-fg-faint nums">${(weekActual / 60).toFixed(1)} / ${(weekPlanned / 60).toFixed(1)} h</div>
              </div>
              ${weekRows || `<div class="text-xs text-fg-faint">No blocks generated this week yet.</div>`}
            </div>
            <div class="card p-4 text-xs text-fg-muted space-y-1">
              <div>Goals run in order, not on a clock — take them when you have the energy.</div>
              <div>Sunday is off. Durations still drive the weekly hour budget.</div>
            </div>
          </div>
        </div>
      </div>`;

    mountRings(rootEl);
    wire();

    function numbered(list: Block[]): string {
      let n = 0;
      return list.map((b) => blockCard(b, b.cat === "break" ? 0 : ++n)).join("");
    }
  }

  function wire() {
    if (!rootEl) return;
    const root = rootEl;
    $(root, "#td-prev")?.addEventListener("click", () => go(shiftDay(iso, -1)));
    $(root, "#td-next")?.addEventListener("click", () => go(shiftDay(iso, 1)));
    $(root, "#td-today")?.addEventListener("click", () => go(localIso(new Date())));
    $(root, "#td-regen")?.addEventListener("click", async () => {
      msg("Regenerating…");
      const r = await tryApi<Day>("/day/generate", { method: "POST", body: JSON.stringify({ date: iso, force: true }) });
      if (r.ok) { day = r.data; await refreshWeek(); draw(); } else msg(r.error, true);
    });
    $(root, "#td-add")?.addEventListener("click", () => { adding = !adding; draw(); });
    $(root, "#td-add-cancel")?.addEventListener("click", () => { adding = false; draw(); });
    $(root, "#td-add-save")?.addEventListener("click", async () => {
      const min = Number(($(root, "#td-add-min") as HTMLInputElement).value) || 60;
      const cat = ($(root, "#td-add-cat") as HTMLSelectElement).value;
      const title = ($(root, "#td-add-title") as HTMLInputElement).value.trim();
      // `start` is the ordering key, not a wall-clock time — append after the last goal
      const ordered = [...(day?.blocks ?? [])].sort((a, b) => (a.start < b.start ? -1 : 1));
      const start = ordered.length ? ordered[ordered.length - 1].end : "09:00";
      const r = await tryApi<Block>("/day", { method: "POST", body: JSON.stringify({ date: iso, start, min, cat, title: title || undefined }) });
      if (r.ok) { adding = false; await reload(); } else msg(r.error, true);
    });
    for (const card of $$(root, "[data-block]")) {
      const id = card.dataset.block!;
      const b = day?.blocks.find((x) => x.id === id);
      if (!b) continue;
      for (const btn of $$(card, "button[data-act]")) {
        btn.addEventListener("click", async () => {
          const act = btn.dataset.act;
          const n = Number(btn.dataset.min || 0);
          if (act === "done") await patch(id, { status: b.status === "done" ? "planned" : "done", ...(b.status !== "done" && !b.actual_min ? { actual_min: mins(b.start, b.end) } : {}) });
          else if (act === "skip") await patch(id, { status: b.status === "skipped" ? "planned" : "skipped" });
          else if (act === "actual") await patch(id, { actual_min: btn.dataset.set ? n : Math.max(0, (b.actual_min || 0) + n) });
          else if (act === "del") {
            const r = await tryApi<{ ok: boolean }>(`/day/${id}`, { method: "DELETE" });
            if (r.ok) await reload(); else msg(r.error, true);
          }
        });
      }
    }
  }

  async function patch(id: string, body: Partial<Block>) {
    const r = await tryApi<Block>(`/day/${id}`, { method: "PUT", body: JSON.stringify(body) });
    if (!r.ok) { msg(r.error, true); return; }
    if (day) day.blocks = day.blocks.map((b) => (b.id === id ? r.data : b));
    if (day) {
      day.actual_min = day.blocks.reduce((a, b) => a + (b.actual_min || 0), 0);
      day.done = day.blocks.filter((b) => b.status === "done").length;
    }
    await refreshWeek();
    draw();
  }

  async function reload() {
    await load();
    draw();
  }

  async function refreshWeek() {
    week = await api<Week>(`/day/week?start=${weekStart(iso)}`).catch(() => week);
  }

  async function go(next: string) {
    iso = next;
    adding = false;
    if (rootEl) rootEl.innerHTML = `<div class="p-2 text-fg-muted">Loading ${esc(fmtDate(iso))}…</div>`;
    await reload();
  }

  function msg(text: string, bad = false) {
    const el = rootEl && $(rootEl, "#td-msg");
    if (el) { el.textContent = text; el.className = `px-1 text-xs ${bad ? "text-danger" : "text-fg-faint"}`; }
  }
}

function localIso(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function mins(a: string, b: string): number {
  const [ah, am] = a.split(":").map(Number);
  const [bh, bm] = b.split(":").map(Number);
  return Math.max(0, bh * 60 + bm - (ah * 60 + am));
}
function shiftDay(iso: string, n: number): string {
  const [y, m, d] = iso.split("-").map(Number);
  return localIso(new Date(y, m - 1, d + n));
}
function weekStart(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  const dt = new Date(y, m - 1, d);
  return localIso(new Date(y, m - 1, d - ((dt.getDay() + 6) % 7)));
}
function fmtDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
}
function days(iso: string | null): number | null {
  if (!iso) return null;
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  const now = new Date();
  return Math.round((Date.UTC(y, m - 1, d) - Date.UTC(now.getFullYear(), now.getMonth(), now.getDate())) / 86400000);
}
