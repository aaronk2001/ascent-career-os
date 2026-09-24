import { api, tryApi } from "../api";
import type { View } from "../router";
import { $$, esc } from "../ui";
import { ring, mountRings } from "../visuals";

type Resource = { type: string; title: string; url: string };
type Node = {
  id: string; title: string; level: string; skill?: string;
  prereq?: string[]; description?: string; resources?: Resource[];
  state: string; notes?: string | null;
};
type Section = { id: string; title: string; summary?: string; nodes: Node[] };
type Roadmap = { id: string; title: string; description?: string; accent?: string; sections: Section[] };

type Evidence = { label: string; url?: string };
type Skill = { id: string; skill: string; proficiency?: number; target_proficiency?: number; evidence?: string };
type Profile = { id: string; title: string; summary?: string; bucket?: string; required_skills: { skill: string; level: number }[]; certs: string[] };
type Gap = { skill: string; required: number; current: number; gap: number; met: boolean; tracked: boolean; skill_id?: string | null };
type GapResult = { profile: { id: string; title: string; summary?: string; bucket?: string; certs: string[] }; match_pct: number; met: number; total: number; gaps: Gap[] };

const ROADMAP_ID = "robotics-controls";
const STATES = ["available", "in_progress", "mastered"] as const;
const STATE_LABEL: Record<string, string> = { available: "To-do", in_progress: "Doing", mastered: "Done", locked: "Locked" };
const STATE_RING: Record<string, string> = {
  mastered: "border-positive/50", in_progress: "border-brand-500/50",
  available: "border-line", locked: "border-line opacity-60",
};
const LEVEL_TONE: Record<string, string> = {
  beginner: "text-positive border-positive/40", core: "text-brand-300 border-brand-500/40",
  advanced: "text-violet-400 border-violet-400/40",
};
const BUCKET_TONE: Record<string, string> = {
  other: "text-fg-faint border-line", remote: "text-cyan-400 border-cyan-400/40", local: "text-violet-400 border-violet-400/40",
};

const parseEvidence = (s?: string): Evidence[] => {
  try { const v = JSON.parse(s || "[]"); return Array.isArray(v) ? v : []; } catch { return []; }
};

