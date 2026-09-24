import { esc } from "../../ui";
import { type Board, type Health, type Item, type Lane, LANE_META, dayIndex, isoFromIndex } from "./data";

export type ZoomLevel = "quarter" | "month" | "week";
export const PX_PER_DAY: Record<ZoomLevel, number> = { quarter: 3, month: 8, week: 24 };

export type GanttState = {
  zoom: ZoomLevel;
  hidden: Set<Lane>;
  today: string;
  solo?: Lane | null; // focus a single section (larger, readable); null = all lanes
  onItemClick?: (item: Item, el: HTMLElement) => void;
  onDrag?: (item: Item, newIso: string) => void;
};

const PILL_H = 22;
const V_GAP = 4;
const ROW_PAD = 8;
const RULER_H = 34;
const RAIL_W = 112;
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

type Placed = Item & { x: number; w: number; sub: number };

/** Estimate a point-item's pill width from its label (for collision packing). */
function pillWidth(item: Item, pxPerDay: number): number {
  if (item.end_date && item.end_date !== item.date) {
    const span = dayIndex(item.end_date) - dayIndex(item.date) + 1;
    return Math.max(span * pxPerDay, 26);
  }
  return Math.min(item.label.length * 6.4 + 26, 240);
}

/** Greedy sub-lane packing: each item drops into the first row whose last item cleared. */
function pack(items: Item[], startDay: number, pxPerDay: number): { placed: Placed[]; subs: number } {
  const sorted = items
    .map((it) => {
      let x = (dayIndex(it.date) - startDay) * pxPerDay;
      let w = pillWidth(it, pxPerDay);
      // a bar straddling the left edge (started before the view window) gets its
      // left clamped to 0 so the visible remainder still renders.
      if (it.end_date && it.end_date !== it.date && x < 0) {
        w = Math.max((dayIndex(it.end_date) - startDay + 1) * pxPerDay, 26);
        x = 0;
      }
      return { it, x, w };
    })
    .sort((a, b) => a.x - b.x);
  const rowEnds: number[] = [];
  const placed: Placed[] = [];
  for (const { it, x, w } of sorted) {
    let sub = rowEnds.findIndex((end) => x >= end + 6);
    if (sub === -1) {
      sub = rowEnds.length;
      rowEnds.push(0);
    }
    rowEnds[sub] = x + w;
    placed.push({ ...it, x, w, sub });
  }
  return { placed, subs: Math.max(rowEnds.length, 1) };
}

/** Full rebuild of the gantt into `host`. Returns cleanup for listeners. */
export function drawGantt(host: HTMLElement, board: Board, state: GanttState): () => void {
  const pxPerDay = PX_PER_DAY[state.zoom];
  const solo = state.solo ?? null;
  const today = state.today;
  const ph = solo ? 30 : PILL_H; // taller, roomier rows when a single section is focused
  const vg = solo ? 8 : V_GAP;
  const laneList = (solo ? [solo] : board.lanes).filter((l) => !state.hidden.has(l));
  const lanes = laneList;
  // strictly today-forward: a point item shows if its date >= today; a bar shows
  // if it hasn't ended yet. Past items live in the triage strip, not the chart.
  const items = board.items.filter(
    (i) => !state.hidden.has(i.lane) && (!solo || i.lane === solo) && (i.end_date ?? i.date) >= today,
  );

  const days = items.map((i) => dayIndex(i.date)).concat(items.filter((i) => i.end_date).map((i) => dayIndex(i.end_date!)));
  const tIdx = dayIndex(today);
  // Range opens on today (2-day gutter); no past padding.
  const startDay = tIdx - 2;
  const endDay = Math.max(...days, tIdx + 30) + 20;
  const width = (endDay - startDay) * pxPerDay;

  // per-lane packing → row heights
  const byLane = new Map<Lane, { placed: Placed[]; subs: number; top: number; h: number }>();
  let y = 0;
  for (const lane of lanes) {
    const laneItems = items.filter((i) => i.lane === lane);
    const { placed, subs } = pack(laneItems, startDay, pxPerDay);
    const h = subs * (ph + vg) - vg + ROW_PAD * 2;
    byLane.set(lane, { placed, subs, top: y, h });
    y += h;
  }
  const bodyH = Math.max(y, 80);

  const rulerHtml = buildRuler(startDay, endDay, pxPerDay, state.zoom);
  const gridHtml = buildGridlines(startDay, endDay, pxPerDay, state.zoom, bodyH);
  const todayX = (tIdx - startDay) * pxPerDay;

  // lane label rail (sticky left) — one block per lane, aligned to row tops
  const railHtml = lanes
    .map((lane) => {
      const r = byLane.get(lane)!;
      const m = LANE_META[lane];
      const health = board.health[lane];
      const badge = health ? healthDot(health.status) : "";
      return `<div class="flex items-center gap-1.5 px-2.5 border-b border-line" style="height:${r.h}px" title="${health ? esc(health.detail) : ""}">
        <span class="h-2 w-2 rounded-full ${m.dot} shrink-0"></span>
        <span class="text-[11px] text-fg-muted truncate">${m.label}</span>${badge}</div>`;
    })
    .join("");

  // item pills per lane
  const itemsHtml = lanes
    .map((lane) => {
      const r = byLane.get(lane)!;
      const pills = r.placed.map((p) => itemPill(p, r.top, ph, vg, !!solo)).join("");
      return pills;
    })
    .join("");

  host.innerHTML = `
    <div class="grid" style="grid-template-columns:${RAIL_W}px 1fr">
      <div class="border-r border-line bg-ink-900/40">
        <div style="height:${RULER_H}px" class="border-b border-line"></div>
        ${railHtml}
      </div>
      <div id="tl-scroll" class="overflow-x-auto overflow-y-hidden">
        <div class="relative" style="width:${width}px">
          <div class="relative" style="height:${RULER_H}px">${rulerHtml}</div>
          <div class="relative" style="height:${bodyH}px">
            ${gridHtml}
            <div class="absolute top-0 bottom-0 z-20 pointer-events-none" style="left:${todayX}px">
              <div class="w-px h-full" style="background:var(--accent)"></div>
              <div class="absolute -top-0.5 -left-1 h-2 w-2 rounded-full" style="background:var(--accent)"></div>
            </div>
            ${itemsHtml}
          </div>
        </div>
      </div>
    </div>`;

  // open on today: today-line sits at the left edge, history scrollable to the left
  const scroller = host.querySelector<HTMLElement>("#tl-scroll");
  if (scroller) scroller.scrollLeft = Math.max(0, todayX - 8);

  return wireInteractions(host, board, state, pxPerDay);
}

