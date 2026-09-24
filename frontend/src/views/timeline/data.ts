import { api } from "../../api";

export type Lane =
  | "milestones"
  | "applications"
  | "follow-ups"
  | "certs"
  | "learning"
  | "weekly"
  | "events";

export type Item = {
  id: string;
  lane: Lane;
  source: "timeline" | "milestone" | "application" | "followup" | "cert" | "track" | "weekly";
  source_id: string;
  date: string; // YYYY-MM-DD
  end_date: string | null;
  label: string;
  done: boolean;
  phase: string | number | null;
  track: string | null;
  editable: boolean;
  meta: Record<string, unknown>;
};

export type Health = { status: "on_track" | "at_risk" | "behind"; detail: string; metrics?: Record<string, unknown> };

export type Board = {
  items: Item[];
  anchors: {
    next_exam: string | null;
    next_exam_title: string | null;
    program_end: string | null;
    full_program_end: string | null;
    primary_due: string | null;
    primary_text: string | null;
    offer_date: string | null;
    stretch_date: string | null;
    runway_end: string | null;
    bridge_gate: string | null;
    bridge_mode: boolean;
    runway_days: number | null;
    offer_days: number | null;
  };
  lanes: Lane[];
  today: string;
  health: Partial<Record<Lane, Health>>;
  triage: Item[];
  generated_at: string;
};

export const LANE_META: Record<Lane, { label: string; dot: string; color: string }> = {
  milestones: { label: "Milestones", dot: "bg-violet-500", color: "var(--color-violet-500)" },
  applications: { label: "Applications", dot: "bg-brand-500", color: "var(--color-brand-500)" },
  "follow-ups": { label: "Follow-ups", dot: "bg-warn", color: "var(--color-warn)" },
  certs: { label: "Certs", dot: "bg-cyan-400", color: "var(--color-cyan-400)" },
  learning: { label: "Learning", dot: "bg-positive", color: "var(--color-positive)" },
  weekly: { label: "Weekly", dot: "bg-brand-400", color: "var(--color-brand-400)" },
  events: { label: "Events", dot: "bg-brand-300", color: "var(--color-brand-300)" },
};

export async function loadBoard(): Promise<Board> {
  // Live-computed aggregate — never serve a stale cached copy (health/triage drift).
  return api<Board>("/timeline/board", { cache: "no-store" });
}

// ── date math: integer day-indices off a fixed epoch (no tz, no float drift) ──
const EPOCH = Date.UTC(2026, 0, 1); // 2026-01-01

export function dayIndex(iso: string): number {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return Math.round((Date.UTC(y, m - 1, d) - EPOCH) / 86400000);
}

export function isoFromIndex(idx: number): string {
  const dt = new Date(EPOCH + idx * 86400000);
  return `${dt.getUTCFullYear()}-${String(dt.getUTCMonth() + 1).padStart(2, "0")}-${String(dt.getUTCDate()).padStart(2, "0")}`;
}

export function todayIso(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
