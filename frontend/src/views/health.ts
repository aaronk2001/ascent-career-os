import { api, tryApi } from "../api";
import type { View } from "../router";
import { $, $$, esc, progressBar } from "../ui";

type Exercise = { id: string; split: string; name: string; sets: string | null; note: string | null; sort: number };
type HealthDay = {
  id: string; date: string; weight_lb: number | null; split: string | null;
  minutes: number; routine: Record<string, boolean>; note: string | null;
};
type Summary = {
  current: number | null; delta: number | null; avg7: number | null; to_goal: number | null;
  weigh_ins: number; streak_days: number; sessions_week: number; planned_week: number;
  minutes_week: number; routine_pct: number;
  weight_goal: number | null; weight_start: number | null; weight_mode: string;
  goal_date?: string | null;
};
type Gym = { weekday: number; label: string; splits: string[]; exercises: Exercise[] };
type Projection = {
  goal_date: string | null; days_left: number | null; required_delta: number | null;
  required_target: number | null; rate_lb_week: number | null; warnings: string[];
};
type Energy = {
  missing: string[]; bmr: number | null; tdee: number | null; target: number | null;
  activity_factor: number; mode: string; daily_delta: number;
  burned_today: number | null; session_today: number; burned_week: number;
  burn_breakdown: { resting: number; daily: number; session: number } | null;
  projection: Projection; protein_g: number | null;
  height_in: number | null; birth_year: number | null; sex: string | null;
};
type Payload = {
  today: string; summary: Summary; gym: Gym; energy: Energy; day: HealthDay | null; days: HealthDay[];
  routine_items: { key: string; label: string }[]; splits: string[];
};

const SPLIT_LABEL: Record<string, string> = {
  push: "Push", pull: "Pull", legs: "Legs", zone2: "Zone-2 cardio", rest: "Rest day",
};
const CHECK = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"><path d="M5 13l4 4L19 7"/></svg>';

