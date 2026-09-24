import { api, tryApi } from "../api";
import type { View } from "../router";
import { $, $$, esc, progressBar } from "../ui";
import { growBars } from "../motion";
import { routeParam } from "../router";

type Step = { text: string; hours: number; done: boolean };
type HowTo = {
  url?: string | null; prereqs?: string | null; format?: string | null; cost_note?: string | null;
  checked_on?: string | null; study_hours?: number | null; resources?: { label: string; url: string }[] | null;
  booking?: string | null; results_time?: string | null; sources?: string[] | null;
};
type Pace = { state: "no_plan" | "done" | "no_date" | "past" | "on_pace" | "behind"; days_left: number | null; hours_left: number; slot_hours: number };
type Summary = { budget: { active_total: number; before_runway: number; pct_of_budget: number | null }; pace: Record<string, Pace> };

type Cert = {
  id: string;
  provider?: string | null;
  title: string;
  url?: string | null;
  track?: string | null;
  status: string;
  hours?: number | null;
  cost?: string | null;
  category?: string | null;
  time_est?: string | null;
  why?: string | null;
  exam_date?: string | null;
  cost_usd?: number | null;
  verdict?: string | null;
  verdict_reason?: string | null;
  how_to?: HowTo | null;
  steps: Step[];
};

const STATUSES = ["wishlist", "in_progress", "completed", "later", "cut"] as const;
const NEXT: Record<string, string> = { wishlist: "in_progress", in_progress: "completed", completed: "wishlist", later: "in_progress", cut: "wishlist" };

// Phase-sequenced roadmap. `track` holds the phase id.
const PHASES: { id: string; label: string; blurb: string }[] = [
  { id: "phase1", label: "Phase 1 — Now", blurb: "Free / cheap / eligible today. Bank these first — fast wins, no experience gate." },
  { id: "phase2", label: "Phase 2 — Core market value", blurb: "3–12 months. Maps directly to your target JDs and hands-on work." },
  { id: "phase3", label: "Phase 3 — Leadership & safety", blurb: "6–18 months. Management-grade and machine-safety credentials." },
  { id: "phase4", label: "Phase 4 — Gated", blurb: "~1–2 years. Premier credentials needing post-degree experience." },
  { id: "phase5", label: "Phase 5 — Robotics / ML pivot", blurb: "Optional. Only if you target frontier robotics; portfolio > certs." },
  { id: "situational", label: "Situational & Optional", blurb: "Off the main path. Only when the equipment, tool, or role fits." },
  { id: "other", label: "Other — Personal Backlog", blurb: "Certs you were already tracking that sit outside the phased roadmap." },
];
const PHASE_IDS = PHASES.map((p) => p.id);
const PHASE_LABEL: Record<string, string> = Object.fromEntries(PHASES.map((p) => [p.id, p.label]));

const STATUS_DOT: Record<string, string> = { completed: "bg-positive", in_progress: "accent-bg", wishlist: "bg-ink-600", later: "bg-ink-700", cut: "bg-danger" };
const ADVANCE_LABEL: Record<string, string> = { wishlist: "Start", in_progress: "Done", later: "Start" };
const PACE_LABEL: Record<Pace["state"], string> = {
  no_plan: "no study plan", done: "steps done — book it", no_date: "set a date", past: "exam date passed",
  on_pace: "on pace", behind: "behind",
};
const VERDICT_TO_KEY: Record<string, string> = { "KEEP-NOW": "k", LATER: "l", CUT: "x" };

