import type { Chart as ChartType } from "chart.js";
import { api } from "../api";
import type { View } from "../router";
import { esc, badge } from "../ui";
import { countUp, growBars } from "../motion";
import { ring, mountRings } from "../visuals";
import { getPrefs, setPrefs, type WidgetPref } from "../prefs";
import { appHome, appMarkers } from "../geocode";
import { modules } from "../modules";

// chart.js (~187KB) is dynamic-imported and registered once on first chart
// mount (mirrors the globe defer below) so the hero + non-chart widgets paint
// before the chart lib is parsed.
let _Chart: typeof import("chart.js").Chart | null = null;
async function ensureChart() {
  if (_Chart) return _Chart;
  const m = await import("chart.js");
  m.Chart.register(
    m.BarController, m.BarElement, m.CategoryScale, m.LinearScale, m.Tooltip, m.Legend,
    m.DoughnutController, m.ArcElement, m.LineController, m.LineElement, m.PointElement, m.Filler,
    m.RadarController, m.RadialLinearScale,
  );
  return (_Chart = m.Chart);
}

const accent = () => getComputedStyle(document.documentElement).getPropertyValue("--accent").trim() || "#6366f1";
const accent2 = () => getComputedStyle(document.documentElement).getPropertyValue("--accent-2").trim() || "#8b5cf6";

type Stats = { total: number; by_stage: Record<string, number>; overdue_count: number; this_week_count: number; response_rate: number };
type Skill = { skill: string; target_hours: number; hours_logged: number };
type Week = { id: number; title: string; status: string; vocab?: string[] };
type Track = { id?: string; weeks?: Week[] };
type Reminder = { id: string; kind: string; title: string; due?: string | null };
type Milestone = { id: string; text: string; due?: string | null; done?: number };
type GlossTerm = { term: string; def: string; domain?: string; formula?: string | null };
type FollowupItem = { id: string; company: string; role: string; bucket: string; due: string; overdue: boolean; action: string };
type Cadence = {
  weekly_target: number; bucket_targets: Record<string, number>;
  week_total: number; week_by_bucket: Record<string, number>;
  by_bucket: Record<string, number>; needs_followup: FollowupItem[];
};
type FunnelStep = { from: string; to: string; reached_from: number; reached_to: number; rate: number };
type Funnel = { stages: string[]; reached: number[]; steps: FunnelStep[] };
type TrackSum = {
  id: string; title: string; pct: number; done: number; weeks: number; active: boolean;
  daily_hours: number | null; days: string[] | null; resume_after: string | null;
  accent?: string | null; short?: string; caption?: string;
};
type Anchors = {
  next_exam: string | null; next_exam_title: string | null; program_end: string | null; full_program_end: string | null;
  primary_due: string | null; primary_text: string | null; offer_date: string | null; stretch_date: string | null;
  runway_end: string | null; bridge_gate: string | null; bridge_mode: boolean;
  runway_days: number | null; offer_days: number | null; sprint_start: string | null; name?: string;
};
type SideSummary = {
  latest_followers: Record<string, { followers: number; date: string }>;
  posts_mtd: number; revenue_mtd: number; posts_total: number; revenue_total: number;
  streak_days: number; entries: unknown[];
};
type DayBlock = {
  id: string; start: string; end: string; cat: string; title: string; detail?: string | null;
  deep_link?: string | null; status: "planned" | "done" | "skipped"; actual_min?: number | null;
};
type DayResp = {
  date: string; template: string; blocks: DayBlock[];
  planned_min: number; actual_min: number; done: number; wake: string; hard_stop: string;
};

function daysUntil(iso: string): number {
  // UTC midnights → exact whole-day diff (no DST fractional hour); consistent
  // with Focus and the Timeline countdown so every section shows the same count.
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  const now = new Date();
  return Math.round((Date.UTC(y, m - 1, d) - Date.UTC(now.getFullYear(), now.getMonth(), now.getDate())) / 86400000);
}
function relDate(iso: string): string {
  const n = daysUntil(iso.slice(0, 10));
  return n < 0 ? `${-n}d late` : n === 0 ? "today" : n === 1 ? "tomorrow" : `in ${n}d`;
}

const STAGE_LABELS: Record<string, string> = {
  discovered: "Discovered", applied: "Applied", phone_screen: "Phone",
  technical: "Technical", onsite: "Onsite", offer: "Offer", rejected: "Rejected",
};
const KIND_DOT: Record<string, string> = { deadline: "bg-warn", followup: "bg-brand-500", cadence: "bg-violet-500" };

type Widget = { id: string; title: string; span: number; min: number; max: number; body: () => string; mount?: (el: HTMLElement) => void | Promise<void> };