export default function health(): View {
  let d: Payload | undefined;
  let library: Exercise[] = [];
  let editing = "";

  return {
    async render(root) {
      root.innerHTML = `<div class="p-2 text-fg-muted">Loading…</div>`;
      try {
        [d, library] = await Promise.all([api<Payload>("/health"), api<Exercise[]>("/health/workouts")]);
        draw(root);
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        root.innerHTML = `<div class="space-y-3 p-2">
          <h1 class="text-2xl font-semibold tracking-tight">Health</h1>
          <div class="card p-5 space-y-2">
            <div class="text-sm text-danger">Couldn't load health data.</div>
            <div class="text-xs text-fg-muted">${esc(msg)}</div>
            <button id="h-retry" class="rounded-lg btn-accent px-3 py-1.5 text-sm w-fit">Retry</button>
          </div></div>`;
        $$(root, "#h-retry").forEach((b) => b.addEventListener("click", () => void this.render(root)));
      }
    },
  };

  function draw(root: HTMLElement) {
    if (!d) return;
    root.innerHTML = `
      <div class="space-y-4 pb-6">
        <div class="flex items-start justify-between gap-3 px-2">
          <div>
            <h1 class="text-2xl font-semibold tracking-tight">Health</h1>
            <p class="text-sm text-fg-muted mt-1">Weight goal · the gym blocks the schedule already plans · daily routine</p>
          </div>
        </div>
        ${statTiles(d.summary)}
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-3">
          ${todayCard(d)}
          ${routineCard(d)}
        </div>
        ${energyCard(d.energy)}
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-3">
          ${goalCard(d.summary, d.energy)}
          ${trendCard(d.days)}
        </div>
        ${libraryCard()}
      </div>`;
    wire(root);
  }

  function statTiles(s: Summary): string {
    const sign = (n: number) => (n > 0 ? `+${n}` : `${n}`);
    const tile = (label: string, value: string, sub = "", tone = "") =>
      `<div class="card p-4"><div class="text-xs uppercase tracking-wide text-fg-faint">${esc(label)}</div>
        <div class="mt-1 text-3xl font-semibold nums ${tone}">${value}</div>
        ${sub ? `<div class="mt-1 text-[11px] text-fg-faint">${sub}</div>` : ""}</div>`;
    return `<div class="grid grid-cols-2 md:grid-cols-4 gap-3">
      ${tile("Weight", s.current == null ? "—" : `${s.current}<span class="text-sm text-fg-faint"> lb</span>`,
        s.delta == null ? `${s.weigh_ins} weigh-ins` : `${sign(s.delta)} lb since last · 7d avg ${s.avg7 ?? "—"}`)}
      ${tile("To goal", s.to_goal == null ? "—" : `${Math.abs(s.to_goal)}<span class="text-sm text-fg-faint"> lb</span>`,
        s.weight_goal == null ? "Set a target below" : `target ${s.weight_goal} lb · ${esc(s.weight_mode)}`)}
      ${tile("Gym streak", `${s.streak_days}<span class="text-sm text-fg-faint"> d</span>`, `${s.minutes_week} min this week`)}
      ${tile("Sessions", `${s.sessions_week}<span class="text-fg-faint">/${s.planned_week}</span>`, "this week, vs planned")}
    </div>`;
  }

  function todayCard(p: Payload): string {
    const logged = p.day?.minutes ?? 0;
    const rows = p.gym.exercises.map((e) => `<div class="flex items-baseline gap-2 py-1 text-sm">
        <span class="flex-1">${esc(e.name)}</span>
        <span class="nums text-fg-muted shrink-0">${esc(e.sets ?? "")}</span>
      </div>${e.note ? `<div class="text-[11px] text-fg-faint -mt-0.5 pb-1">${esc(e.note)}</div>` : ""}`).join("");
    return `<div class="card p-4 space-y-3">
      <div class="flex items-center justify-between gap-2">
        <div class="text-sm font-medium">Today · ${esc(p.gym.label)}</div>
        ${logged ? `<span class="rounded-full bg-positive/15 text-positive px-2 py-0.5 text-[11px] nums">${logged} min logged</span>` : ""}
      </div>
      ${rows || '<div class="text-sm text-fg-muted">No exercises for this split yet — add some below.</div>'}
      <div class="flex items-center gap-2 pt-1">
        <input data-h-min type="number" min="0" value="${logged || 60}" class="w-24 bg-ink-800 rounded-lg px-3 py-1.5 text-sm nums" />
        <button data-h-log class="rounded-lg btn-accent px-3 py-1.5 text-sm">Log session</button>
        <input data-h-weight type="number" step="0.1" placeholder="Weigh-in lb" value="${p.day?.weight_lb ?? ""}" class="w-32 bg-ink-800 rounded-lg px-3 py-1.5 text-sm nums" />
        <button data-h-weigh class="rounded-lg border border-line px-3 py-1.5 text-sm text-fg-muted hover:text-fg">Save weight</button>
      </div>
    </div>`;
  }

  function routineCard(p: Payload): string {
    const done = p.day?.routine ?? {};
    const rows = p.routine_items.map((it) => {
      const on = !!done[it.key];
      return `<label data-h-routine="${esc(it.key)}" class="flex items-center gap-2.5 py-1.5 text-sm">
        <span class="grid place-items-center h-4 w-4 rounded border shrink-0 ${on ? "accent-bg border-transparent text-white" : "border-line-strong"}">${on ? CHECK : ""}</span>
        <span class="${on ? "text-fg-faint line-through" : ""}">${esc(it.label)}</span></label>`;
    }).join("");
    return `<div class="card p-4 space-y-2">
      <div class="flex items-center justify-between">
        <div class="text-sm font-medium">Daily routine</div>
        <span class="text-[11px] text-fg-faint nums">${p.summary.routine_pct}% last 7 days</span>
      </div>
      ${rows}
    </div>`;
  }

  function energyCard(e: Energy): string {
    const n = (v: number | null) => (v == null ? "—" : v.toLocaleString());
    if (e.missing.length) {
      return `<div class="card p-4 space-y-1">
        <div class="text-sm font-medium">Energy</div>
        <p class="text-sm text-fg-muted">Add ${esc(e.missing.join(", ").replace(/_/g, " "))} below and this fills in
          — BMR needs height, age and sex, and the target needs a weigh-in.</p>
      </div>`;
    }
    const b = e.burn_breakdown;
    const verb = e.mode === "cut" ? `−${e.daily_delta} cut` : e.mode === "bulk" ? `+${e.daily_delta} bulk` : "maintain";
    const tile = (label: string, value: string, sub: string) =>
      `<div><div class="text-xs uppercase tracking-wide text-fg-faint">${esc(label)}</div>
        <div class="mt-1 text-2xl font-semibold nums">${value}</div>
        <div class="text-[11px] text-fg-faint">${esc(sub)}</div></div>`;
    return `<div class="card p-4 space-y-3">
      <div class="flex items-center justify-between">
        <div class="text-sm font-medium">Energy</div>
        <span class="text-[11px] text-fg-faint nums">lightly active ×${e.activity_factor}</span>
      </div>
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
        ${tile("BMR", n(e.bmr), "resting")}
        ${tile("TDEE", n(e.tdee), `×${e.activity_factor}`)}
        ${tile("Target", n(e.target), verb)}
        ${tile("Burned today", n(e.burned_today), b
          ? `${n(b.resting)} resting + ${n(b.daily)} daily + ${n(b.session)} session`
          : `${n(e.burned_week)} session kcal this week`)}
      </div>
      ${projectionRow(e)}
      ${e.projection.warnings.map((w) => `<div class="rounded-lg border border-warn/40 bg-warn/5 px-3 py-2 text-xs text-warn">${esc(w)}</div>`).join("")}
      <div class="text-xs text-fg-muted">Protein ${n(e.protein_g)} g/day · burn is measured, the target is not —
        it uses a flat ×${e.activity_factor}, so a rest day still shows ${n(e.target)}.</div>
    </div>`;
  }

  function projectionRow(e: Energy): string {
    const p = e.projection;
    if (p.required_delta == null) return "";
    const sign = p.required_delta > 0 ? "+" : "−";
    return `<div class="rounded-lg bg-ink-800/40 border border-line px-3 py-2 text-sm flex flex-wrap gap-x-5 gap-y-1">
      <span class="text-fg-muted">To hit goal by <span class="text-fg nums">${esc(p.goal_date ?? "")}</span></span>
      <span class="nums">${p.days_left} days left</span>
      <span class="nums">${sign}${Math.abs(p.required_delta).toLocaleString()} kcal/day</span>
      <span class="nums">eat ${(p.required_target ?? 0).toLocaleString()}</span>
      <span class="nums">${p.rate_lb_week} lb/week</span>
    </div>`;
  }

  function goalCard(s: Summary, e: Energy): string {
    let pct = 0;
    if (s.weight_goal != null && s.weight_start != null && s.current != null) {
      const total = Math.abs(s.weight_start - s.weight_goal);
      pct = total ? Math.max(0, Math.min(100, (Math.abs(s.weight_start - s.current) / total) * 100)) : 0;
    }
    return `<div class="card p-4 space-y-3">
      <div class="text-sm font-medium">Weight goal</div>
      ${s.weight_goal != null && s.weight_start != null
        ? `<div><div class="flex items-center justify-between text-xs text-fg-muted mb-1">
             <span>${s.weight_start} → ${s.weight_goal} lb</span><span class="nums">${Math.round(pct)}%</span></div>
           ${progressBar(pct)}</div>`
        : '<p class="text-sm text-fg-muted">Set a start and target weight to track progress.</p>'}
      <div class="grid grid-cols-3 gap-2">
        <input data-g-start type="number" step="0.1" placeholder="Start lb" value="${s.weight_start ?? ""}" class="bg-ink-800 rounded-lg px-3 py-1.5 text-sm nums" />
        <input data-g-goal type="number" step="0.1" placeholder="Target lb" value="${s.weight_goal ?? ""}" class="bg-ink-800 rounded-lg px-3 py-1.5 text-sm nums" />
        <select data-g-mode class="bg-ink-800 rounded-lg px-3 py-1.5 text-sm">
          ${["cut", "bulk", "maintain"].map((m) => `<option value="${m}"${s.weight_mode === m ? " selected" : ""}>${m}</option>`).join("")}
        </select>
        <input data-g-height type="number" placeholder="Height in" value="${e.height_in ?? ""}" class="bg-ink-800 rounded-lg px-3 py-1.5 text-sm nums" />
        <input data-g-year type="number" placeholder="Birth year" value="${e.birth_year ?? ""}" class="bg-ink-800 rounded-lg px-3 py-1.5 text-sm nums" />
        <select data-g-sex class="bg-ink-800 rounded-lg px-3 py-1.5 text-sm">
          <option value=""${e.sex ? "" : " selected"}>Sex (for BMR)</option>
          ${["male", "female"].map((x) => `<option value="${x}"${e.sex === x ? " selected" : ""}>${x}</option>`).join("")}
        </select>
        <label class="col-span-3 flex items-center gap-2 text-xs text-fg-muted">
          Goal date
          <input data-g-date type="date" value="${esc(s.goal_date ?? "")}" class="bg-ink-800 rounded-lg px-3 py-1.5 text-sm" />
          <span class="text-fg-faint">drives the daily number below</span>
        </label>
        <label class="col-span-3 flex items-center gap-2 text-xs text-fg-muted">
          ${e.mode === "bulk" ? "Daily surplus" : e.mode === "cut" ? "Daily deficit" : "Daily delta (unused in maintain)"}
          <input data-g-delta type="number" step="50" value="${e.daily_delta}" class="w-24 bg-ink-800 rounded-lg px-3 py-1.5 text-sm nums" />
          <span class="text-fg-faint">kcal</span>
        </label>
      </div>
      <button data-g-save class="rounded-lg btn-accent px-3 py-1.5 text-sm w-fit">Save goal</button>
    </div>`;
  }

  function trendCard(days: HealthDay[]): string {
    const pts = days.filter((x) => x.weight_lb != null)
      .map((x) => ({ date: x.date, w: x.weight_lb as number }))
      .sort((a, b) => a.date.localeCompare(b.date));
    return `<div class="card p-4 space-y-2">
      <div class="text-sm font-medium">Weight trend</div>
      ${sparkline(pts.map((p) => p.w))}
      ${pts.length ? `<div class="flex justify-between text-[11px] text-fg-faint nums"><span>${esc(pts[0].date)}</span><span>${esc(pts[pts.length - 1].date)}</span></div>` : ""}
    </div>`;
  }

  function sparkline(values: number[]): string {
    if (values.length < 2) return `<div class="h-[60px] grid place-items-center text-[11px] text-fg-faint">Log two weigh-ins to see a trend</div>`;
    const w = 200, h = 60, pad = 4;
    const min = Math.min(...values), max = Math.max(...values);
    const range = max - min || 1;
    const step = (w - pad * 2) / (values.length - 1);
    const points = values.map((v, i) =>
      `${(pad + i * step).toFixed(1)},${(h - pad - ((v - min) / range) * (h - pad * 2)).toFixed(1)}`).join(" ");
    return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" class="block w-full" style="height:${h}px">
      <polyline points="${points}" fill="none" stroke="var(--accent)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>`;
  }

  function libraryCard(): string {
    const splits = [...new Set([...Object.keys(SPLIT_LABEL), ...library.map((e) => e.split)])];
    const groups = splits.map((sp) => {
      const rows = library.filter((e) => e.split === sp).map((e) => e.id === editing ? editRow(e) : readRow(e)).join("");
      return `<div class="space-y-1">
        <div class="text-xs uppercase tracking-wide text-fg-faint">${esc(SPLIT_LABEL[sp] ?? sp)}</div>
        ${rows || '<div class="text-xs text-fg-faint py-1">Nothing here yet.</div>'}
        <div class="flex gap-2 pt-1">
          <input data-n-name="${esc(sp)}" type="text" placeholder="Exercise" class="flex-1 bg-ink-800 rounded-lg px-3 py-1.5 text-sm" />
          <input data-n-sets="${esc(sp)}" type="text" placeholder="4x8" class="w-24 bg-ink-800 rounded-lg px-3 py-1.5 text-sm" />
          <button data-n-add="${esc(sp)}" class="rounded-lg border border-line px-3 py-1.5 text-sm text-fg-muted hover:text-fg">Add</button>
        </div>
      </div>`;
    }).join("");
    return `<div class="card p-4 space-y-4">
      <div class="text-sm font-medium">Workout library</div>
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-x-6 gap-y-4">${groups}</div>
    </div>`;
  }

  function readRow(e: Exercise): string {
    return `<div class="flex items-baseline gap-2 py-1 text-sm border-b border-line/60">
      <span class="flex-1">${esc(e.name)}${e.note ? `<span class="block text-[11px] text-fg-faint">${esc(e.note)}</span>` : ""}</span>
      <span class="nums text-fg-muted shrink-0">${esc(e.sets ?? "")}</span>
      <button data-e-edit="${esc(e.id)}" class="text-fg-faint hover:text-fg text-xs shrink-0">edit</button>
      <button data-e-del="${esc(e.id)}" class="text-fg-faint hover:text-danger text-xs shrink-0">✕</button>
    </div>`;
  }

  function editRow(e: Exercise): string {
    return `<div class="space-y-1 py-1 border-b border-line/60">
      <div class="flex gap-2">
        <input data-e-name type="text" value="${esc(e.name)}" class="flex-1 bg-ink-800 rounded-lg px-3 py-1.5 text-sm" />
        <input data-e-sets type="text" value="${esc(e.sets ?? "")}" class="w-24 bg-ink-800 rounded-lg px-3 py-1.5 text-sm" />
      </div>
      <input data-e-note type="text" value="${esc(e.note ?? "")}" placeholder="Cue / progression" class="w-full bg-ink-800 rounded-lg px-3 py-1.5 text-sm" />
      <div class="flex gap-2">
        <button data-e-save="${esc(e.id)}" class="rounded-lg btn-accent px-3 py-1 text-xs">Save</button>
        <button data-e-cancel class="rounded-lg border border-line px-3 py-1 text-xs text-fg-muted hover:text-fg">Cancel</button>
      </div>
    </div>`;
  }

  async function refresh(root: HTMLElement) {
    const [p, lib] = await Promise.all([
      api<Payload>("/health").catch(() => d),
      api<Exercise[]>("/health/workouts").catch(() => library),
    ]);
    if (p) d = p;
    if (lib) library = lib;
    draw(root);
  }

  async function putDay(root: HTMLElement, patch: Record<string, unknown>) {
    if (!d) return;
    const r = await tryApi(`/health/${d.today}`, { method: "PUT", body: JSON.stringify(patch) });
    if (!r.ok) { alert(`Could not save: ${r.error}`); return; }
    await refresh(root);
  }

  function wire(root: HTMLElement) {
    $(root, "[data-h-log]")?.addEventListener("click", () => {
      const min = Number(($(root, "[data-h-min]") as HTMLInputElement).value) || 0;
      void putDay(root, { minutes: min, split: d?.gym.splits[0] ?? null });
    });
    $(root, "[data-h-weigh]")?.addEventListener("click", () => {
      const v = ($(root, "[data-h-weight]") as HTMLInputElement).value;
      void putDay(root, { weight_lb: v === "" ? null : Number(v) });
    });
    $$(root, "[data-h-routine]").forEach((el) => el.addEventListener("click", (ev) => {
      ev.preventDefault();
      const key = el.dataset.hRoutine!;
      const cur = { ...(d?.day?.routine ?? {}) };
      cur[key] = !cur[key];
      void putDay(root, { routine: cur });
    }));

    $(root, "[data-g-save]")?.addEventListener("click", async () => {
      const num = (sel: string) => {
        const v = ($(root, sel) as HTMLInputElement).value;
        return v === "" ? null : Number(v);
      };
      const r = await tryApi("/health/goal", {
        method: "PUT",
        body: JSON.stringify({
          weight_start: num("[data-g-start]"), weight_goal: num("[data-g-goal]"),
          weight_mode: ($(root, "[data-g-mode]") as HTMLSelectElement).value,
          height_in: num("[data-g-height]"), birth_year: num("[data-g-year]"),
          sex: ($(root, "[data-g-sex]") as HTMLSelectElement).value || null,
          daily_delta: num("[data-g-delta]") ?? 0,
          goal_date: ($(root, "[data-g-date]") as HTMLInputElement).value || null,
        }),
      });
      if (!r.ok) { alert(`Could not save goal: ${r.error}`); return; }
      await refresh(root);
    });

    $$(root, "[data-e-edit]").forEach((b) => b.addEventListener("click", () => { editing = b.dataset.eEdit!; draw(root); }));
    $(root, "[data-e-cancel]")?.addEventListener("click", () => { editing = ""; draw(root); });
    $$(root, "[data-e-save]").forEach((b) => b.addEventListener("click", async () => {
      const body = {
        name: ($(root, "[data-e-name]") as HTMLInputElement).value.trim(),
        sets: ($(root, "[data-e-sets]") as HTMLInputElement).value.trim(),
        note: ($(root, "[data-e-note]") as HTMLInputElement).value.trim(),
      };
      const r = await tryApi(`/health/workouts/${b.dataset.eSave}`, { method: "PUT", body: JSON.stringify(body) });
      if (!r.ok) { alert(`Could not save exercise: ${r.error}`); return; }
      editing = "";
      await refresh(root);
    }));
    $$(root, "[data-e-del]").forEach((b) => b.addEventListener("click", async () => {
      const r = await tryApi(`/health/workouts/${b.dataset.eDel}`, { method: "DELETE" });
      if (!r.ok) { alert(`Could not delete: ${r.error}`); return; }
      await refresh(root);
    }));
    $$(root, "[data-n-add]").forEach((b) => b.addEventListener("click", async () => {
      const sp = b.dataset.nAdd!;
      const name = ($(root, `[data-n-name="${sp}"]`) as HTMLInputElement).value.trim();
      if (!name) return;
      const sets = ($(root, `[data-n-sets="${sp}"]`) as HTMLInputElement).value.trim();
      const r = await tryApi("/health/workouts", {
        method: "POST",
        body: JSON.stringify({ split: sp, name, sets, sort: library.filter((e) => e.split === sp).length }),
      });
      if (!r.ok) { alert(`Could not add exercise: ${r.error}`); return; }
      await refresh(root);
    }));
  }
}
