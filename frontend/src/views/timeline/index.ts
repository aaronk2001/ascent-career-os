import { routeParam, type View } from "../../router";
import { $, $$, esc } from "../../ui";
import { toast } from "../../notifications";
import { type Board, type Item, type Lane, LANE_META, loadBoard } from "./data";
import { drawGantt, type GanttState, type ZoomLevel } from "./gantt";
import { mountCalendar } from "./calendar";
import { openPopover, writeDate, writeDone, deleteItem } from "./interact";
import { renderTriage } from "./triage";
import { renderAttention } from "./health";

type Mode = "gantt" | "month";
type Section = Lane | "all";
type UiState = { mode: Mode; zoom: ZoomLevel; section: Section; hidden: Lane[] };

const UI_KEY = "ascent:timeline-ui";
const ZOOMS: ZoomLevel[] = ["quarter", "month", "week"];

function loadUi(): UiState {
  try {
    const s = JSON.parse(localStorage.getItem(UI_KEY) || "{}") as Partial<UiState>;
    const z = routeParam("zoom") as ZoomLevel | null; // #/timeline?zoom=week deep link
    return { mode: s.mode ?? "gantt", zoom: (z && ZOOMS.includes(z) ? z : s.zoom) ?? "month", section: s.section ?? "all", hidden: s.hidden ?? [] };
  } catch {
    return { mode: "gantt", zoom: "month", section: "all", hidden: [] };
  }
}

