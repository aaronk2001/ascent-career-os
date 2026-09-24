export function esc(s: unknown): string {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function $<T extends HTMLElement = HTMLElement>(
  root: ParentNode,
  sel: string,
): T | null {
  return root.querySelector<T>(sel);
}

export function $$<T extends HTMLElement = HTMLElement>(
  root: ParentNode,
  sel: string,
): T[] {
  return Array.from(root.querySelectorAll<T>(sel));
}

const STAGE_TONE: Record<string, string> = {
  offer: "text-positive border-positive/40",
  rejected: "text-fg-faint border-line",
  completed: "text-positive border-positive/40",
  in_progress: "text-brand-400 border-brand-500/40",
  not_started: "text-fg-muted border-line",
};

export function badge(label: string, key?: string): string {
  const tone = (key && STAGE_TONE[key]) || "text-fg-muted border-line";
  return `<span class="inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] ${tone}">${esc(label)}</span>`;
}

export function progressBar(pct: number, tone = "bg-brand-500"): string {
  const w = Math.max(0, Math.min(100, Math.round(pct)));
  return `<div class="h-1.5 rounded-full bg-ink-700 overflow-hidden"><div class="bar-fill h-full ${tone}" style="width:${w}%"></div></div>`;
}

export function titleCase(s: string): string {
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
