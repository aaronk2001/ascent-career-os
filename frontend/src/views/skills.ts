import { api, tryApi } from "../api";
import type { View } from "../router";
import { $, $$, esc, progressBar } from "../ui";
import { growBars } from "../motion";
import { accent, accent2 } from "../visuals";

type ChartType = import("chart.js").Chart;

// chart.js (~208KB) is dynamic-imported and registered once on first radar mount
// (mirrors dashboard.ts) so the skill cards paint before the chart lib is parsed.
let _Chart: typeof import("chart.js").Chart | null = null;
async function ensureChart() {
  if (_Chart) return _Chart;
  const m = await import("chart.js");
  m.Chart.register(m.RadarController, m.RadialLinearScale, m.PointElement, m.LineElement, m.Filler, m.Tooltip);
  return (_Chart = m.Chart);
}

type Evidence = { label: string; url?: string; type?: string };
type Skill = {
  id: string; skill: string; priority?: string | null;
  target_hours: number; hours_logged: number; complete: number;
  proficiency?: number; target_proficiency?: number;
  evidence?: string; domain?: string | null;
};

const PRIO_TONE: Record<string, string> = { high: "text-danger border-danger/40", medium: "text-warn border-warn/40", low: "text-fg-muted border-line" };

const parseEvidence = (s?: string): Evidence[] => {
  try { const v = JSON.parse(s || "[]"); return Array.isArray(v) ? v : []; } catch { return []; }
};
const evidenceToText = (e: Evidence[]) => e.map((x) => (x.url ? `${x.label} | ${x.url}` : x.label)).join("\n");
const textToEvidence = (t: string): Evidence[] =>
  t.split("\n").map((l) => l.trim()).filter(Boolean).map((l) => {
    const [label, url] = l.split("|").map((x) => x.trim());
    return url ? { label, url } : { label };
  });
const isStale = (s: Skill) => !s.complete && !s.hours_logged && !(s.proficiency || 0);

function profScale(cur = 0, target = 0): string {
  const segs = [1, 2, 3, 4, 5].map((n) => {
    const filled = n <= cur;
    const tgt = target && n === target;
    return `<span class="h-1.5 w-3.5 rounded-full ${filled ? "bg-brand-500" : "bg-ink-700"} ${tgt ? "ring-1 ring-warn" : ""}"></span>`;
  }).join("");
  const lbl = target ? `${cur}/${target}` : cur ? `${cur}/5` : "—";
  return `<div class="flex items-center gap-1.5" title="Proficiency ${cur}/5${target ? ` · target ${target}` : ""}">
    <div class="flex items-center gap-1">${segs}</div>
    <span class="text-[11px] text-fg-faint nums">L${lbl}</span></div>`;
}

