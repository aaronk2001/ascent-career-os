import { api } from "../api";
import type { View } from "../router";
import { $$, esc, progressBar } from "../ui";
import { ring, mountRings } from "../visuals";

type Action = { type: string; id: string; title: string; why: string; deep_link: string; impact: number; est: string };
type Focus = {
  profile: { id: string; title: string; match_pct: number; met: number; total: number };
  deadline: string; days_left: number; actions: Action[]; missing_certs: string[];
};
type Profile = { id: string; title: string };

const TYPE_LABEL: Record<string, string> = {
  roadmap_node: "Roadmap", learning_week: "Learning", certification: "Cert", skill: "Skill",
};

export default function focus(): View {
  let profiles: Profile[] = [];
  let active = "controls-engineer";
  let data: Focus | undefined;

  return {
    async render(root) {
      root.innerHTML = `<div class="p-2 text-fg-muted">Loading…</div>`;
      try {
        if (!profiles.length) profiles = await api<Profile[]>("/jobprofiles").catch(() => []);
        if (profiles.length && !profiles.some((p) => p.id === active)) active = profiles[0].id;
        data = await api<Focus>(`/focus?profile=${encodeURIComponent(active)}`);
        draw(root);
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        root.innerHTML = `<div class="space-y-3 p-2">
          <h1 class="text-2xl font-semibold tracking-tight">Focus</h1>
          <div class="card p-5 space-y-2">
            <div class="text-sm text-danger">Couldn't load focus.</div>
            <div class="text-xs text-fg-muted">${esc(msg)}</div>
            <button id="f-retry" class="rounded-lg btn-accent px-3 py-1.5 text-sm w-fit">Retry</button>
          </div></div>`;
        $$(root, "#f-retry").forEach((b) => b.addEventListener("click", () => void this.render(root)));
      }
    },
  };

  function actionCard(a: Action): string {
    return `<div class="card p-4">
      <div class="flex items-start justify-between gap-3">
        <div class="min-w-0">
          <div class="flex items-center gap-2">
            <span class="rounded-full border border-line px-2 py-0.5 text-[10px] text-fg-faint">${esc(TYPE_LABEL[a.type] ?? a.type)}</span>
            <span class="text-sm font-medium">${esc(a.title)}</span>
          </div>
          <p class="mt-1 text-xs text-fg-muted">${esc(a.why)}</p>
        </div>
        <a href="${esc(a.deep_link)}" class="shrink-0 rounded-lg btn-accent px-3 py-1.5 text-xs">Go →</a>
      </div>
      <div class="mt-3 flex items-center gap-3">
        <div class="flex-1">${progressBar(a.impact)}</div>
        <span class="text-[11px] text-fg-faint nums shrink-0">${esc(a.est)}</span>
      </div>
    </div>`;
  }

  function draw(root: HTMLElement) {
    if (!data) return;
    const d = data;
    // compute the countdown client-side with UTC midnights (DST-safe, whole days)
    // so Focus, Dashboard and the Timeline chip always show the same number.
    const [dy, dm, dd] = d.deadline.slice(0, 10).split("-").map(Number);
    const now = new Date();
    const daysLeft = Math.max(0, Math.round((Date.UTC(dy, dm - 1, dd) - Date.UTC(now.getFullYear(), now.getMonth(), now.getDate())) / 86400000));
    const weeks = Math.max(0, Math.round(daysLeft / 7));
    const tone = d.profile.match_pct >= 70 ? "var(--color-positive)"
      : d.profile.match_pct >= 40 ? "var(--color-warn)" : "var(--color-danger)";
    const chips = profiles.map((p) =>
      `<button data-profile="${esc(p.id)}" class="rounded-full border px-3 py-1 text-xs transition-colors ${p.id === active ? "accent-bg text-white border-transparent" : "border-line-strong text-fg-muted hover:text-fg"}">${esc(p.title)}</button>`).join("");
    const missing = d.missing_certs.length
      ? `<div class="card p-4">
          <div class="text-sm text-fg-muted mb-1.5">Target certs not tracked yet</div>
          <div class="flex flex-wrap gap-1.5">${d.missing_certs.map((c) => `<span class="rounded-md border border-line bg-ink-800/60 px-2 py-0.5 text-[11px] text-fg-muted">${esc(c)}</span>`).join("")}</div>
          <a href="#/certs" class="mt-2 inline-block text-xs accent-text hover:underline">Add on Certifications →</a>
        </div>` : "";

    const dl = new Date(d.deadline + "T00:00:00");
    const dlMonthYear = dl.toLocaleDateString(undefined, { month: "long", year: "numeric" });
    const dlFull = dl.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });

    root.innerHTML = `
      <div class="space-y-5 pb-6">
        <div class="px-2">
          <h1 class="text-2xl font-semibold tracking-tight">Focus — next target ${esc(dlMonthYear)}</h1>
          <p class="text-sm text-fg-muted mt-1">Your highest-leverage next moves toward the target role.</p>
        </div>

        <div class="card p-5 flex flex-col md:flex-row items-center gap-6">
          <div class="flex flex-col items-center gap-0.5 shrink-0">
            <div class="text-4xl font-semibold nums">${daysLeft}</div>
            <div class="text-[11px] text-fg-faint">days to ${esc(dlFull)}</div>
            <div class="text-[11px] text-fg-faint nums">~${weeks} weeks left</div>
          </div>
          <div class="flex items-center gap-3 shrink-0">
            ${ring(d.profile.match_pct, { size: 96, stroke: 9, color: tone, label: `${d.profile.match_pct}%` })}
            <div>
              <div class="text-sm font-medium">${esc(d.profile.title)}</div>
              <div class="text-xs text-fg-faint nums">${d.profile.met}/${d.profile.total} skills met</div>
            </div>
          </div>
          <div class="flex-1"></div>
          <div class="flex flex-wrap gap-2 md:justify-end">${chips}</div>
        </div>

        <h2 class="text-sm font-semibold tracking-tight px-2">Do next</h2>
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-3">${d.actions.map(actionCard).join("") || '<div class="card p-8 text-center text-fg-muted">Nothing queued — you\'re on track.</div>'}</div>
        ${missing}
      </div>`;

    mountRings(root);
    wire(root);
  }

  function wire(root: HTMLElement) {
    $$(root, "[data-profile]").forEach((b) => b.addEventListener("click", async () => {
      active = b.dataset.profile!;
      data = await api<Focus>(`/focus?profile=${encodeURIComponent(active)}`).catch(() => data);
      draw(root);
    }));
  }
}
