import { esc } from "../../ui";
import { type Board, type Lane, LANE_META } from "./data";

const TONE = {
  behind: { chip: "border-danger/50 text-danger", dot: "bg-danger" },
  at_risk: { chip: "border-warn/50 text-warn", dot: "bg-warn" },
  on_track: { chip: "border-positive/40 text-positive", dot: "bg-positive" },
} as const;

// Lanes whose health links to a real section route.
const ROUTE: Partial<Record<Lane, string>> = {
  applications: "applications",
  "follow-ups": "applications",
  certs: "certs",
  learning: "tracks",
};

/** Attention strip: one pill per lane that isn't on_track. Click → toggle that
 * lane solo (via onFocusLane) or jump to its section. Empty when all green. */
export function renderAttention(host: HTMLElement, board: Board, onFocusLane: (lane: Lane) => void) {
  const flagged = board.lanes
    .map((l) => ({ l, h: board.health[l] }))
    .filter((x) => x.h && x.h.status !== "on_track");
  if (!flagged.length) {
    host.innerHTML = "";
    return;
  }
  host.innerHTML = flagged
    .map(({ l, h }) => {
      const t = TONE[h!.status];
      const m = LANE_META[l];
      const route = ROUTE[l];
      return `<button data-lane-focus="${l}" ${route ? `data-route="${route}"` : ""}
        class="inline-flex items-center gap-1.5 rounded-full border ${t.chip} px-2.5 py-1 text-xs transition-colors hover:bg-ink-800/60">
        <span class="h-1.5 w-1.5 rounded-full ${t.dot}"></span>
        <span class="text-fg-muted">${m.label}:</span> ${esc(h!.detail)}</button>`;
    })
    .join("");

  host.querySelectorAll<HTMLButtonElement>("[data-lane-focus]").forEach((b) =>
    b.addEventListener("click", (e) => {
      const route = b.dataset.route;
      if (route && (e.metaKey || e.ctrlKey)) { location.hash = `#/${route}`; return; }
      onFocusLane(b.dataset.laneFocus as Lane);
    }),
  );
}
