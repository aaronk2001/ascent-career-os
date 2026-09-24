import { tryApi } from "../../api";
import { esc } from "../../ui";
import { type Item, LANE_META } from "./data";

type Result = { ok: true; data: unknown } | { ok: false; error: string };

/** Where a dragged/edited item's new date is written back. Null = not reschedulable. */
export function writeDate(item: Item, newIso: string): Promise<Result> {
  switch (item.source) {
    case "timeline":
      return tryApi(`/timeline/${item.source_id}`, { method: "PUT", body: JSON.stringify({ date: newIso }) });
    case "milestone":
      return tryApi(`/goals/milestones/${item.source_id}`, { method: "PUT", body: JSON.stringify({ due: newIso }) });
    case "followup": {
      const field = (item.meta as { field?: string }).field || "next_action_due";
      return tryApi(`/applications/${item.source_id}`, { method: "PUT", body: JSON.stringify({ [field]: newIso }) });
    }
    case "cert":
      return tryApi(`/certifications/${item.source_id}`, { method: "PUT", body: JSON.stringify({ exam_date: newIso }) });
    default:
      return Promise.resolve({ ok: false, error: "locked" });
  }
}

/** Toggle completion. Only meaningful for timeline / milestone / cert. */
export function writeDone(item: Item, done: boolean): Promise<Result> {
  switch (item.source) {
    case "timeline":
      return tryApi(`/timeline/${item.source_id}`, { method: "PUT", body: JSON.stringify({ done: done ? 1 : 0 }) });
    case "milestone":
      return tryApi(`/goals/milestones/${item.source_id}`, { method: "PUT", body: JSON.stringify({ done: done ? 1 : 0 }) });
    case "cert":
      return tryApi(`/certifications/${item.source_id}`, {
        method: "PUT",
        body: JSON.stringify({ status: done ? "completed" : "in_progress" }),
      });
    case "weekly": // backend endpoint toggles; body ignored
      return tryApi(`/goals/weekly/${item.source_id}`, { method: "PUT" });
    default:
      return Promise.resolve({ ok: false, error: "not completable here" });
  }
}

/** Hard delete — only ad-hoc timeline events and milestones (never apps/certs/tracks). */
export function deleteItem(item: Item): Promise<Result> {
  if (item.source === "timeline") return tryApi(`/timeline/${item.source_id}`, { method: "DELETE" });
  if (item.source === "milestone") return tryApi(`/goals/milestones/${item.source_id}`, { method: "DELETE" });
  return Promise.resolve({ ok: false, error: "not deletable here" });
}

const SECTION: Partial<Record<Item["source"], { route: string; label: string }>> = {
  application: { route: "applications", label: "Applications" },
  followup: { route: "applications", label: "Applications" },
  cert: { route: "certs", label: "Certifications" },
  track: { route: "tracks", label: "Learning" },
};

export type PopoverHandlers = {
  onReschedule: (item: Item, newIso: string) => void;
  onToggleDone: (item: Item) => void;
  onDelete: (item: Item) => void;
};

/** Floating detail/edit card anchored to an item element. Returns a close fn. */
export function openPopover(item: Item, anchor: HTMLElement, h: PopoverHandlers): () => void {
  document.querySelectorAll(".tl-popover").forEach((n) => n.remove());
  const m = LANE_META[item.lane];
  const notes = (item.meta as { notes?: string }).notes;
  const canDone =
    item.source === "timeline" || item.source === "milestone" || item.source === "cert" || item.source === "weekly";
  const canDelete = item.source === "timeline" || item.source === "milestone";
  const sect = SECTION[item.source];

  const pop = document.createElement("div");
  pop.className = "tl-popover fixed z-[90] w-72 glass border border-line-strong rounded-xl p-3 anim-fade-up";
  pop.innerHTML = `
    <div class="flex items-start gap-2 mb-2">
      <span class="mt-1 h-2 w-2 rounded-full ${m.dot} shrink-0"></span>
      <div class="text-sm font-medium leading-snug">${esc(item.label)}</div>
    </div>
    <div class="text-[11px] text-fg-faint mb-2">${m.label}${item.track ? ` · ${esc(item.track)}` : ""}${item.done ? " · done" : ""}</div>
    ${notes ? `<div class="text-xs text-fg-muted mb-2">${esc(notes)}</div>` : ""}
    <label class="block text-[11px] text-fg-faint mb-1">Date</label>
    <input type="date" value="${esc(item.date)}" ${item.editable ? "" : "disabled"}
      class="tl-date w-full bg-ink-800 rounded-lg px-2.5 py-1.5 text-sm mb-3 ${item.editable ? "" : "opacity-50"}" />
    <div class="flex flex-wrap gap-2">
      ${canDone ? `<button class="tl-done btn-accent rounded-lg px-2.5 py-1 text-xs">${item.done ? "Mark undone" : "Mark done"}</button>` : ""}
      ${sect ? `<button class="tl-open rounded-lg bg-ink-800 hover:bg-ink-700 px-2.5 py-1 text-xs text-fg-muted">Open in ${sect.label}</button>` : ""}
      ${canDelete ? `<button class="tl-del rounded-lg bg-ink-800 hover:bg-danger/20 px-2.5 py-1 text-xs text-fg-faint hover:text-danger ml-auto">Delete</button>` : ""}
    </div>
    ${item.editable ? "" : `<div class="mt-2 text-[10px] text-fg-faint">Locked — edit in ${sect?.label ?? "its section"}.</div>`}`;
  document.body.append(pop);

  const r = anchor.getBoundingClientRect();
  const w = 288;
  pop.style.left = `${Math.min(Math.max(8, r.left), window.innerWidth - w - 8)}px`;
  const below = r.bottom + 8;
  pop.style.top = `${below + pop.offsetHeight > window.innerHeight ? Math.max(8, r.top - pop.offsetHeight - 8) : below}px`;

  const close = () => {
    pop.remove();
    document.removeEventListener("keydown", onKey);
    document.removeEventListener("pointerdown", onOutside, true);
  };
  const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
  const onOutside = (e: Event) => {
    if (!pop.contains(e.target as Node) && e.target !== anchor) close();
  };
  document.addEventListener("keydown", onKey);
  setTimeout(() => document.addEventListener("pointerdown", onOutside, true), 0);

  pop.querySelector(".tl-date")?.addEventListener("change", (e) => {
    const v = (e.target as HTMLInputElement).value;
    if (v && v !== item.date) { close(); h.onReschedule(item, v); }
  });
  pop.querySelector(".tl-done")?.addEventListener("click", () => { close(); h.onToggleDone(item); });
  pop.querySelector(".tl-del")?.addEventListener("click", () => { close(); h.onDelete(item); });
  pop.querySelector(".tl-open")?.addEventListener("click", () => { close(); if (sect) location.hash = `#/${sect.route}`; });

  return close;
}
