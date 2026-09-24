import { $$, esc } from "../../ui";
import { type Board, type Item, LANE_META } from "./data";

export type TriageHandlers = {
  onDone: (item: Item) => void;
  onReschedule: (item: Item, newIso: string) => void;
  onDelete: (item: Item) => void;
};

type TriageItem = Item & { suggested?: string };

/** Collapsible "needs attention" strip for overdue milestones / stray events. */
export function renderTriage(host: HTMLElement, board: Board, h: TriageHandlers) {
  const triage = board.triage as TriageItem[];
  if (!triage.length) {
    host.innerHTML = "";
    return;
  }
  const rows = triage
    .map((i) => {
      const m = LANE_META[i.lane];
      const canDelete = i.source === "timeline" || i.source === "milestone";
      return `<div class="flex items-center gap-2 py-1.5 text-sm border-t border-line/60 first:border-0" data-tid="${esc(i.id)}">
        <span class="h-2 w-2 rounded-full ${m.dot} shrink-0"></span>
        <span class="flex-1 truncate">${esc(i.label)}</span>
        <span class="text-[11px] text-danger nums shrink-0">${esc(i.date)}</span>
        <button data-act="done" class="rounded-md bg-ink-800 hover:bg-positive/20 hover:text-positive px-2 py-0.5 text-[11px] text-fg-muted">Done</button>
        <button data-act="resc" class="rounded-md bg-ink-800 hover:bg-ink-700 px-2 py-0.5 text-[11px] text-fg-muted" title="Move to ${esc(i.suggested || "")}">+2 wks</button>
        ${canDelete ? `<button data-act="del" class="rounded-md bg-ink-800 hover:bg-danger/20 px-2 py-0.5 text-[11px] text-fg-faint hover:text-danger">Drop</button>` : ""}
      </div>`;
    })
    .join("");

  host.innerHTML = `
    <details class="card p-3 border-warn/30" open>
      <summary class="flex items-center gap-2 cursor-default list-none select-none">
        <span class="h-2 w-2 rounded-full bg-warn"></span>
        <span class="text-sm font-medium">Needs attention</span>
        <span class="text-[11px] text-fg-faint nums">${triage.length} overdue</span>
      </summary>
      <div class="mt-2">${rows}</div>
    </details>`;

  const byId = new Map(triage.map((i) => [i.id, i]));
  $$(host, "[data-tid]").forEach((row) => {
    const item = byId.get(row.dataset.tid!);
    if (!item) return;
    $$(row, "[data-act]").forEach((b) =>
      b.addEventListener("click", () => {
        const act = b.dataset.act;
        if (act === "done") h.onDone(item);
        else if (act === "resc") h.onReschedule(item, item.suggested || item.date);
        else if (act === "del") h.onDelete(item);
      }),
    );
  });
}