/** Click-to-open + pointer-drag reschedule for editable items. Returns cleanup. */
function wireInteractions(
  host: HTMLElement,
  board: Board,
  state: GanttState,
  pxPerDay: number,
): () => void {
  let drag: { el: HTMLElement; item: Item; startX: number; moved: boolean; dayDelta: number } | null = null;

  const onPointerDown = (e: PointerEvent) => {
    if (e.button !== 0) return;
    const el = (e.target as HTMLElement).closest<HTMLElement>("[data-item-id]");
    if (!el) return;
    const item = board.items.find((i) => i.id === el.dataset.itemId);
    if (!item) return;
    if (el.dataset.editable !== "true" || !state.onDrag) return; // locked items: click only
    drag = { el, item, startX: e.clientX, moved: false, dayDelta: 0 };
    el.setPointerCapture(e.pointerId);
  };

  const onPointerMove = (e: PointerEvent) => {
    if (!drag) return;
    const dx = e.clientX - drag.startX;
    if (Math.abs(dx) < 4 && !drag.moved) return; // threshold — below it, still a click
    drag.moved = true;
    drag.dayDelta = Math.round(dx / pxPerDay);
    drag.el.style.transform = `translateX(${drag.dayDelta * pxPerDay}px)`;
    drag.el.style.zIndex = "40";
    drag.el.style.opacity = "0.85";
  };

  const onPointerUp = (e: PointerEvent) => {
    if (!drag) return;
    const d = drag;
    drag = null;
    d.el.releasePointerCapture?.(e.pointerId);
    d.el.style.transform = "";
    d.el.style.opacity = "";
    if (!d.moved) {
      state.onItemClick?.(d.item, d.el); // treat as click
      return;
    }
    if (d.dayDelta !== 0) {
      // clamp to today — the chart is today-forward, so a past target would just
      // make the item vanish from view.
      const idx = Math.max(dayIndex(d.item.date) + d.dayDelta, dayIndex(state.today));
      const newIso = isoFromIndex(idx);
      if (newIso !== d.item.date) state.onDrag?.(d.item, newIso);
    }
  };

  // plain click for locked items (no drag path)
  const onClick = (e: Event) => {
    const el = (e.target as HTMLElement).closest<HTMLElement>("[data-item-id]");
    if (!el || el.dataset.editable === "true") return; // editable handled via pointerup
    const item = board.items.find((i) => i.id === el.dataset.itemId);
    if (item) state.onItemClick?.(item, el);
  };

  host.addEventListener("pointerdown", onPointerDown);
  host.addEventListener("pointermove", onPointerMove);
  host.addEventListener("pointerup", onPointerUp);
  host.addEventListener("click", onClick);
  return () => {
    host.removeEventListener("pointerdown", onPointerDown);
    host.removeEventListener("pointermove", onPointerMove);
    host.removeEventListener("pointerup", onPointerUp);
    host.removeEventListener("click", onClick);
  };
}