export default function skills(): View {
  let items: Skill[] = [];
  let adding = false;
  let editId: string | null = null;
  let chart: ChartType | undefined;

  return {
    cleanup() { chart?.destroy(); },
    async render(root) {
      root.innerHTML = `<div class="p-2 text-fg-muted">Loading…</div>`;
      items = await api<Skill[]>("/skills");
      draw(root);
    },
  };

  function lvlOpts(sel: number): string {
    return [0, 1, 2, 3, 4, 5].map((n) => `<option value="${n}" ${n === sel ? "selected" : ""}>${n || "—"}</option>`).join("");
  }

  function card(s: Skill): string {
    if (editId === s.id) {
      const ev = parseEvidence(s.evidence);
      return `<div class="card p-4 space-y-2" data-id="${esc(s.id)}">
        <input data-e="skill" value="${esc(s.skill)}" class="w-full bg-ink-800 rounded-lg px-3 py-2 text-sm" />
        <div class="flex flex-wrap gap-2">
          <select data-e="priority" class="bg-ink-800 rounded-lg px-2 py-2 text-sm">${["high", "medium", "low"].map((p) => `<option ${p === (s.priority || "medium") ? "selected" : ""}>${p}</option>`).join("")}</select>
          <input data-e="domain" value="${esc(s.domain ?? "")}" placeholder="domain" class="w-32 bg-ink-800 rounded-lg px-3 py-2 text-sm" />
          <input data-e="target" type="number" min="0" value="${s.target_hours}" class="w-20 bg-ink-800 rounded-lg px-3 py-2 text-sm" placeholder="target h" />
        </div>
        <div class="flex items-center gap-2 text-xs text-fg-muted">
          <label class="flex items-center gap-1">Level <select data-e="prof" class="bg-ink-800 rounded-lg px-2 py-1.5">${lvlOpts(s.proficiency || 0)}</select></label>
          <label class="flex items-center gap-1">Target <select data-e="tprof" class="bg-ink-800 rounded-lg px-2 py-1.5">${lvlOpts(s.target_proficiency || 0)}</select></label>
        </div>
        <textarea data-e="evidence" rows="2" placeholder="Evidence — one per line:  Project X | https://…" class="w-full bg-ink-800 rounded-lg px-3 py-2 text-xs">${esc(evidenceToText(ev))}</textarea>
        <div class="flex gap-2">
          <button data-save class="btn-accent rounded-lg px-3 py-1.5 text-sm">Save</button>
          <button data-cancel class="rounded-lg bg-ink-800 hover:bg-ink-700 px-3 py-1.5 text-sm">Cancel</button>
        </div></div>`;
    }
    const pct = s.target_hours ? (s.hours_logged / s.target_hours) * 100 : (s.complete ? 100 : 0);
    const tone = PRIO_TONE[s.priority || "medium"] ?? PRIO_TONE.medium;
    const ev = parseEvidence(s.evidence);
    const evChips = ev.length
      ? `<div class="mt-2 flex flex-wrap gap-1">${ev.map((e) => e.url
          ? `<a href="${esc(e.url)}" target="_blank" class="rounded-md border border-line bg-ink-800/60 px-2 py-0.5 text-[10px] text-fg-muted hover:text-fg hover:border-line-strong transition-colors">${esc(e.label)} ↗</a>`
          : `<span class="rounded-md border border-line bg-ink-800/60 px-2 py-0.5 text-[10px] text-fg-muted">${esc(e.label)}</span>`).join("")}</div>` : "";
    return `<div class="card card-hover p-4 ${s.complete ? "opacity-70" : ""}" data-id="${esc(s.id)}">
      <div class="flex items-center justify-between gap-2">
        <div class="flex items-center gap-2 min-w-0">
          <span class="text-sm font-medium truncate ${s.complete ? "line-through text-fg-muted" : ""}">${esc(s.skill)}</span>
          ${s.domain ? `<span class="shrink-0 rounded-full border border-line px-2 py-0.5 text-[10px] text-fg-faint">${esc(s.domain)}</span>` : ""}
          ${isStale(s) ? `<span class="shrink-0 rounded-full border border-warn/40 text-warn px-2 py-0.5 text-[10px]">untouched</span>` : ""}
          ${s.priority ? `<span class="shrink-0 rounded-full border px-2 py-0.5 text-[10px] ${tone}">${esc(s.priority)}</span>` : ""}
        </div>
        <div class="text-xs text-fg-muted nums shrink-0">${s.hours_logged}h / ${s.target_hours}h</div>
      </div>
      <div class="mt-2 flex items-center justify-between gap-2">
        ${profScale(s.proficiency || 0, s.target_proficiency || 0)}
        <div class="flex items-center gap-1">
          <button data-prof="-1" class="h-5 w-5 grid place-items-center rounded bg-ink-800 hover:bg-ink-700 text-xs">−</button>
          <button data-prof="1" class="h-5 w-5 grid place-items-center rounded bg-ink-800 hover:bg-ink-700 text-xs">+</button>
        </div>
      </div>
      <div class="mt-2">${progressBar(pct, s.complete ? "bg-positive" : "bg-brand-500")}</div>
      ${evChips}
      <div class="mt-3 flex items-center gap-1.5 flex-wrap">
        <button data-log="1" class="rounded-lg bg-ink-800 hover:bg-ink-700 px-2.5 py-1 text-xs">+1h</button>
        <button data-log="5" class="rounded-lg bg-ink-800 hover:bg-ink-700 px-2.5 py-1 text-xs">+5h</button>
        <button data-complete class="rounded-lg bg-ink-800 hover:bg-ink-700 px-2.5 py-1 text-xs">${s.complete ? "Reopen" : "✓ Done"}</button>
        <span class="flex-1"></span>
        <button data-edit class="text-fg-faint hover:text-fg text-xs">edit</button>
        <button data-del class="text-fg-faint hover:text-danger text-xs">✕</button>
      </div></div>`;
  }

  function gapHtml(): string {
    const gaps = items
      .filter((s) => (s.target_proficiency || 0) > 0 && !s.complete)
      .map((s) => ({ s, gap: (s.target_proficiency || 0) - (s.proficiency || 0) }))
      .filter((g) => g.gap > 0)
      .sort((a, b) => b.gap - a.gap);
    if (!gaps.length) return "";
    const row = ({ s, gap }: { s: Skill; gap: number }) => `<div class="grid grid-cols-[1fr_auto_auto] items-center gap-3 py-1.5">
      <span class="text-sm truncate">${esc(s.skill)}</span>
      ${profScale(s.proficiency || 0, s.target_proficiency || 0)}
      <span class="text-xs nums ${gap >= 3 ? "text-danger" : "text-warn"} w-12 text-right">+${gap} lvl</span></div>`;
    return `<div class="card p-4">
      <div class="flex items-center justify-between mb-2">
        <h2 class="text-sm font-semibold tracking-tight">Gap analysis</h2>
        <span class="text-[11px] text-fg-faint">target − current proficiency</span>
      </div>
      <div class="divide-y divide-line">${gaps.map(row).join("")}</div></div>`;
  }

  function draw(root: HTMLElement) {
    chart?.destroy();
    const profItems = [...items].filter((s) => (s.target_proficiency || 0) > 0).sort((a, b) => (b.target_proficiency || 0) - (a.target_proficiency || 0)).slice(0, 7);
    const hoursItems = [...items].filter((s) => s.target_hours > 0).sort((a, b) => b.target_hours - a.target_hours).slice(0, 7);
    const useProf = profItems.length >= 3;
    const radarItems = useProf ? profItems : hoursItems;
    const total = items.reduce((a, s) => a + s.hours_logged, 0);
    const done = items.filter((s) => s.complete).length;
    const stale = items.filter(isStale).length;

    root.innerHTML = `
      <div class="space-y-4 pb-6">
        <div class="flex items-center justify-between px-2">
          <div><h1 class="text-2xl font-semibold tracking-tight">Skills</h1>
            <div class="text-xs text-fg-faint nums">${items.length} tracked · ${total}h logged · ${done} complete${stale ? ` · <span class="text-warn">${stale} untouched</span>` : ""}</div></div>
          <button id="add" class="btn-accent rounded-lg px-3 py-1.5 text-sm">+ Add skill</button>
        </div>
        ${adding ? `<div class="card p-4">
          <div class="flex flex-wrap gap-2">
            <input id="n-skill" placeholder="Skill name" class="flex-1 min-w-48 bg-ink-800 rounded-lg px-3 py-2 text-sm" />
            <input id="n-domain" placeholder="domain" class="w-32 bg-ink-800 rounded-lg px-3 py-2 text-sm" />
            <select id="n-prio" class="bg-ink-800 rounded-lg px-2 py-2 text-sm">${["high", "medium", "low"].map((p) => `<option ${p === "medium" ? "selected" : ""}>${p}</option>`).join("")}</select>
            <input id="n-target" type="number" min="0" value="20" class="w-20 bg-ink-800 rounded-lg px-3 py-2 text-sm" placeholder="target h" />
            <label class="flex items-center gap-1 text-xs text-fg-muted">Target L<select id="n-tprof" class="bg-ink-800 rounded-lg px-2 py-2 text-sm">${lvlOpts(3)}</select></label>
            <button id="n-save" class="btn-accent rounded-lg px-3 py-1.5 text-sm">Add</button>
            <button id="n-cancel" class="rounded-lg bg-ink-800 hover:bg-ink-700 px-3 py-1.5 text-sm">Cancel</button>
          </div></div>` : ""}
        ${gapHtml()}
        ${radarItems.length >= 3 ? `<div class="card p-4"><div class="text-sm text-fg-muted mb-2">Skill coverage · ${useProf ? "proficiency" : "hours"} (current vs target)</div><canvas id="radar" height="160"></canvas></div>` : ""}
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3">${items.map(card).join("") || '<div class="text-fg-muted px-2 text-sm">No skills tracked.</div>'}</div>
      </div>`;

    growBars(root);
    wire(root);

    const canvas = root.querySelector<HTMLCanvasElement>("#radar");
    if (canvas && radarItems.length >= 3) void mountRadar(canvas, radarItems, useProf);
  }

  async function mountRadar(canvas: HTMLCanvasElement, radarItems: Skill[], useProf: boolean) {
    const Chart = await ensureChart();
    if (!canvas.isConnected) return;  // view swapped out while chart.js loaded
    const cur = (s: Skill) => useProf ? (s.proficiency || 0) : s.hours_logged;
    const tgt = (s: Skill) => useProf ? (s.target_proficiency || 0) : s.target_hours;
    chart?.destroy();
    chart = new Chart(canvas, {
        type: "radar",
        data: {
          labels: radarItems.map((s) => s.skill.length > 16 ? s.skill.slice(0, 15) + "…" : s.skill),
          datasets: [
            { label: "Current", data: radarItems.map(cur), borderColor: accent(), backgroundColor: "color-mix(in oklab, " + accent() + " 28%, transparent)", pointBackgroundColor: accent2() },
            { label: "Target", data: radarItems.map(tgt), borderColor: "color-mix(in oklab, " + accent2() + " 60%, transparent)", borderDash: [4, 4], backgroundColor: "transparent", pointRadius: 0 },
          ],
        },
      options: { plugins: { legend: { display: false } }, scales: { r: { suggestedMin: 0, ...(useProf ? { suggestedMax: 5 } : {}), grid: { color: "#20202f" }, angleLines: { color: "#20202f" }, pointLabels: { color: "#9aa0ba", font: { size: 10 } }, ticks: { display: false } } } },
    });
  }

  function wire(root: HTMLElement) {
    $(root, "#add")?.addEventListener("click", () => { adding = true; draw(root); });
    $(root, "#n-cancel")?.addEventListener("click", () => { adding = false; draw(root); });
    $(root, "#n-save")?.addEventListener("click", async () => {
      const skill = ($(root, "#n-skill") as HTMLInputElement).value.trim();
      if (!skill) return;
      const priority = ($(root, "#n-prio") as HTMLSelectElement).value;
      const domain = ($(root, "#n-domain") as HTMLInputElement).value.trim() || null;
      const target_hours = Number(($(root, "#n-target") as HTMLInputElement).value) || 0;
      const target_proficiency = Number(($(root, "#n-tprof") as HTMLSelectElement).value) || 0;
      const rec = await api<Skill>("/skills", { method: "POST", body: JSON.stringify({ skill, priority, domain, target_hours, target_proficiency }) });
      items.push(rec); adding = false; draw(root);
    });

    $$(root, "[data-id]").forEach((el) => {
      const id = el.dataset.id!;
      const skill = () => items.find((s) => s.id === id)!;
      const replace = (rec: Skill) => { const i = items.findIndex((s) => s.id === id); if (i >= 0) items[i] = rec; };
      const put = (body: object) => api<Skill>(`/skills/${id}`, { method: "PUT", body: JSON.stringify(body) });

      $$(el, "[data-log]").forEach((b) => b.addEventListener("click", async () => {
        replace(await put({ hours: Number(b.dataset.log) })); draw(root);
      }));
      $$(el, "[data-prof]").forEach((b) => b.addEventListener("click", async () => {
        const next = Math.max(0, Math.min(5, (skill().proficiency || 0) + Number(b.dataset.prof)));
        if (next === (skill().proficiency || 0)) return;
        replace(await put({ proficiency: next })); draw(root);
      }));
      $(el, "[data-complete]")?.addEventListener("click", async () => {
        replace(await put({ complete: skill().complete ? 0 : 1 })); draw(root);
      });
      $(el, "[data-edit]")?.addEventListener("click", () => { editId = id; draw(root); });
      $(el, "[data-cancel]")?.addEventListener("click", () => { editId = null; draw(root); });
      $(el, "[data-save]")?.addEventListener("click", async () => {
        const v = (sel: string) => ($(el, sel) as HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement).value;
        const rec = await put({
          skill: v('[data-e="skill"]').trim(),
          priority: v('[data-e="priority"]'),
          domain: v('[data-e="domain"]').trim() || null,
          target_hours: Number(v('[data-e="target"]')) || 0,
          proficiency: Number(v('[data-e="prof"]')) || 0,
          target_proficiency: Number(v('[data-e="tprof"]')) || 0,
          evidence: textToEvidence(v('[data-e="evidence"]')),
        });
        replace(rec); editId = null; draw(root);
      });
      $(el, "[data-del]")?.addEventListener("click", async () => {
        const r = await tryApi(`/skills/${id}`, { method: "DELETE" });
        if (!r.ok) { alert(`Could not delete: ${r.error}`); return; }
        items = items.filter((s) => s.id !== id); draw(root);
      });
    });
  }
}