export default function certs(): View {
  let items: Cert[] = [];
  let adding = false;
  let editId: string | null = null;
  let selected: string | null = null;
  let showCut = false;
  let showLater = false;
  let summary: Summary | null = null;
  let reviewing = false;
  let reviewIdx = 0;
  let keyHandler: ((e: KeyboardEvent) => void) | null = null;
  let flash = "";

  return {
    async render(root) {
      root.innerHTML = `<div class="p-2 text-fg-muted">Loading…</div>`;
      [items, summary] = await Promise.all([api<Cert[]>("/certifications"), api<Summary>("/certifications/summary")]);
      const want = routeParam("open");
      selected = want && items.some((c) => c.id === want) ? want : null;
      draw(root);
    },
    cleanup() { if (keyHandler) removeEventListener("keydown", keyHandler); },
  };

  function phaseOf(c: Cert) {
    const t = (c.track || "situational").toLowerCase();
    return PHASE_IDS.includes(t) ? t : "situational";
  }
  function statusOf(c: Cert) {
    return (STATUSES as readonly string[]).includes(c.status) ? c.status : "wishlist";
  }

  function card(c: Cert, showPhase = false): string {
    const sel = c.id === selected;
    const ring = sel ? "ring-1 ring-[color-mix(in_oklab,var(--accent)_60%,transparent)]" : "";
    const bits = showPhase ? [PHASE_LABEL[phaseOf(c)], c.category, c.cost, c.time_est] : [c.category, c.cost, c.time_est];
    const meta = bits.filter(Boolean).map((x) => esc(x)).join(" · ");
    const adv = ADVANCE_LABEL[statusOf(c)]
      ? `<button data-advance="${esc(c.id)}" title="Move to ${esc((NEXT[statusOf(c)] || "").replace("_", " "))}" class="shrink-0 rounded-md bg-ink-800 hover:bg-ink-700 px-2 py-0.5 text-[11px] text-fg-muted hover:text-fg transition-colors">${ADVANCE_LABEL[statusOf(c)]} →</button>`
      : "";
    return `<div data-cert="${esc(c.id)}" class="card card-hover p-3 ${ring}">
      <div class="flex items-start justify-between gap-2">
        <div class="flex items-start gap-2 min-w-0">
          <span class="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${STATUS_DOT[statusOf(c)]}"></span>
          <div class="text-sm font-medium leading-snug min-w-0">${esc(c.title)}</div>
        </div>
        ${adv}
      </div>
      ${meta ? `<div class="mt-1 pl-3.5 text-[11px] text-fg-muted truncate">${meta}</div>` : ""}
      ${statusOf(c) === "in_progress" ? paceLine(c) : ""}
    </div>`;
  }

  function paceLine(c: Cert): string {
    const p = summary?.pace[c.id];
    if (!p) return "";
    const tone = p.state === "behind" || p.state === "past" ? "text-danger" : p.state === "on_pace" ? "text-positive" : "text-fg-muted";
    const days = p.days_left !== null && p.days_left >= 0 ? `${p.days_left} d · ` : "";
    return `<div class="mt-1 pl-3.5 text-[11px] ${tone}">${days}${PACE_LABEL[p.state]}${p.state === "on_pace" || p.state === "behind" ? ` (${p.hours_left} h left / ${p.slot_hours} h of slots)` : ""}</div>`;
  }

  function budgetStrip(): string {
    if (!summary) return "";
    const b = summary.budget;
    const pct = b.pct_of_budget === null ? `<a href="#/settings" class="accent-text">set a cert budget</a>` : `${b.pct_of_budget}% of budget`;
    return `<div class="card p-3 text-xs text-fg-muted nums flex flex-wrap gap-x-4 gap-y-1">
      <span>Active certs: <b class="text-fg">$${b.active_total.toFixed(0)}</b></span>
      <span>Due before runway end: <b class="text-fg">$${b.before_runway.toFixed(0)}</b></span>
      <span>${pct}</span></div>`;
  }

  function bucketSection(status: "later" | "cut", open: boolean, label: string): string {
    const list = items.filter((c) => statusOf(c) === status);
    if (!list.length) return "";
    return `<section class="card p-4 space-y-2">
      <button data-bucket="${status}" class="text-sm font-medium">${open ? "▾" : "▸"} ${label} (${list.length})</button>
      ${open ? `<div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2 items-start">${list.map((c) => card(c, true)).join("")}</div>` : ""}
    </section>`;
  }

  function phaseSection(p: { id: string; label: string; blurb: string }): string {
    // later/cut live in their own buckets; active certs live in the top focus section
    const list = items.filter((c) => phaseOf(c) === p.id && !["later", "cut"].includes(statusOf(c)));
    if (!list.length) return "";
    const done = list.filter((c) => statusOf(c) === "completed").length;
    const active = list.filter((c) => statusOf(c) === "in_progress").length;
    const shown = list.filter((c) => statusOf(c) === "wishlist" || statusOf(c) === "completed");
    const cards = shown.map((c) => card(c)).join("");
    return `<section class="space-y-2">
      <div class="px-1">
        <div class="flex items-baseline justify-between gap-3">
          <h2 class="text-sm font-semibold tracking-tight">${esc(p.label)}</h2>
          <span class="text-[11px] text-fg-faint nums shrink-0">${done}/${list.length}</span>
        </div>
        <div class="mt-1">${progressBar((done / list.length) * 100)}</div>
        <div class="mt-1.5 text-[11px] text-fg-faint">${esc(p.blurb)}${active ? ` · <span class="accent-text">${active} active ↑</span>` : ""}</div>
      </div>
      ${shown.length ? `<div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2 items-start">${cards}</div>` : ""}
    </section>`;
  }

  function activeSection(): string {
    const list = items.filter((c) => statusOf(c) === "in_progress");
    if (!list.length) return "";
    const cards = list.map((c) => card(c, true)).join("");
    return `<section class="space-y-2 rounded-2xl border border-[color-mix(in_oklab,var(--accent)_35%,transparent)] bg-[color-mix(in_oklab,var(--accent)_8%,transparent)] p-3">
      <div class="flex items-baseline justify-between gap-3 px-1">
        <h2 class="text-sm font-semibold tracking-tight accent-text">▸ Working on now</h2>
        <span class="text-[11px] text-fg-faint nums shrink-0">${list.length} active</span>
      </div>
      <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2 items-start">${cards}</div>
    </section>`;
  }

  function nextUp(): string {
    const c = items.find((x) => statusOf(x) === "wishlist"); // items arrive pre-sorted by phase/sort
    if (!c) return "";
    return `<div data-cert="${esc(c.id)}" class="card card-hover p-3 flex items-center gap-3">
      <span class="text-[11px] uppercase tracking-wide text-fg-faint shrink-0">Next up</span>
      <span class="h-1.5 w-1.5 rounded-full ${STATUS_DOT.wishlist} shrink-0"></span>
      <span class="text-sm font-medium min-w-0 truncate flex-1">${esc(c.title)}</span>
      <span class="text-[11px] text-fg-faint shrink-0 hidden sm:inline">${esc(PHASE_LABEL[phaseOf(c)])}</span>
      <button data-advance="${esc(c.id)}" title="Move to in progress" class="shrink-0 rounded-md bg-ink-800 hover:bg-ink-700 px-2 py-0.5 text-[11px] text-fg-muted hover:text-fg transition-colors">Start →</button>
    </div>`;
  }

  function detail(c: Cert): string {
    if (editId === c.id) {
      return `<div class="card p-4 space-y-2" data-id="${esc(c.id)}">
        <input data-e="title" value="${esc(c.title)}" class="w-full bg-ink-800 rounded-lg px-3 py-2 text-sm" placeholder="Title" />
        <div class="flex flex-wrap gap-2">
          <input data-e="category" value="${esc(c.category || "")}" class="flex-1 min-w-32 bg-ink-800 rounded-lg px-3 py-2 text-sm" placeholder="Category" />
          <select data-e="track" class="bg-ink-800 rounded-lg px-2 py-2 text-sm">${PHASES.map((p) => `<option value="${p.id}" ${p.id === phaseOf(c) ? "selected" : ""}>${esc(p.label)}</option>`).join("")}</select>
        </div>
        <div class="flex flex-wrap gap-2">
          <input data-e="cost" value="${esc(c.cost || "")}" class="flex-1 min-w-24 bg-ink-800 rounded-lg px-3 py-2 text-sm" placeholder="Cost" />
          <input data-e="time_est" value="${esc(c.time_est || "")}" class="w-32 bg-ink-800 rounded-lg px-3 py-2 text-sm" placeholder="Time" />
        </div>
        <textarea data-e="why" rows="2" class="w-full bg-ink-800 rounded-lg px-3 py-2 text-sm" placeholder="Why it fits">${esc(c.why || "")}</textarea>
        <input data-e="url" value="${esc(c.url || "")}" class="w-full bg-ink-800 rounded-lg px-3 py-2 text-sm" placeholder="URL" />
        <div class="flex gap-2"><button data-save class="btn-accent rounded-lg px-3 py-1.5 text-sm">Save</button><button data-cancel class="rounded-lg bg-ink-800 hover:bg-ink-700 px-3 py-1.5 text-sm">Cancel</button></div></div>`;
    }
    const meta = [PHASE_LABEL[phaseOf(c)], c.category, c.cost, c.time_est].filter(Boolean).map((x) => esc(x)).join(" · ");
    const title = c.url ? `<a href="${esc(c.url)}" target="_blank" class="hover:text-brand-400">${esc(c.title)}</a>` : esc(c.title);
    return `<div class="card p-4" data-id="${esc(c.id)}">
      <div class="flex items-start justify-between gap-3">
        <div class="min-w-0"><div class="text-base font-medium">${title}</div><div class="mt-1 text-xs text-fg-muted">${meta}</div></div>
        <button data-cycle class="shrink-0 inline-flex items-center gap-1.5 rounded-full bg-ink-800 hover:bg-ink-700 px-2.5 py-1 text-xs"><span class="h-1.5 w-1.5 rounded-full ${STATUS_DOT[statusOf(c)]}"></span>${esc(statusOf(c).replace("_", " "))}</button>
      </div>
      ${c.why ? `<div class="mt-3 text-sm text-fg-muted leading-relaxed">${esc(c.why)}</div>` : ""}
      ${c.verdict_reason ? `<div class="mt-2 text-xs text-fg-faint">Research: ${esc(c.verdict ?? "")} — ${esc(c.verdict_reason)}</div>` : ""}${stepsPanel(c)}${howToPanel(c.how_to)}
      <div class="mt-3 flex items-center gap-3"><span class="flex-1"></span>
        <button data-edit class="text-fg-faint hover:text-fg text-xs">edit</button>
        <button data-del class="text-fg-faint hover:text-danger text-xs">delete</button></div></div>`;
  }

  function howToPanel(h: HowTo | null | undefined): string {
    if (!h) return "";
    const row = (k: string, v: unknown) => `<div class="grid grid-cols-[8rem_1fr] gap-2"><span class="text-fg-faint">${k}</span><span>${v === null || v === undefined || v === "" ? '<span class="text-fg-faint italic">unverified</span>' : esc(String(v))}</span></div>`;
    const links = (h.resources ?? []).map((r) => `<a href="${esc(r.url)}" target="_blank" class="accent-text">${esc(r.label)}</a>`).join(" · ");
    const src = (h.sources ?? []).map((u, i) => `<a href="${esc(u)}" target="_blank" class="accent-text">[${i + 1}]</a>`).join(" ");
    return `<div class="mt-4 space-y-1.5 text-xs">
      <div class="text-[11px] uppercase tracking-wide text-fg-faint">How to get it${h.checked_on ? ` · checked ${esc(h.checked_on)}` : ""}</div>
      ${h.url ? `<a href="${esc(h.url)}" target="_blank" class="accent-text text-sm">Official page →</a>` : ""}
      ${row("Prerequisites", h.prereqs)}${row("Exam format", h.format)}${row("Cost", h.cost_note)}
      ${row("Study hours", h.study_hours)}${row("Booking", h.booking)}${row("Results", h.results_time)}
      ${links ? `<div class="grid grid-cols-[8rem_1fr] gap-2"><span class="text-fg-faint">Resources</span><span>${links}</span></div>` : ""}
      ${src ? `<div class="text-fg-faint">Sources ${src}</div>` : ""}
    </div>`;
  }

  function stepsPanel(c: Cert): string {
    const done = c.steps.filter((s) => s.done).length;
    return `<div class="mt-4 space-y-1.5">
      <div class="flex items-baseline justify-between"><span class="text-[11px] uppercase tracking-wide text-fg-faint">Study plan</span><span class="text-[11px] text-fg-faint nums">${done}/${c.steps.length}</span></div>
      ${c.steps.map((s, i) => `
        <div class="flex items-center gap-2 text-sm">
          <input type="checkbox" data-step-done="${i}" ${s.done ? "checked" : ""}>
          <input data-step-text="${i}" value="${esc(s.text)}" class="flex-1 bg-transparent border-b border-line px-1 py-0.5 text-sm ${s.done ? "line-through text-fg-muted" : ""}">
          <input data-step-hours="${i}" value="${s.hours}" class="w-12 bg-transparent border-b border-line px-1 py-0.5 text-xs nums" title="hours">
          <button data-step-del="${i}" class="text-fg-faint hover:text-danger text-xs">✕</button>
        </div>`).join("")}
      <button data-step-add class="text-xs accent-text">+ add step</button>
      <label class="flex items-center gap-2 text-xs text-fg-muted pt-2">Exam date
        <input type="date" data-exam value="${esc(c.exam_date ?? "")}" class="bg-ink-800 rounded-lg px-2 py-1 text-xs"></label>
    </div>`;
  }

  function reviewPanel(): string {
    const c = items[reviewIdx];
    if (!c) return `<div class="card p-5 space-y-2"><div class="text-sm">Review done.</div><button id="r-exit" class="rounded-lg bg-ink-800 hover:bg-ink-700 px-3 py-1.5 text-sm w-fit">Close review</button></div>`;
    const sugg = c.verdict ? VERDICT_TO_KEY[c.verdict] : undefined;
    const btn = (key: string, act: string, label: string) =>
      `<button data-review="${act}" class="rounded-lg px-3 py-1.5 text-sm ${sugg === key ? "btn-accent" : "bg-ink-800 hover:bg-ink-700"}">${label}</button>`;
    return `<div class="card p-5 space-y-3">
      <div class="flex items-center justify-between text-xs text-fg-faint"><span>Review ${reviewIdx + 1} / ${items.length} · now <b class="text-fg">${esc(statusOf(c).replace("_", " "))}</b></span><span>K keep · L later · X cut · ← back · → skip · Esc</span></div>
      <div class="text-lg font-semibold">${esc(c.title)}</div>
      <div class="text-xs text-fg-muted">${esc([c.cost, c.time_est].filter(Boolean).join(" · "))}</div>
      ${c.verdict ? `<div class="text-sm">Research says <b>${esc(c.verdict)}</b>: ${esc(c.verdict_reason ?? "")}</div>` : `<div class="text-sm text-fg-faint">No research verdict.</div>`}
      <div class="flex flex-wrap gap-2">${btn("k", "keep", "Keep (K)")}${btn("l", "later", "Later (L)")}${btn("x", "cut", "Cut (X)")}
        <button data-review="back" class="rounded-lg bg-ink-800 hover:bg-ink-700 px-3 py-1.5 text-sm">← Back</button>
        <button data-review="skip" class="rounded-lg bg-ink-800 hover:bg-ink-700 px-3 py-1.5 text-sm">Skip →</button>
        <button id="r-exit" class="rounded-lg bg-ink-800 hover:bg-ink-700 px-3 py-1.5 text-sm">Exit</button></div>
    </div>`;
  }

  // items order is fixed during review (no re-sort on update), so reviewIdx stays valid
  async function reviewAct(root: HTMLElement, act: string) {
    const c = items[reviewIdx];
    if (act === "back") { reviewIdx = Math.max(0, reviewIdx - 1); draw(root); return; }
    if (!c) return;
    let status: string | null = null;
    if (act === "keep") status = statusOf(c) === "wishlist" ? "in_progress" : null;
    if (act === "later") status = "later";
    if (act === "cut") status = "cut";
    if (status && status !== statusOf(c)) {
      const rec = await api<Cert>(`/certifications/${c.id}`, { method: "PUT", body: JSON.stringify({ status }) });
      items[reviewIdx] = rec;
      summary = await api<Summary>("/certifications/summary");
    }
    reviewIdx += 1;
    draw(root);
  }

  function bindKeys(root: HTMLElement) {
    if (keyHandler) removeEventListener("keydown", keyHandler);
    keyHandler = (e: KeyboardEvent) => {
      if (!reviewing || (e.target as HTMLElement).closest("input, textarea, select")) return;
      const map: Record<string, string> = { k: "keep", l: "later", x: "cut", ArrowLeft: "back", ArrowRight: "skip" };
      const key = e.key.length === 1 ? e.key.toLowerCase() : e.key;
      if (key === "Escape") exitReview(root);
      else if (map[key]) void reviewAct(root, map[key]);
    };
    addEventListener("keydown", keyHandler);
  }

  function exitReview(root: HTMLElement) {
    reviewing = false;
    if (keyHandler) removeEventListener("keydown", keyHandler);
    keyHandler = null;
    draw(root);
  }

  // A step save lands after focus has moved to the next step input: keep that input's unsaved text and focus.
  function redrawKeepingFocus(root: HTMLElement) {
    const a = document.activeElement;
    const attr = a instanceof HTMLInputElement && root.contains(a)
      ? ["data-step-text", "data-step-hours"].find((n) => a.hasAttribute(n)) : undefined;
    const sel = attr && a instanceof HTMLInputElement ? `[${attr}="${a.getAttribute(attr)}"]` : null;
    const value = a instanceof HTMLInputElement ? a.value : "";
    draw(root);
    const b = sel ? $<HTMLInputElement>(root, sel) : null;
    if (b) { b.value = value; b.focus(); }
  }

  function draw(root: HTMLElement) {
    if (selected && !items.some((c) => c.id === selected)) selected = null;
    const done = items.filter((c) => statusOf(c) === "completed").length;
    const active = items.filter((c) => statusOf(c) === "in_progress").length;
    const sel = items.find((c) => c.id === selected);
    const sections = PHASES.map(phaseSection).filter(Boolean).join("");

    root.innerHTML = `
      <div class="space-y-5 pb-6">
        <div class="flex items-center justify-between px-2">
          <div><h1 class="text-2xl font-semibold tracking-tight">Certifications</h1>
            <div class="text-xs text-fg-faint nums">${items.length} total · ${active} active · ${done} done · click a card to manage</div></div>
          <div class="flex gap-2 shrink-0">
            <button id="c-review" class="rounded-lg bg-ink-800 hover:bg-ink-700 px-3 py-1.5 text-sm">Review all</button>
            <button id="add" class="btn-accent rounded-lg px-3 py-1.5 text-sm">+ Add cert</button>
          </div>
        </div>
        ${flash ? `<div class="mx-2 text-xs text-danger">${esc(flash)}</div>` : ""}
        ${budgetStrip()}
        ${reviewing ? reviewPanel() : ""}
        ${items.length ? `<div class="px-2"><div class="flex items-baseline justify-between mb-1"><span class="text-[11px] text-fg-faint">Overall</span><span class="text-[11px] text-fg-faint nums">${done}/${items.length}</span></div>${progressBar((done / items.length) * 100, "bg-positive")}</div>` : ""}
        ${adding ? `<div class="card p-4 space-y-2">
          <input id="n-title" placeholder="Certification title" class="w-full bg-ink-800 rounded-lg px-3 py-2 text-sm" />
          <div class="flex flex-wrap gap-2">
            <input id="n-category" placeholder="Category" class="flex-1 min-w-32 bg-ink-800 rounded-lg px-3 py-2 text-sm" />
            <select id="n-track" class="bg-ink-800 rounded-lg px-2 py-2 text-sm">${PHASES.map((p) => `<option value="${p.id}">${esc(p.label)}</option>`).join("")}</select>
            <input id="n-cost" placeholder="Cost" class="w-24 bg-ink-800 rounded-lg px-3 py-2 text-sm" />
            <input id="n-time" placeholder="Time" class="w-24 bg-ink-800 rounded-lg px-3 py-2 text-sm" />
            <button id="n-save" class="btn-accent rounded-lg px-3 py-1.5 text-sm">Add</button>
            <button id="n-cancel" class="rounded-lg bg-ink-800 hover:bg-ink-700 px-3 py-1.5 text-sm">Cancel</button>
          </div></div>` : ""}
        ${sel ? detail(sel) : ""}
        ${items.length
          ? `<div class="space-y-6">${activeSection()}${nextUp()}${sections}${bucketSection("later", showLater, "Later — after the offer / employer-funded")}${bucketSection("cut", showCut, "Cut")}</div>`
          : '<div class="card p-8 text-center text-fg-muted">No certifications yet.</div>'}
      </div>`;

    growBars(root);
    wire(root);
  }

  function wire(root: HTMLElement) {
    $(root, "#add")?.addEventListener("click", () => { adding = true; draw(root); });
    $(root, "#c-review")?.addEventListener("click", () => { reviewing = true; reviewIdx = 0; bindKeys(root); draw(root); });
    $$(root, "#r-exit").forEach((b) => b.addEventListener("click", () => exitReview(root)));
    $$(root, "[data-review]").forEach((b) => b.addEventListener("click", () => void reviewAct(root, b.dataset.review!)));
    $$(root, "[data-bucket]").forEach((b) => b.addEventListener("click", () => {
      if (b.dataset.bucket === "later") showLater = !showLater; else showCut = !showCut;
      draw(root);
    }));
    $(root, "#n-cancel")?.addEventListener("click", () => { adding = false; draw(root); });
    $(root, "#n-save")?.addEventListener("click", async () => {
      const title = ($(root, "#n-title") as HTMLInputElement).value.trim();
      if (!title) return;
      const rec = await api<Cert>("/certifications", { method: "POST", body: JSON.stringify({
        title, category: ($(root, "#n-category") as HTMLInputElement).value.trim() || null,
        track: ($(root, "#n-track") as HTMLSelectElement).value,
        cost: ($(root, "#n-cost") as HTMLInputElement).value.trim() || null,
        time_est: ($(root, "#n-time") as HTMLInputElement).value.trim() || null, status: "wishlist",
      }) });
      items.push(rec); adding = false; selected = rec.id; draw(root);
    });

    $$(root, "[data-advance]").forEach((b) => b.addEventListener("click", async (e) => {
      e.stopPropagation();
      const id = b.dataset.advance!;
      const c = items.find((x) => x.id === id);
      if (!c) return;
      const rec = await api<Cert>(`/certifications/${id}`, { method: "PUT", body: JSON.stringify({ status: NEXT[statusOf(c)] ?? "in_progress" }) });
      const i = items.findIndex((x) => x.id === id); if (i >= 0) items[i] = rec;
      draw(root);
    }));

    $$(root, "[data-cert]").forEach((b) => b.addEventListener("click", () => {
      const id = b.dataset.cert!;
      selected = selected === id ? null : id; editId = null; flash = ""; draw(root);
    }));

    const el = $(root, "[data-id]");
    if (el) {
      const id = el.dataset.id!;
      const cert = () => items.find((c) => c.id === id)!;
      const replace = (rec: Cert) => { const i = items.findIndex((c) => c.id === id); if (i >= 0) items[i] = rec; };
      $(el, "[data-cycle]")?.addEventListener("click", async () => {
        replace(await api<Cert>(`/certifications/${id}`, { method: "PUT", body: JSON.stringify({ status: NEXT[statusOf(cert())] ?? "wishlist" }) })); draw(root);
      });
      $(el, "[data-edit]")?.addEventListener("click", () => { editId = id; draw(root); });
      $(el, "[data-cancel]")?.addEventListener("click", () => { editId = null; draw(root); });
      $(el, "[data-save]")?.addEventListener("click", async () => {
        const v = (sel: string) => ($(el, sel) as HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement).value;
        const rec = await api<Cert>(`/certifications/${id}`, { method: "PUT", body: JSON.stringify({
          title: v('[data-e="title"]').trim(), category: v('[data-e="category"]').trim() || null,
          track: v('[data-e="track"]'), cost: v('[data-e="cost"]').trim() || null,
          time_est: v('[data-e="time_est"]').trim() || null, why: v('[data-e="why"]').trim() || null,
          url: v('[data-e="url"]').trim() || null,
        }) });
        replace(rec); editId = null; draw(root);
      });
      $(el, "[data-del]")?.addEventListener("click", async () => {
        const r = await tryApi(`/certifications/${id}`, { method: "DELETE" });
        if (!r.ok) { flash = `Could not delete: ${r.error}`; draw(root); return; }
        items = items.filter((c) => c.id !== id); selected = null; flash = ""; draw(root);
      });

      // Steps are read from the DOM, not state: a change can fire while an earlier step save is
      // still in flight, and the DOM always holds the latest value of every row.
      const domSteps = (): Step[] => $$<HTMLInputElement>(el, "[data-step-text]").map((t) => {
        const i = t.dataset.stepText!;
        return {
          text: t.value,
          hours: Number($<HTMLInputElement>(el, `[data-step-hours="${i}"]`)?.value) || 0,
          done: $<HTMLInputElement>(el, `[data-step-done="${i}"]`)?.checked ?? false,
        };
      });
      const saveSteps = async (steps: Step[]) => {
        replace(await api<Cert>(`/certifications/${id}`, { method: "PUT", body: JSON.stringify({ steps }) }));
        summary = await api<Summary>("/certifications/summary");
        redrawKeepingFocus(root);
      };
      $$<HTMLInputElement>(el, "[data-step-done], [data-step-text], [data-step-hours]").forEach((b) =>
        b.addEventListener("change", () => void saveSteps(domSteps())));
      $$(el, "[data-step-del]").forEach((b) => b.addEventListener("click", () => {
        void saveSteps(domSteps().filter((_, i) => i !== Number(b.dataset.stepDel)));
      }));
      $(el, "[data-step-add]")?.addEventListener("click", () => {
        void saveSteps([...domSteps(), { text: "New step", hours: 1, done: false }]);
      });
      $<HTMLInputElement>(el, "[data-exam]")?.addEventListener("change", async (e) => {
        const v = (e.target as HTMLInputElement).value || null;
        replace(await api<Cert>(`/certifications/${id}`, { method: "PUT", body: JSON.stringify({ exam_date: v }) }));
        summary = await api<Summary>("/certifications/summary");
        redrawKeepingFocus(root);
      });
    }
  }
}