function itemPill(p: Placed, laneTop: number, ph: number, vg: number, solo: boolean): string {
  const m = LANE_META[p.lane];
  const top = laneTop + ROW_PAD + p.sub * (ph + vg);
  const past = p.done;
  const anchor = p.lane === "milestones" && (p.meta as { anchor?: boolean }).anchor;
  const isBar = !!p.end_date && p.end_date !== p.date;
  const overdue = (p.meta as { overdue?: boolean }).overdue;
  const tone = anchor ? "text-goal font-semibold" : past ? "text-fg-faint" : "text-fg";
  const border = overdue ? "border-danger/60" : "border-line-strong";
  const bg = isBar
    ? `background:color-mix(in oklab, ${m.color} 22%, transparent);border-color:color-mix(in oklab, ${m.color} 45%, transparent)`
    : "";
  const editableRing = p.editable ? "" : "opacity-95";
  const maxW = solo ? 460 : 240;
  const text = solo ? "text-[12px]" : "text-[11px]";
  // focused view has room to show the date inline
  const dateTag = solo && !isBar ? `<span class="ml-1 shrink-0 text-fg-faint nums text-[10px]">${esc(p.date.slice(5))}</span>` : "";
  // meta.parked = the track YAML says `active: false` (timeline_board._collect_track_weeks)
  const parked = p.lane === "learning" && (p.meta.parked === true || p.label.includes("[parked]"));
  const parkedClass = parked ? "opacity-45" : "";
  const titleText = parked ? `${p.label} · after offer` : p.label;
  return `<div data-item-id="${esc(p.id)}" data-editable="${p.editable}"
      class="absolute flex items-center gap-1 rounded-md border ${border} ${editableRing} ${parkedClass} px-1.5 ${text} leading-none ${tone} ${past ? "line-through" : ""} ${isBar ? "" : "bg-ink-850/90 backdrop-blur-sm"} hover:z-30 hover:border-[color:var(--accent)] transition-colors"
      style="left:${p.x}px;top:${top}px;height:${ph}px;${isBar ? `width:${p.w}px;${bg}` : `max-width:${maxW}px`}"
      title="${esc(titleText)}">
      ${isBar ? "" : `<span class="h-1.5 w-1.5 rounded-full ${m.dot} shrink-0"></span>`}
      <span class="truncate">${anchor ? "★ " : ""}${esc(p.label)}</span>${dateTag}
    </div>`;
}

function healthDot(status: Health["status"]): string {
  const c = status === "on_track" ? "bg-positive" : status === "at_risk" ? "bg-warn" : "bg-danger";
  return `<span class="ml-auto h-1.5 w-1.5 rounded-full ${c} shrink-0"></span>`;
}

/** Month labels along the top ruler; week/day numbers as zoom tightens. */
function buildRuler(startDay: number, endDay: number, pxPerDay: number, zoom: ZoomLevel): string {
  const out: string[] = [];
  let cursor = new Date(Date.UTC(2026, 0, 1) + startDay * 86400000);
  // walk month starts
  let d = new Date(Date.UTC(cursor.getUTCFullYear(), cursor.getUTCMonth(), 1));
  while (idxOf(d) <= endDay) {
    const x = (idxOf(d) - startDay) * pxPerDay;
    const label = `${MONTHS[d.getUTCMonth()]}${d.getUTCMonth() === 0 ? " " + d.getUTCFullYear() : ""}`;
    out.push(`<div class="absolute top-1 text-[11px] font-medium text-fg-muted" style="left:${x + 4}px">${label}</div>`);
    d = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 1));
  }
  if (zoom === "week") {
    // day numbers (weekends dimmed); each track's own days show as its bars
    for (let i = startDay; i <= endDay; i++) {
      const dt = new Date(Date.UTC(2026, 0, 1) + i * 86400000);
      const dow = dt.getUTCDay();
      const x = (i - startDay) * pxPerDay;
      const wknd = dow === 0 || dow === 6;
      out.push(`<div class="absolute bottom-0.5 text-[9px] ${wknd ? "text-fg-faint/60" : "text-fg-faint"}" style="left:${x + 3}px">${dt.getUTCDate()}</div>`);
    }
  }
  return out.join("");
}

/** Vertical gridlines: month boundaries always; week starts at month/week zoom. */
function buildGridlines(startDay: number, endDay: number, pxPerDay: number, zoom: ZoomLevel, h: number): string {
  const out: string[] = [];
  for (let i = startDay; i <= endDay; i++) {
    const dt = new Date(Date.UTC(2026, 0, 1) + i * 86400000);
    const x = (i - startDay) * pxPerDay;
    const isMonth = dt.getUTCDate() === 1;
    const isWeek = dt.getUTCDay() === 1;
    if (isMonth) {
      out.push(`<div class="absolute top-0 w-px" style="left:${x}px;height:${h}px;background:var(--color-line-strong)"></div>`);
    } else if (zoom !== "quarter" && isWeek) {
      out.push(`<div class="absolute top-0 w-px" style="left:${x}px;height:${h}px;background:var(--color-line)"></div>`);
    }
    if (zoom === "week" && (dt.getUTCDay() === 0 || dt.getUTCDay() === 6)) {
      out.push(`<div class="absolute top-0" style="left:${x}px;width:${pxPerDay}px;height:${h}px;background:color-mix(in oklab,var(--color-ink-800) 30%,transparent)"></div>`);
    }
  }
  return out.join("");
}

function idxOf(d: Date): number {
  return Math.round((d.getTime() - Date.UTC(2026, 0, 1)) / 86400000);
}