export default function roadmap(): View {
  let rm: Roadmap | undefined;
  let skills: Skill[] = [];
  let profiles: Profile[] = [];
  let activeProfile = "";
  let gap: GapResult | undefined;

  return {
    async render(root) {
      root.innerHTML = `<div class="p-2 text-fg-muted">Loading…</div>`;
      try {
        const [r, sk, pr] = await Promise.all([
          api<Roadmap>(`/roadmaps/${ROADMAP_ID}`),
          api<Skill[]>("/skills").catch(() => [] as Skill[]),
          api<Profile[]>("/jobprofiles").catch(() => [] as Profile[]),
        ]);
        rm = r; skills = sk; profiles = pr;
        activeProfile = pr[0]?.id ?? "";
        if (activeProfile) gap = await api<GapResult>(`/skills/gap-analysis?profile=${encodeURIComponent(activeProfile)}`).catch(() => undefined);
        draw(root);
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        const stale = /404|not found/i.test(msg);
        root.innerHTML = `<div class="space-y-3 p-2">
          <h1 class="text-2xl font-semibold tracking-tight">Roadmap</h1>
          <div class="card p-5 space-y-2">
            <div class="text-sm text-danger">Couldn't load the roadmap.</div>
            <div class="text-xs text-fg-muted">${esc(msg)}</div>
            ${stale ? `<div class="text-xs text-fg-faint">This usually means Ascent is running an older session — fully close and reopen it to pick up the roadmap.</div>` : ""}
            <button id="rm-retry" class="rounded-lg btn-accent px-3 py-1.5 text-sm w-fit">Retry</button>
          </div></div>`;
        $$(root, "#rm-retry").forEach((b) => b.addEventListener("click", () => void this.render(root)));
      }
    },
  };

  function skillMap(): Map<string, Skill> {
    return new Map(skills.map((s) => [s.skill.trim().toLowerCase(), s]));
  }
  function nodeStates(): Map<string, string> {
    const m = new Map<string, string>();
    rm?.sections.forEach((sec) => sec.nodes.forEach((n) => m.set(n.id, n.state)));
    return m;
  }
  function unmetPrereqs(n: Node, states: Map<string, string>): string[] {
    return (n.prereq ?? []).filter((p) => states.get(p) !== "mastered");
  }
  function nodeTitle(id: string): string {
    for (const sec of rm?.sections ?? []) for (const n of sec.nodes) if (n.id === id) return n.title;
    return id;
  }

  // ── job-fit panel ─────────────────────────────────────────────────────────────
  function fitHtml(): string {
    if (!profiles.length) return "";
    const chips = profiles.map((p) =>
      `<button data-profile="${esc(p.id)}" class="rounded-full border px-3 py-1 text-xs transition-colors ${p.id === activeProfile ? "accent-bg text-white border-transparent" : "border-line-strong text-fg-muted hover:text-fg"}">${esc(p.title)}</button>`).join("");
    let panel = "";
    if (gap) {
      const g = gap;
      const tone = g.match_pct >= 70 ? "var(--color-positive)" : g.match_pct >= 40 ? "var(--color-warn)" : "var(--color-danger)";
      const row = (x: Gap) => {
        const lbl = x.met ? `<span class="text-positive">met</span>` : x.tracked ? `<span class="text-warn">+${x.gap}</span>` : `<span class="text-fg-faint">untracked</span>`;
        const act = x.tracked ? "" : `<button data-track="${esc(x.skill)}" data-level="${x.required}" class="text-[11px] accent-text hover:underline shrink-0">track</button>`;
        return `<div class="grid grid-cols-[1fr_auto_auto] items-center gap-3 py-1.5">
          <span class="text-sm truncate">${esc(x.skill)}</span>
          <span class="text-xs nums text-fg-faint w-16 text-right">L${x.current}/${x.required}</span>
          <span class="text-xs w-20 text-right flex items-center justify-end gap-2">${lbl}${act}</span></div>`;
      };
      const certs = g.profile.certs.length
        ? `<div class="mt-3 pt-3 border-t border-line"><div class="text-[11px] uppercase tracking-wide text-fg-faint mb-1.5">Target certs</div>
            <div class="flex flex-wrap gap-1.5">${g.profile.certs.map((c) => `<span class="rounded-md border border-line bg-ink-800/60 px-2 py-0.5 text-[11px] text-fg-muted">${esc(c)}</span>`).join("")}</div></div>` : "";
      panel = `<div class="mt-3 flex flex-col md:flex-row gap-5">
        <div class="flex flex-col items-center gap-2 shrink-0">
          ${ring(g.match_pct, { size: 96, stroke: 9, color: tone, label: `${g.match_pct}%` })}
          <div class="text-xs text-fg-faint">${g.met}/${g.total} skills met</div>
          ${g.profile.bucket ? `<span class="rounded-full border px-2 py-0.5 text-[10px] ${BUCKET_TONE[g.profile.bucket] ?? "text-fg-faint border-line"}">${esc(g.profile.bucket === "local" ? "Local" : g.profile.bucket)}</span>` : ""}
        </div>
        <div class="flex-1 min-w-0">
          ${g.profile.summary ? `<p class="text-sm text-fg-muted mb-2">${esc(g.profile.summary)}</p>` : ""}
          <div class="divide-y divide-line">${g.gaps.map(row).join("")}</div>
          ${certs}
        </div></div>`;
    }
    return `<div class="card p-4">
      <div class="flex items-center justify-between mb-2">
        <h2 class="text-sm font-semibold tracking-tight">Job-ready checklist</h2>
        <span class="text-[11px] text-fg-faint">proficiency vs target role</span>
      </div>
      <div class="flex flex-wrap gap-2">${chips}</div>
      ${panel}</div>`;
  }

  // ── node card ─────────────────────────────────────────────────────────────────
  function nodeHtml(n: Node, states: Map<string, string>, smap: Map<string, Skill>): string {
    const unmet = unmetPrereqs(n, states);
    const eff = n.state === "available" && unmet.length ? "locked" : n.state;
    const levelTone = LEVEL_TONE[n.level] ?? "text-fg-muted border-line";
    const sk = n.skill ? smap.get(n.skill.trim().toLowerCase()) : undefined;
    const ev = parseEvidence(sk?.evidence);
    const evHtml = ev.length
      ? `<div class="mt-2 flex flex-wrap gap-1">${ev.slice(0, 4).map((e) => e.url
          ? `<a href="${esc(e.url)}" target="_blank" class="rounded-md border border-line bg-ink-800/60 px-2 py-0.5 text-[10px] text-fg-muted hover:text-fg transition-colors">${esc(e.label)} ↗</a>`
          : `<span class="rounded-md border border-line bg-ink-800/60 px-2 py-0.5 text-[10px] text-fg-muted">${esc(e.label)}</span>`).join("")}</div>` : "";
    const resHtml = (n.resources ?? []).map((r) =>
      `<a href="${esc(r.url)}" target="_blank" class="flex items-center gap-1.5 text-xs text-fg-muted hover:text-fg transition-colors">
        <span class="text-[10px] uppercase tracking-wide text-fg-faint w-12 shrink-0">${esc(r.type)}</span>
        <span class="truncate">${esc(r.title)} ↗</span></a>`).join("");
    const seg = STATES.map((st) =>
      `<button data-set="${st}" class="px-2 py-0.5 text-[11px] rounded transition-colors ${n.state === st ? "btn-accent" : "bg-ink-800 text-fg-muted hover:text-fg"}">${STATE_LABEL[st]}</button>`).join("");
    const skillTag = sk
      ? `<span class="text-[10px] text-fg-faint">· L${sk.proficiency ?? 0} tracked</span>`
      : n.skill ? `<button data-track="${esc(n.skill)}" data-level="3" class="text-[10px] accent-text hover:underline">+ track skill</button>` : "";

    return `<div class="card p-4 border ${STATE_RING[eff]}" data-node="${esc(n.id)}">
      <div class="flex items-start justify-between gap-2">
        <div class="min-w-0">
          <div class="flex items-center gap-2">
            <span class="text-sm font-medium ${eff === "mastered" ? "text-positive" : ""}">${esc(n.title)}</span>
            ${eff === "mastered" ? '<span class="text-positive text-xs">✓</span>' : ""}
          </div>
          <div class="mt-0.5 flex items-center gap-2">
            <span class="rounded-full border px-1.5 py-0.5 text-[10px] ${levelTone}">${esc(n.level)}</span>
            ${skillTag}
          </div>
        </div>
        ${eff === "locked" ? `<span title="Needs: ${esc(unmet.map(nodeTitle).join(", "))}" class="text-[10px] text-fg-faint shrink-0">🔒 locked</span>` : ""}
      </div>
      ${n.description ? `<p class="mt-2 text-xs text-fg-muted">${esc(n.description)}</p>` : ""}
      ${resHtml ? `<div class="mt-2 space-y-1">${resHtml}</div>` : ""}
      ${evHtml}
      <div class="mt-3 flex items-center gap-1">${seg}</div>
    </div>`;
  }

  function sectionHtml(sec: Section, states: Map<string, string>, smap: Map<string, Skill>): string {
    const mastered = sec.nodes.filter((n) => n.state === "mastered").length;
    const pct = sec.nodes.length ? (mastered / sec.nodes.length) * 100 : 0;
    return `<section class="space-y-3">
      <div class="flex items-center gap-3 px-1">
        ${ring(pct, { size: 44, stroke: 5, label: `${Math.round(pct)}` })}
        <div>
          <h2 class="text-base font-semibold tracking-tight">${esc(sec.title)}</h2>
          ${sec.summary ? `<div class="text-xs text-fg-faint">${esc(sec.summary)} · ${mastered}/${sec.nodes.length} mastered</div>` : ""}
        </div>
      </div>
      <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">${sec.nodes.map((n) => nodeHtml(n, states, smap)).join("")}</div>
    </section>`;
  }

  function draw(root: HTMLElement) {
    if (!rm) return;
    const states = nodeStates();
    const smap = skillMap();
    const allNodes = rm.sections.flatMap((s) => s.nodes);
    const mastered = allNodes.filter((n) => n.state === "mastered").length;
    const overall = allNodes.length ? (mastered / allNodes.length) * 100 : 0;

    root.innerHTML = `
      <div class="space-y-5 pb-6">
        <div class="flex items-center justify-between gap-4 px-2">
          <div><h1 class="text-2xl font-semibold tracking-tight">${esc(rm.title)} Roadmap</h1>
            ${rm.description ? `<p class="text-sm text-fg-muted mt-1 max-w-2xl">${esc(rm.description)}</p>` : ""}</div>
          <div class="flex flex-col items-center shrink-0">${ring(overall, { size: 72, stroke: 7, label: `${Math.round(overall)}%` })}
            <div class="text-[11px] text-fg-faint mt-1">${mastered}/${allNodes.length} mastered</div></div>
        </div>
        ${fitHtml()}
        <div class="space-y-6">${rm.sections.map((sec) => sectionHtml(sec, states, smap)).join("")}</div>
      </div>`;

    mountRings(root);
    wire(root);
  }

  function wire(root: HTMLElement) {
    // profile switch
    $$(root, "[data-profile]").forEach((b) => b.addEventListener("click", async () => {
      activeProfile = b.dataset.profile!;
      gap = await api<GapResult>(`/skills/gap-analysis?profile=${encodeURIComponent(activeProfile)}`).catch(() => undefined);
      draw(root);
    }));

    // node state changes
    $$(root, "[data-node]").forEach((el) => {
      const id = el.dataset.node!;
      const node = rm!.sections.flatMap((s) => s.nodes).find((n) => n.id === id)!;
      $$(el, "[data-set]").forEach((b) => b.addEventListener("click", async () => {
        const state = b.dataset.set!;
        if (state === node.state) return;
        const prev = node.state;
        node.state = state;
        draw(root);
        const r = await tryApi(`/roadmaps/${ROADMAP_ID}/progress/${id}`, { method: "PUT", body: JSON.stringify({ state }) });
        if (!r.ok) { node.state = prev; draw(root); alert(`Could not update: ${r.error}`); return; }
        if (activeProfile) { gap = await api<GapResult>(`/skills/gap-analysis?profile=${encodeURIComponent(activeProfile)}`).catch(() => gap); draw(root); }
      }));
    });

    // track an untracked skill (from a node or a gap row)
    $$(root, "[data-track]").forEach((b) => b.addEventListener("click", async () => {
      const skill = b.dataset.track!;
      const target = Number(b.dataset.level) || 3;
      const r = await tryApi<Skill>("/skills", {
        method: "POST",
        body: JSON.stringify({ skill, priority: "medium", target_proficiency: target, domain: "roadmap" }),
      });
      if (!r.ok) { alert(`Could not track skill: ${r.error}`); return; }
      skills.push(r.data);
      if (activeProfile) gap = await api<GapResult>(`/skills/gap-analysis?profile=${encodeURIComponent(activeProfile)}`).catch(() => gap);
      draw(root);
    }));
  }
}