export default function timeline(): View {
  const ui = loadUi();
  const hidden = new Set<Lane>(ui.hidden);
  let board: Board | null = null;
  let disposeGantt: (() => void) | null = null;
  let rootEl: HTMLElement | null = null;

  const save = () =>
    localStorage.setItem(UI_KEY, JSON.stringify({ mode: ui.mode, zoom: ui.zoom, section: ui.section, hidden: [...hidden] }));

  return {
    cleanup() {
      disposeGantt?.();
      disposeGantt = null;
      document.querySelectorAll(".tl-popover").forEach((n) => n.remove());
    },
    async render(root) {
      rootEl = root;
      root.innerHTML = `<div class="p-2 text-fg-muted">Loading timeline…</div>`;
      board = await loadBoard();
      shell();
    },
  };

  function shell() {
    if (!rootEl || !board) return;
    const a = board.anchors;
    const chips = [
      a.next_exam ? cd(a.next_exam_title ? `Exam · ${a.next_exam_title}` : "Next exam", a.next_exam) : "",
      cd("Offer", a.offer_date),
      cd("Stretch", a.stretch_date),
      cd("Runway", a.runway_end, a.runway_days != null && a.runway_days <= 21 ? "text-warn font-medium" : undefined),
      cd("Bridge gate", a.bridge_gate),
    ].join("");

    const sectionTab = (id: Section, label: string, dot?: string) => {
      const active = ui.section === id;
      return `<button data-section="${id}" class="inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs transition-colors ${active ? "border-[color:var(--accent)] accent-text bg-[color-mix(in_oklab,var(--accent)_12%,transparent)]" : "border-line text-fg-muted hover:text-fg hover:border-line-strong"}">${dot ? `<span class="h-2 w-2 rounded-full ${dot}"></span>` : ""}${esc(label)}</button>`;
    };
    const sectionTabs = [sectionTab("all", "All")]
      .concat(board.lanes.map((l) => sectionTab(l, LANE_META[l].label, LANE_META[l].dot)))
      .join("");

    const zoomSeg = ZOOMS.map((z) =>
      `<button data-zoom="${z}" class="px-2.5 py-1 text-xs capitalize transition-colors ${ui.zoom === z ? "accent-bg text-white" : "text-fg-muted hover:text-fg"}">${z}</button>`).join("");

    rootEl.innerHTML = `
      <div class="space-y-4 pb-6">
        <div class="flex flex-wrap items-center justify-between gap-3 px-2">
          <h1 class="text-2xl font-semibold tracking-tight">Timeline</h1>
          <div class="flex flex-wrap items-center gap-2">
            ${chips}
            <div class="flex rounded-lg overflow-hidden border border-line ${ui.mode === "month" ? "hidden" : ""}">${zoomSeg}</div>
            <div class="flex rounded-lg overflow-hidden border border-line">
              <button data-mode="gantt" class="px-2.5 py-1 text-xs transition-colors ${ui.mode === "gantt" ? "accent-bg text-white" : "text-fg-muted hover:text-fg"}">Gantt</button>
              <button data-mode="month" class="px-2.5 py-1 text-xs transition-colors ${ui.mode === "month" ? "accent-bg text-white" : "text-fg-muted hover:text-fg"}">Month</button>
            </div>
            <a href="/api/calendar.ics" download class="flex items-center gap-1.5 rounded-lg glass px-3 py-1.5 text-xs text-fg-muted hover:text-fg transition-colors">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 3v12M7 10l5 5 5-5M5 21h14"/></svg>Export</a>
          </div>
        </div>
        <div id="tl-attention" class="flex flex-wrap gap-2 px-2 empty:hidden"></div>
        <div id="tl-triage" class="px-2"></div>
        <div class="flex flex-wrap gap-1.5 px-2 ${ui.mode === "month" ? "hidden" : ""}">${sectionTabs}</div>
        <div id="tl-body" class="${ui.mode === "gantt" ? "card p-0 overflow-hidden" : ""}"></div>
      </div>`;

    $$(rootEl, "[data-section]").forEach((b) =>
      b.addEventListener("click", () => { ui.section = b.dataset.section as Section; save(); shell(); }),
    );
    $$(rootEl, "[data-zoom]").forEach((b) => b.addEventListener("click", () => { ui.zoom = b.dataset.zoom as ZoomLevel; save(); shell(); }));
    $$(rootEl, "[data-mode]").forEach((b) => b.addEventListener("click", () => { ui.mode = b.dataset.mode as Mode; save(); shell(); }));

    const attnHost = $(rootEl, "#tl-attention");
    if (attnHost)
      renderAttention(attnHost, board, (lane) => {
        ui.section = lane; // focus that section
        ui.mode = "gantt";
        save();
        shell();
      });

    const triageHost = $(rootEl, "#tl-triage");
    if (triageHost) renderTriage(triageHost, board, { onDone: (i) => toggleDone(i), onReschedule: reschedule, onDelete: remove });

    body();
  }

  function body() {
    if (!rootEl || !board) return;
    disposeGantt?.();
    disposeGantt = null;
    const host = $(rootEl, "#tl-body")!;
    if (ui.mode === "month") {
      mountCalendar(host, board, hidden, reload);
      return;
    }
    const state: GanttState = {
      zoom: ui.zoom,
      hidden,
      today: board.today,
      solo: ui.section === "all" ? null : ui.section,
      onItemClick: (item, el) =>
        openPopover(item, el, { onReschedule: reschedule, onToggleDone: toggleDone, onDelete: remove }),
      onDrag: reschedule,
    };
    disposeGantt = drawGantt(host, board, state);
    const scroller = $(host, "#tl-scroll");
    scroller?.addEventListener(
      "wheel",
      (e) => {
        if (!e.ctrlKey) return;
        e.preventDefault();
        const i = ZOOMS.indexOf(ui.zoom);
        const next = ZOOMS[Math.min(ZOOMS.length - 1, Math.max(0, i + (e.deltaY < 0 ? 1 : -1)))];
        if (next !== ui.zoom) { ui.zoom = next; save(); shell(); }
      },
      { passive: false },
    );
  }

  // ── mutations: optimistic local change → redraw → API → reconcile ──────────
  function localPatch(id: string, patch: Partial<Item>) {
    if (!board) return;
    const it = board.items.find((i) => i.id === id);
    if (it) Object.assign(it, patch);
  }

  async function reschedule(item: Item, newIso: string) {
    if (!item.editable) return toast("That item is locked — edit it in its own section.", "info");
    localPatch(item.id, { date: newIso });
    shell();
    const res = await writeDate(item, newIso);
    if (res.ok) toast(`Moved “${trim(item.label)}” to ${newIso}`, "ok");
    else toast(res.error || "Reschedule failed", "err");
    await reload();
  }

  async function toggleDone(item: Item) {
    const next = !item.done;
    localPatch(item.id, { done: next });
    shell();
    const res = await writeDone(item, next);
    if (!res.ok) toast(res.error || "Update failed", "err");
    await reload();
  }

  async function remove(item: Item) {
    const res = await deleteItem(item);
    if (res.ok) toast("Deleted", "ok");
    else toast(res.error || "Delete failed", "err");
    await reload();
  }

  async function reload() {
    board = await loadBoard();
    shell();
  }
}

const trim = (s: string) => (s.length > 28 ? s.slice(0, 27) + "…" : s);

/** Countdown chip; whole days from today (UTC midnights → DST-safe, matches
 * Dashboard/Focus). Past → check mark. */
function cd(label: string, iso: string | null, tone?: string): string {
  if (!iso) return "";
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  const now = new Date();
  const n = Math.round((Date.UTC(y, m - 1, d) - Date.UTC(now.getFullYear(), now.getMonth(), now.getDate())) / 86400000);
  const t = tone ?? (n < 0 ? "text-fg-faint" : "text-goal font-medium");
  return `<span class="rounded-full glass px-2.5 py-1 text-xs ${t}" title="${esc(iso)}">${esc(label)} ${n < 0 ? "✓" : n + " d"}</span>`;
}