function shortDate(iso: string | null): string {
  return iso ? new Date(`${iso.slice(0, 10)}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" }) : "unset";
}
function greeting(): string {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}
function currentWeek(t: Track): Week | undefined {
  const w = t.weeks ?? [];
  return w.find((x) => x.status === "in_progress") ?? w.find((x) => x.status !== "completed");
}
function trackProgress(t: Track) {
  const w = t.weeks ?? [];
  return { done: w.filter((x) => x.status === "completed").length, total: w.length };
}
const clamp = (n: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, n));

function isoUTC(iso: string): number {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return Date.UTC(y, m - 1, d);
}
function sprintElapsedPct(endIso: string, startIso: string | null): number {
  if (!startIso) return 0;
  const start = isoUTC(startIso);
  const end = isoUTC(endIso);
  if (end <= start) return 100;
  return clamp(((Date.now() - start) / (end - start)) * 100, 0, 100);
}
// Today is an ordered goal list, not a timetable: "next" is the first open goal.
function nextGoal(blocks: DayBlock[]): DayBlock | undefined {
  return blocks.find((b) => b.status === "planned" && b.cat !== "break");
}

export default function dashboard(): View {
  let charts: ChartType[] = [];
  let disposeGlobe: (() => void) | undefined;
  let detachScroll: (() => void) | undefined;
  let editing = false;
  const killCharts = () => { charts.forEach((c) => c.destroy()); charts = []; };

  return {
    cleanup() {
      killCharts();
      disposeGlobe?.();
      detachScroll?.();
    },
    async render(root) {
      root.innerHTML = `<div class="p-2 text-fg-muted">Loading…</div>`;
      const mods = modules();
      const [s, skills, reminders, apps, miles, gloss, cad, funnel, anchors, tracks, side, day] = await Promise.all([
        api<Stats>("/applications/stats"),
        api<Skill[]>("/skills"),
        api<Reminder[]>("/reminders").catch(() => [] as Reminder[]),
        api<{ company: string; role: string; status: string; applied_date?: string | null; location?: string | null }[]>("/applications").catch(() => []),
        api<Milestone[]>("/goals/milestones").catch(() => [] as Milestone[]),
        api<{ terms: GlossTerm[] }>("/glossary").catch(() => ({ terms: [] as GlossTerm[] })),
        api<Cadence>("/applications/cadence").catch(() => ({ weekly_target: 8, bucket_targets: {}, week_total: 0, week_by_bucket: {}, by_bucket: {}, needs_followup: [] as FollowupItem[] })),
        api<Funnel>("/applications/funnel").catch(() => ({ stages: [], reached: [], steps: [] as FunnelStep[] })),
        api<Anchors>("/anchors").catch(() => ({
          next_exam: null, next_exam_title: null, program_end: null, full_program_end: null,
          primary_due: null, primary_text: null, offer_date: null, stretch_date: null,
          runway_end: null, bridge_gate: null, bridge_mode: false, runway_days: null, offer_days: null, sprint_start: null,
        } as Anchors)),
        api<TrackSum[]>("/tracks").catch(() => [] as TrackSum[]),
        (mods.side || mods.clips ? api<SideSummary>("/side/summary") : Promise.reject(new Error("off"))).catch(() => ({
          latest_followers: {}, posts_mtd: 0, revenue_mtd: 0, posts_total: 0, revenue_total: 0, streak_days: 0, entries: [],
        } as SideSummary)),
        api<DayResp>("/day").catch(() => ({
          date: new Date().toISOString().slice(0, 10), template: "", blocks: [] as DayBlock[],
          planned_min: 0, actual_min: 0, done: 0, wake: "", hard_stop: "",
        } as DayResp)),
      ]);
      // Active tracks (YAML `active: true`) drive the rings and vocab; parked ones live on Learning.
      const activeTracks = tracks.filter((t) => t.active);
      const trackDetails = await Promise.all(activeTracks.map((t) =>
        api<Track>(`/tracks/${encodeURIComponent(t.id)}`).catch(() => ({ weeks: [] } as Track))));
      const defs: Record<string, { def: string; formula?: string | null }> =
        Object.fromEntries(gloss.terms.map((t) => [t.term, { def: t.def, formula: t.formula }]));

      const todayIso = new Date().toISOString().slice(0, 10);
      const undoneGoals = miles.filter((m) => !m.done && m.due);
      const upcoming = undoneGoals.filter((m) => m.due! >= todayIso).sort((a, b) => (a.due! < b.due! ? -1 : 1));
      const overdue = undoneGoals.filter((m) => m.due! < todayIso).sort((a, b) => (a.due! > b.due! ? -1 : 1));
      const nextGoals = [...upcoming, ...overdue].slice(0, 4);
      const goalsRow = (m: Milestone) => {
        const n = daysUntil(m.due!);
        const tone = n < 0 ? "text-danger border-danger/40" : n <= 14 ? "text-warn border-warn/40" : "accent-text border-[color-mix(in_oklab,var(--accent)_40%,transparent)]";
        const lbl = n < 0 ? `${-n}d late` : n === 0 ? "today" : `${n}d`;
        return `<div class="flex items-center gap-3 rounded-xl bg-ink-800/40 px-3 py-2.5">
          <div class="shrink-0 grid place-items-center min-w-12 h-12 rounded-xl border ${tone}"><div class="text-sm font-semibold nums leading-none">${esc(lbl)}</div></div>
          <div class="min-w-0"><div class="text-sm truncate">${esc(m.text)}</div><div class="text-[11px] text-fg-faint nums">${esc(m.due!)}</div></div>
        </div>`;
      };
      const goalsSection = nextGoals.length ? `
        <section class="card p-4">
          <div class="flex items-center justify-between mb-3">
            <div class="text-sm font-medium flex items-center gap-2"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" class="accent-text"><path d="M12 2v8M12 22v-4M4.9 4.9l5.7 5.7M18.4 18.4l-1.4-1.4M2 12h8M22 12h-4"/></svg>Next goals</div>
            <a href="#/timeline" class="text-xs accent-text hover:underline">Calendar →</a>
          </div>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-2">${nextGoals.map(goalsRow).join("")}</div>
        </section>` : "";

      // applications-over-time (monthly buckets from applied_date)
      const months: string[] = [];
      const now = new Date();
      for (let i = 5; i >= 0; i--) {
        const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
        months.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`);
      }
      const trend = months.map((m) => apps.filter((a) => (a.applied_date || "").slice(0, 7) === m).length);
      const topSkills = [...skills].sort((a, b) => (b.target_hours || 0) - (a.target_hours || 0)).slice(0, 6);

      const skillHours = skills.reduce((a, x) => a + (x.hours_logged || 0), 0);
      const skillTarget = skills.reduce((a, x) => a + (x.target_hours || 0), 0);
      const pipeline = (s.by_stage.applied ?? 0) + (s.by_stage.phone_screen ?? 0) + (s.by_stage.technical ?? 0) + (s.by_stage.onsite ?? 0);

      // ── Widget registry ──────────────────────────────────────────────────
      const statTile = (label: string, val: number, cls: string, suffix = "") =>
        `<div class="card card-hover p-4"><div class="text-xs uppercase tracking-wide text-fg-faint">${label}</div>
          <div class="mt-1 text-3xl font-semibold nums ${cls}" data-count="${val}" data-suffix="${suffix}">0${suffix}</div></div>`;

      const vocabChips = (lbl: string, w?: Week) =>
        !w?.vocab?.length ? "" : `<div><div class="text-xs text-fg-faint mb-1.5">${esc(lbl)} · W${w.id} ${esc(w.title)}</div>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-1.5">${w.vocab.map((v) => {
            const d = defs[v];
            return `<div class="rounded-md bg-ink-800/50 border border-line px-2.5 py-1.5">
              <div class="flex items-baseline justify-between gap-2"><span class="text-xs font-medium">${esc(v)}</span>${d?.formula ? `<code class="shrink-0 text-[10px] accent-text font-mono whitespace-nowrap">${esc(d.formula)}</code>` : ""}</div>
              <div class="text-[11px] ${d ? "text-fg-muted" : "text-fg-faint italic"} line-clamp-2">${esc(d?.def || "Definition coming soon")}</div></div>`;
          }).join("")}</div></div>`;

      const emptyApps = `<div class="text-sm text-fg-faint py-6 text-center">No applications yet.
        <a href="#/applications" class="block mt-1 accent-text hover:underline">Add your first application →</a></div>`;

      const registry: Widget[] = [
        {
          id: "stats", title: "Key metrics", span: 4, min: 2, max: 4,
          body: () => `<div class="grid grid-cols-2 md:grid-cols-4 gap-3">
            ${statTile("Total apps", s.total, "text-fg")}
            ${statTile("In pipeline", pipeline, "accent-text")}
            ${statTile("Offers", s.by_stage.offer ?? 0, "text-positive")}
            ${statTile("Skill hours", skillHours, "text-fg", "h")}</div>`,
          mount: (el) => el.querySelectorAll<HTMLElement>("[data-count]").forEach((n) =>
            countUp(n, Number(n.dataset.count), { suffix: n.dataset.suffix || "" })),
        },
        {
          id: "pipeline", title: "Pipeline by stage", span: 2, min: 2, max: 4,
          body: () => s.total ? `<canvas height="150"></canvas>` : emptyApps,
          mount: async (el) => {
            const Chart = await ensureChart();
            const canvas = el.querySelector("canvas");
            if (!canvas?.isConnected) return;
            const stages = Object.keys(s.by_stage);
            charts.push(new Chart(canvas, {
              type: "bar",
              data: { labels: stages.map((k) => STAGE_LABELS[k] ?? k), datasets: [{ data: stages.map((k) => s.by_stage[k] ?? 0), backgroundColor: accent(), borderRadius: 6 }] },
              options: { plugins: { legend: { display: false } }, scales: { x: { grid: { display: false }, ticks: { color: "#9aa0ba" } }, y: { grid: { color: "#20202f" }, ticks: { color: "#9aa0ba", precision: 0 } } } },
            }));
          },
        },
        {
          id: "donut", title: "Stage mix", span: 1, min: 1, max: 2,
          body: () => s.total ? `<canvas height="160"></canvas>` : emptyApps,
          mount: async (el) => {
            const Chart = await ensureChart();
            const canvas = el.querySelector("canvas");
            if (!canvas?.isConnected) return;
            const stages = Object.keys(s.by_stage);
            const palette = ["#a78bfa", accent(), "#22d3ee", "#10b981", "#f59e0b", "#f43f5e", "#5f6589"];
            charts.push(new Chart(canvas, {
              type: "doughnut",
              data: { labels: stages.map((k) => STAGE_LABELS[k] ?? k), datasets: [{ data: stages.map((k) => s.by_stage[k] ?? 0), backgroundColor: stages.map((_, i) => palette[i % palette.length]), borderWidth: 0 }] },
              options: { cutout: "62%", plugins: { legend: { position: "right", labels: { color: "#9aa0ba", boxWidth: 10, font: { size: 10 } } } } },
            }));
          },
        },
        {
          id: "trend", title: "Applications · 6 mo", span: 2, min: 1, max: 4,
          body: () => trend.some(Boolean) ? `<canvas height="150"></canvas>` : emptyApps,
          mount: async (el) => {
            const Chart = await ensureChart();
            const canvas = el.querySelector("canvas");
            if (!canvas?.isConnected) return;
            charts.push(new Chart(canvas, {
              type: "line",
              data: { labels: months.map((m) => m.slice(5)), datasets: [{ data: trend, borderColor: accent(), backgroundColor: "color-mix(in oklab, " + accent() + " 22%, transparent)", fill: true, tension: 0.35, pointRadius: 3, pointBackgroundColor: accent2() }] },
              options: { plugins: { legend: { display: false } }, scales: { x: { grid: { display: false }, ticks: { color: "#9aa0ba" } }, y: { grid: { color: "#20202f" }, ticks: { color: "#9aa0ba", precision: 0 } } } },
            }));
          },
        },
        {
          id: "radar", title: "Skill coverage", span: 1, min: 1, max: 2,
          body: () => topSkills.length ? `<canvas height="180"></canvas>` : `<div class="text-sm text-fg-faint">No skills tracked.</div>`,
          mount: async (el) => {
            const Chart = await ensureChart();
            const canvas = el.querySelector("canvas");
            if (!canvas?.isConnected) return;
            charts.push(new Chart(canvas, {
              type: "radar",
              data: { labels: topSkills.map((s) => s.skill), datasets: [{ data: topSkills.map((s) => s.hours_logged || 0), borderColor: accent(), backgroundColor: "color-mix(in oklab, " + accent() + " 28%, transparent)", pointBackgroundColor: accent2() }] },
              options: { plugins: { legend: { display: false } }, scales: { r: { grid: { color: "#20202f" }, angleLines: { color: "#20202f" }, pointLabels: { color: "#9aa0ba", font: { size: 9 } }, ticks: { display: false } } } },
            }));
          },
        },
        {
          id: "progress", title: "Learning progress", span: 2, min: 1, max: 4,
          body: () => {
            const cell = (label: string, done: number, total: number, color: string, lbl: string) =>
              `<div class="flex flex-col items-center gap-2">
                ${ring(total ? (done / total) * 100 : 0, { size: 78, stroke: 7, color, label: lbl })}
                <div class="text-xs text-fg-muted">${esc(label)}</div></div>`;
            return `<div class="flex items-center justify-around gap-3 py-1">
              ${activeTracks.map((t, i) => {
                const p = trackProgress(trackDetails[i]);
                return cell(t.short ?? t.title, p.done, p.total, t.accent || "var(--accent)", `${p.done}/${p.total}`);
              }).join("")}
              ${cell("Skill hours", skillHours, skillTarget, "#10b981", `${skillHours}h`)}</div>`;
          },
          mount: (el) => mountRings(el),
        },
        {
          id: "funnel", title: "Conversion funnel", span: 2, min: 1, max: 4,
          body: () => {
            const top = funnel.reached[0] || 0;
            if (!top) return `<div class="text-sm text-fg-faint">No applications yet.</div>`;
            return `<div class="space-y-2.5">${funnel.stages.map((st, i) => {
              const c = funnel.reached[i] ?? 0;
              const w = top ? (c / top) * 100 : 0;
              const step = i > 0 ? funnel.steps[i - 1] : null;
              const rateTone = !step ? "" : step.rate >= 50 ? "text-positive" : step.rate > 0 ? "text-warn" : "text-fg-faint";
              return `<div>
                <div class="flex items-center justify-between text-xs mb-1">
                  <span class="text-fg-muted">${esc(STAGE_LABELS[st] ?? st)}</span>
                  <span class="nums text-fg-faint">${c}${step ? ` · <span class="${rateTone}">${step.rate}%</span>` : ""}</span>
                </div>
                <div class="h-2 rounded-full bg-ink-700 overflow-hidden"><div class="bar-fill h-full accent-bg" style="width:${w.toFixed(0)}%"></div></div>
              </div>`;
            }).join("")}</div>`;
          },
          mount: (el) => growBars(el),
        },
        {
          id: "followup", title: "Needs follow-up", span: 2, min: 1, max: 4,
          body: () => {
            const items = cad.needs_followup;
            if (!items.length) return `<div class="text-sm text-fg-faint">All caught up — no follow-ups due. ✦</div>`;
            return `<div class="space-y-1.5">${items.slice(0, 6).map((i) => `
              <a href="#/applications" class="flex items-center gap-2 text-sm text-fg-muted hover:text-fg transition-colors">
                <span class="h-2 w-2 rounded-full ${i.overdue ? "bg-danger" : "bg-warn"} shrink-0"></span>
                <span class="flex-1 truncate"><span class="font-medium text-fg">${esc(i.company)}</span> · ${esc(i.role)}</span>
                <span class="text-[11px] nums ${i.overdue ? "text-danger" : "text-warn"}">${esc(relDate(i.due))}</span>
              </a>`).join("")}${items.length > 6 ? `<a href="#/applications" class="block pt-1 text-xs accent-text hover:underline">+${items.length - 6} more →</a>` : ""}</div>`;
          },
        },
        {
          id: "upcoming", title: "Inbox", span: 2, min: 1, max: 4,
          body: () => reminders.length
            ? `<div class="space-y-2">${reminders.slice(0, 5).map((r) => {
                const overdue = r.due ? daysUntil(r.due.slice(0, 10)) < 0 : false;
                return `<div class="flex items-center gap-2 text-sm"><span class="h-2 w-2 rounded-full ${KIND_DOT[r.kind] ?? "bg-fg-muted"}"></span><span class="flex-1 truncate">${esc(r.title)}</span>${r.due ? `<span class="text-[11px] nums ${overdue ? "text-danger" : "text-fg-faint"}">${esc(relDate(r.due))}</span>` : ""}</div>`;
              }).join("")}</div>`
            : `<div class="text-sm text-fg-faint">Inbox zero — nothing needs you right now. ✦</div>`,
        },
        {
          id: "vocab", title: "This week's vocab", span: 4, min: 2, max: 4,
          body: () => {
            const v = activeTracks.map((t, i) => vocabChips(t.short ?? t.title, currentWeek(trackDetails[i]))).filter(Boolean).join("");
            return v ? `<div class="space-y-4">${v}</div>` : `<div class="text-sm text-fg-faint">No active track week.</div>`;
          },
        },
        ...(!mods.news ? [] : [{
          id: "news", title: "Signal · live", span: 2, min: 2, max: 4,
          body: () => `<div data-news class="text-sm text-fg-faint">Loading headlines…</div>`,
          mount: (el) => {
            const box = el.querySelector<HTMLElement>("[data-news]");
            if (!box) return;
            const dot: Record<string, string> = { robotics: "bg-brand-500", ai: "bg-violet-500", local: "bg-positive" };
            api<{ items: { title: string; link: string; source: string; topic: string }[] }>("/news")
              .then((d) => {
                box.innerHTML = d.items.slice(0, 7).map((n) =>
                  `<a href="${esc(n.link)}" target="_blank" class="flex items-start gap-2 py-1.5 text-fg-muted hover:text-fg transition-colors">
                    <span class="mt-1.5 h-1.5 w-1.5 rounded-full ${dot[n.topic] ?? "bg-fg-muted"} shrink-0"></span>
                    <span class="text-sm line-clamp-1 flex-1">${esc(n.title)}</span>
                    <span class="text-[10px] text-fg-faint shrink-0">${esc(n.source)}</span></a>`).join("")
                  || `<div class="text-sm text-fg-faint">No headlines.</div>`;
              })
              .catch(() => { box.textContent = "News unavailable."; });
          },
        } satisfies Widget]),
      ];

      const offers = s.by_stage.offer ?? 0;
      // Job-sprint spine: /api/anchors (offer/runway math) + /api/tracks
      // (active track progress) + /api/day (now/next block) drive the hero.
      const weekLine = `<span class="nums">${cad.week_total}/${cad.weekly_target}</span> apps this week`;
      const heroLine = offers
        ? `<span class="text-positive font-semibold">${offers} offer${offers > 1 ? "s" : ""} in hand</span> — keep stacking skills.`
        : anchors.offer_date
          ? `<b>${Math.max(0, anchors.offer_days ?? 0)} days</b> to the signed-offer target (${shortDate(anchors.offer_date)})${anchors.runway_end ? ` · <b>${Math.max(0, anchors.runway_days ?? 0)} days</b> of runway` : ""} · ${weekLine}`
          : `<a href="#/settings" class="accent-text hover:underline">Set an offer target and runway in Settings</a> to start the countdowns · ${weekLine}`;
      const nowBlock = nextGoal(day.blocks);
      const nowNextLine = nowBlock
        ? `<a href="#/today" class="hover:underline">Next goal: <span class="truncate">${esc(nowBlock.title)}</span> → Today</a>`
        : `<a href="#/today" class="hover:underline">Day complete — log actuals →</a>`;

      const ringCell = (pct: number, color: string, label: string, caption: string) =>
        `<div class="flex flex-col items-center gap-1">
          ${ring(pct, { size: 60, stroke: 6, color, label })}
          <div class="text-xs text-fg-faint mt-0.5">${esc(caption)}</div>
        </div>`;
      const trackRings = activeTracks.map((t) =>
        ringCell(t.weeks ? (t.done / t.weeks) * 100 : 0, t.accent || "var(--accent)", `${t.done}/${t.weeks}`, t.caption ?? t.title)).join("");
      const offerPct = anchors.offer_date ? sprintElapsedPct(anchors.offer_date, anchors.sprint_start) : 0;
      // Countdown tile: "—" plus a Settings link while its anchor date is unset.
      const countTile = (n: number | null, caption: string, tone: string) => n == null
        ? `<div class="shrink-0"><div class="text-2xl font-semibold nums text-fg-faint">—</div><a href="#/settings" class="block text-[11px] text-fg-faint mt-0.5 hover:underline">${esc(caption)} · set in Settings</a></div>`
        : `<div class="shrink-0"><div class="text-2xl font-semibold nums ${tone}" data-count="${Math.max(0, n)}">0</div><div class="text-[11px] text-fg-faint mt-0.5">${esc(caption)}</div></div>`;
      const offerLabel = anchors.offer_days != null ? `${anchors.offer_days}` : "–";

      const dStretch = anchors.stretch_date ? daysUntil(anchors.stretch_date) : null;
      const runwayTone = anchors.runway_days != null && anchors.runway_days <= 21 ? "text-warn" : "text-fg";
      const runwayDays = anchors.runway_end ? anchors.runway_days : null;

      root.innerHTML = `
        <div class="space-y-4 pb-6">
          <section class="relative card overflow-hidden min-h-[340px]">
            <div id="globe" class="absolute inset-0 opacity-0 transition-opacity duration-700"></div>
            <div class="absolute inset-0 pointer-events-none" style="background:linear-gradient(100deg, var(--color-ink-950) 3%, color-mix(in oklab, var(--color-ink-950) 52%, transparent) 33%, transparent 60%)"></div>
            <div class="relative h-full flex flex-col justify-between gap-5 p-7 max-w-2xl">
              <div>
                <div class="text-[11px] uppercase tracking-[0.22em] text-fg-faint">Mission Control · Job Sprint</div>
                <h1 class="text-3xl font-semibold tracking-tight mt-1.5">${greeting()}${anchors.name ? `, ${esc(anchors.name)}` : ""}</h1>
                <p class="text-sm text-fg-muted mt-2">${heroLine}</p>
                <p class="text-xs text-fg-faint mt-1">${nowNextLine}</p>
                ${anchors.bridge_mode ? `<div class="mt-1.5">${badge("Bridge mode on")}</div>` : ""}
              </div>
              <div class="flex items-end gap-3 flex-wrap">
                ${ringCell(offerPct, "var(--color-goal)", offerLabel, "to offer")}
                ${ringCell(cad.weekly_target ? Math.min(100, (cad.week_total / cad.weekly_target) * 100) : 0, "var(--accent)", `${cad.week_total}/${cad.weekly_target}`, "apps / week")}
                ${trackRings}
              </div>
              <div class="flex items-center gap-x-6 gap-y-2 flex-nowrap overflow-x-auto">
                ${countTile(anchors.offer_date ? anchors.offer_days : null, "days to offer", "text-goal")}
                ${countTile(runwayDays, "days of runway", runwayTone)}
                ${countTile(dStretch, anchors.stretch_date ? `to stretch (${shortDate(anchors.stretch_date)})` : "to stretch", "text-fg")}
                <div class="shrink-0"><div class="text-2xl font-semibold nums ${offers ? "text-positive" : "text-fg"}" data-count="${offers}">0</div><div class="text-[11px] text-fg-faint mt-0.5">offer${offers === 1 ? "" : "s"} in hand</div></div>
                ${mods.clips ? `<div class="shrink-0"><div class="text-2xl font-semibold nums text-fg" data-count="${side.posts_mtd}">0</div><div class="text-[11px] text-fg-faint mt-0.5">posts MTD</div></div>` : ""}
                ${mods.side ? `<div class="shrink-0"><div class="text-2xl font-semibold nums text-positive" data-count="${Math.round(side.revenue_mtd)}" data-prefix="$">0</div><div class="text-[11px] text-fg-faint mt-0.5">revenue MTD</div></div>` : ""}
              </div>
            </div>
          </section>

          ${goalsSection}

          <div class="flex items-center justify-between px-1">
            <h2 class="text-sm uppercase tracking-wide text-fg-faint">Overview</h2>
            <button id="edit-layout" class="text-xs text-fg-faint hover:text-fg transition-colors flex items-center gap-1.5">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 20h9M16.5 3.5a2.1 2.1 0 013 3L7 19l-4 1 1-4z"/></svg>
              <span>Edit layout</span></button>
          </div>
          <div id="dash-grid" class="grid grid-cols-4 gap-3 auto-rows-min"></div>
        </div>`;

      // Globe — lazy + deferred to idle so the dashboard content and charts paint
      // before the heavy Three.js parse + WebGL init (572 kB chunk) runs.
      const host = root.querySelector<HTMLElement>("#globe");
      if (host && getPrefs().globe) {
        const loadGlobe = () => import("../globe").then(({ createGlobe }) => {
          if (!host.isConnected) return;
          disposeGlobe = createGlobe(host, { markers: apps.length ? appMarkers(apps) : undefined, home: appHome(apps) });
          requestAnimationFrame(() => host.classList.remove("opacity-0"));
        });
        if ("requestIdleCallback" in window) requestIdleCallback(() => void loadGlobe(), { timeout: 2000 });
        else setTimeout(() => void loadGlobe(), 200);
      }

      // Hero scroll parallax
      const hero = root.querySelector<HTMLElement>("section");
      const onScroll = () => {
        if (matchMedia("(prefers-reduced-motion: reduce)").matches || document.documentElement.classList.contains("no-motion")) return;
        const y = root.scrollTop;
        if (host) host.style.transform = `translateY(${y * 0.3}px) scale(${1 + y * 0.0004})`;
        if (hero) hero.style.opacity = String(Math.max(0, 1 - y / 420));
      };
      root.addEventListener("scroll", onScroll, { passive: true });
      detachScroll = () => root.removeEventListener("scroll", onScroll);

      // Hero count-ups + weekly-target ring
      root.querySelectorAll<HTMLElement>("section [data-count]").forEach((n) =>
        countUp(n, Number(n.dataset.count), { suffix: n.dataset.suffix || "", prefix: n.dataset.prefix || "" }));
      mountRings(root);

      const grid = root.querySelector<HTMLElement>("#dash-grid")!;
      const editBtn = root.querySelector<HTMLButtonElement>("#edit-layout")!;

      function reconcile(): { w: Widget; span: number; hidden: boolean }[] {
        const byId = new Map(registry.map((w) => [w.id, w]));
        const seen = new Set<string>();
        const out: { w: Widget; span: number; hidden: boolean }[] = [];
        for (const p of getPrefs().widgets) {
          const w = byId.get(p.id);
          if (w) { out.push({ w, span: clamp(p.span, w.min, w.max), hidden: p.hidden }); seen.add(p.id); }
        }
        for (const w of registry) if (!seen.has(w.id)) out.push({ w, span: w.span, hidden: false });
        return out;
      }
      function persist(layout: { w: Widget; span: number; hidden: boolean }[]) {
        setPrefs({ widgets: layout.map((l): WidgetPref => ({ id: l.w.id, span: l.span, hidden: l.hidden })) });
      }

      function drawGrid() {
        const layout = reconcile();
        killCharts();
        grid.classList.toggle("editing", editing);
        const cards = layout
          .filter((l) => editing || !l.hidden)
          .map((l) => {
            if (l.hidden) {
              return `<button data-show="${l.w.id}" style="grid-column:span ${l.span}" class="rounded-card border border-dashed border-line-strong text-fg-faint hover:text-fg text-sm py-6 transition-colors">+ ${esc(l.w.title)}</button>`;
            }
            const controls = editing
              ? `<div class="flex items-center gap-1 ml-auto">
                  <button data-span="-1" data-id="${l.w.id}" class="h-6 w-6 grid place-items-center rounded bg-ink-800 hover:bg-ink-700">−</button>
                  <span class="text-[11px] text-fg-faint nums w-8 text-center">${l.span}/4</span>
                  <button data-span="1" data-id="${l.w.id}" class="h-6 w-6 grid place-items-center rounded bg-ink-800 hover:bg-ink-700">+</button>
                  <button data-hide="${l.w.id}" class="h-6 w-6 grid place-items-center rounded bg-ink-800 hover:bg-ink-700 hover:text-danger ml-1">✕</button>
                </div>`
              : "";
            const handle = editing
              ? `<svg class="text-fg-faint cursor-grab shrink-0" width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><circle cx="9" cy="6" r="1.5"/><circle cx="15" cy="6" r="1.5"/><circle cx="9" cy="12" r="1.5"/><circle cx="15" cy="12" r="1.5"/><circle cx="9" cy="18" r="1.5"/><circle cx="15" cy="18" r="1.5"/></svg>`
              : "";
            return `<div data-widget="${l.w.id}" ${editing ? 'draggable="true"' : ""} style="grid-column:span ${l.span}" class="card p-4 ${editing ? "ring-1 ring-line-strong" : ""}">
              <div class="flex items-center gap-2 mb-3">${handle}<div class="text-sm text-fg-muted">${esc(l.w.title)}</div>${controls}</div>
              <div data-body>${l.w.body()}</div></div>`;
          })
          .join("");
        grid.innerHTML = cards;
        // mount widget internals
        for (const l of layout) {
          if (editing || !l.hidden) {
            const el = grid.querySelector<HTMLElement>(`[data-widget="${l.w.id}"] [data-body]`);
            if (el) l.w.mount?.(el);
          }
        }
        wireGrid(layout);
      }

      function wireGrid(layout: { w: Widget; span: number; hidden: boolean }[]) {
        const byId = new Map(layout.map((l) => [l.w.id, l]));
        grid.querySelectorAll<HTMLButtonElement>("[data-span]").forEach((b) =>
          b.addEventListener("click", () => {
            const l = byId.get(b.dataset.id!);
            if (!l) return;
            l.span = clamp(l.span + Number(b.dataset.span), l.w.min, l.w.max);
            persist(layout);
            drawGrid();
          }));
        grid.querySelectorAll<HTMLButtonElement>("[data-hide]").forEach((b) =>
          b.addEventListener("click", () => {
            const l = byId.get(b.dataset.hide!);
            if (l) { l.hidden = true; persist(layout); drawGrid(); }
          }));
        grid.querySelectorAll<HTMLButtonElement>("[data-show]").forEach((b) =>
          b.addEventListener("click", () => {
            const l = byId.get(b.dataset.show!);
            if (l) { l.hidden = false; persist(layout); drawGrid(); }
          }));
        // drag reorder
        let dragId: string | null = null;
        grid.querySelectorAll<HTMLElement>("[data-widget]").forEach((card) => {
          card.addEventListener("dragstart", () => { dragId = card.dataset.widget ?? null; card.classList.add("opacity-40"); });
          card.addEventListener("dragend", () => card.classList.remove("opacity-40"));
          card.addEventListener("dragover", (e) => e.preventDefault());
          card.addEventListener("drop", (e) => {
            e.preventDefault();
            const targetId = card.dataset.widget;
            if (!dragId || !targetId || dragId === targetId) return;
            const from = layout.findIndex((l) => l.w.id === dragId);
            const to = layout.findIndex((l) => l.w.id === targetId);
            const [moved] = layout.splice(from, 1);
            layout.splice(to, 0, moved);
            persist(layout);
            drawGrid();
          });
        });
      }

      editBtn.addEventListener("click", () => {
        editing = !editing;
        editBtn.querySelector("span")!.textContent = editing ? "Done" : "Edit layout";
        editBtn.classList.toggle("text-fg", editing);
        drawGrid();
      });

      drawGrid();
    },
  };
}
