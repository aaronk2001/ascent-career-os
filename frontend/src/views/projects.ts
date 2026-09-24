import { api, tryApi } from "../api";
import { routeParam, type View } from "../router";
import { $, $$, esc, progressBar } from "../ui";

type ShipKey = "repo" | "readme" | "demo" | "bullet" | "portfolio";
type Project = {
  id: string; slug: string; name: string; tier: "core" | "other";
  path: string | null; category: string | null; stack: string | null;
  status: string | null; role: string | null; purpose: string | null;
  repo_url: string | null; demo_url: string | null;
  problem: string | null; built: string | null; result: string | null; pitch: string | null;
  ship: Record<ShipKey, boolean>; ship_done: number; story_filled: number; completeness: number;
};
type Overall = { percent: number; complete_count: number; shipped_count: number; total: number };
type Payload = { core: Project[]; other: Project[]; overall: Overall };
type TextField = "status" | "stack" | "role" | "purpose" | "repo_url" | "problem" | "built" | "result" | "pitch";
type Draft = { problem: string; built: string; result: string; bullet: string };

const SHIP: { key: ShipKey; label: string }[] = [
  { key: "repo", label: "Public GitHub repo" },
  { key: "readme", label: "README with screenshot/GIF" },
  { key: "demo", label: "Demo video / photos" },
  { key: "bullet", label: "Resume bullet with a number" },
  { key: "portfolio", label: "On portfolio site" },
];
const STORY: { key: TextField; label: string; prompt: string; optional?: boolean }[] = [
  { key: "problem", label: "Problem", prompt: "What was broken or missing before this existed?" },
  { key: "built", label: "What I built", prompt: "The system in three sentences — what it does, not how proud you are." },
  { key: "result", label: "Result & numbers", prompt: "What changed. Put a number on it — uptime, latency, hours saved, units shipped." },
  { key: "pitch", label: "30-second pitch (optional)", prompt: "Say it out loud. If it takes longer than 30 seconds, cut it.", optional: true },
];

const FACTS: { key: TextField; label: string }[] = [
  { key: "status", label: "Status" },
  { key: "stack", label: "Stack" },
  { key: "role", label: "My role" },
  { key: "purpose", label: "One-liner" },
  { key: "repo_url", label: "Repo" },
];

type Sort = "closest" | "name" | "status";

export default function projectsView(): View {
  let data: Payload = { core: [], other: [], overall: { percent: 0, complete_count: 0, shipped_count: 0, total: 0 } };
  let openId: string | null = null;
  let sort: Sort = "closest";
  let showOther = false;
  let reviewing = false;
  let reviewIdx = 0;
  let draftMsg = "";
  let drafting = false;
  let bulletSuggestion = "";
  let keyHandler: ((e: KeyboardEvent) => void) | null = null;

  return {
    async render(root) {
      root.innerHTML = `<div class="p-2 text-fg-muted">Loading…</div>`;
      try {
        data = await api<Payload>("/projects");
        const want = routeParam("open");
        openId = want && [...data.core, ...data.other].some((p) => p.id === want) ? want : null;
        draw(root);
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        root.innerHTML = `<div class="space-y-3 p-2">
          <h1 class="text-2xl font-semibold tracking-tight">Projects</h1>
          <div class="card p-5 space-y-2">
            <div class="text-sm text-danger">Couldn't load projects.</div>
            <div class="text-xs text-fg-muted">${esc(msg)}</div>
            <button id="p-retry" class="rounded-lg btn-accent px-3 py-1.5 text-sm w-fit">Retry</button>
          </div></div>`;
        $$(root, "#p-retry").forEach((b) => b.addEventListener("click", () => void this.render(root)));
      }
    },
    cleanup() { if (keyHandler) removeEventListener("keydown", keyHandler); },
  };

  function sorted(rows: Project[]): Project[] {
    const copy = [...rows];
    if (sort === "name") return copy.sort((a, b) => a.name.localeCompare(b.name));
    if (sort === "status") return copy.sort((a, b) => (a.status ?? "").localeCompare(b.status ?? ""));
    return copy.sort((a, b) => b.ship_done - a.ship_done || b.story_filled - a.story_filled || a.name.localeCompare(b.name));
  }

  function card(p: Project): string {
    const pct = ((p.ship_done + p.story_filled) / 8) * 100;
    const tone = p.ship_done === 5 ? "bg-positive" : "bg-brand-500";
    return `
      <div class="card p-4 space-y-3 hover:border-brand-500/40" data-open="${p.id}">
        <div class="flex items-start justify-between gap-2">
          <div class="font-medium">${esc(p.name)}</div>
          <button class="shrink-0 text-[11px] rounded-md border border-line px-1.5 py-0.5 text-fg-muted hover:border-brand-500/40" data-tier="${p.id}" data-to="other" title="Move to Other">core ⇄</button>
        </div>
        <div class="text-xs text-fg-muted">${esc(p.purpose ?? "")}</div>
        <div class="text-[11px] text-fg-faint">${esc(p.stack ?? "")} · ${esc(p.status ?? "")}</div>
        <div class="space-y-1">
          ${progressBar(pct, tone)}
          <div class="text-[11px] text-fg-faint">${p.ship_done}/5 shipped · ${p.story_filled}/3 story</div>
        </div>
      </div>`;
  }

  function detail(p: Project): string {
    return `
      <div class="card p-5 space-y-5">
        <div class="flex items-start justify-between gap-3">
          <div>
            <h2 class="text-lg font-semibold">${esc(p.name)}</h2>
            <div class="text-xs text-fg-faint mt-0.5">${esc(p.path ?? "")}</div>
          </div>
          <div class="flex gap-2">
            <button id="p-draft" class="rounded-lg btn-accent px-3 py-1.5 text-sm" ${drafting ? "disabled" : ""}>Draft with Linda</button>
            <button id="p-close" class="rounded-lg bg-ink-800 hover:bg-ink-700 px-3 py-1.5 text-sm">Close</button>
          </div>
        </div>
        ${draftMsg ? `<div class="text-xs text-fg-muted">${esc(draftMsg)}</div>` : ""}
        ${p.tier === "core" ? `
        <div class="space-y-1.5">
          <div class="text-[11px] uppercase tracking-wide text-fg-faint">Ship checklist — resume · GitHub · portfolio</div>
          ${SHIP.map((s) => `
            <label class="flex items-center gap-2 text-sm">
              <input type="checkbox" data-ship="${s.key}" ${p.ship[s.key] ? "checked" : ""}>
              <span class="${p.ship[s.key] ? "text-fg-muted line-through" : ""}">${s.label}</span>
            </label>`).join("")}
        </div>` : ""}
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          ${FACTS.map((f) => `
            <label class="block space-y-1">
              <span class="text-[11px] uppercase tracking-wide text-fg-faint">${f.label}</span>
              <input class="w-full rounded-lg bg-ink-900 border border-line px-2.5 py-1.5 text-sm"
                     data-field="${f.key}" value="${esc(p[f.key] ?? "")}">
            </label>`).join("")}
        </div>
        ${bulletSuggestion ? `<div class="rounded-lg border border-line p-3 text-sm space-y-1">
          <div class="text-[11px] uppercase tracking-wide text-fg-faint">Suggested resume bullet (copy it, verify the numbers)</div>
          <div>${esc(bulletSuggestion)}</div></div>` : ""}
        <div class="space-y-4">
          ${STORY.map((s) => `
            <label class="block space-y-1">
              <span class="text-sm font-medium">${s.label}</span>
              <textarea rows="3" data-field="${s.key}"
                class="w-full rounded-lg bg-ink-900 border border-line px-2.5 py-2 text-sm leading-relaxed"
                placeholder="${esc(s.prompt)}">${esc(p[s.key] ?? "")}</textarea>
            </label>`).join("")}
        </div>
      </div>`;
  }

  function reviewList(): Project[] { return [...data.core, ...data.other]; }

  function reviewPanel(): string {
    const list = reviewList();
    const p = list[reviewIdx];
    if (!p) return `<div class="card p-5 space-y-2"><div class="text-sm">Review done — ${data.core.length} core, ${data.other.length} other.</div>
      <button id="r-exit" class="rounded-lg bg-ink-800 hover:bg-ink-700 px-3 py-1.5 text-sm w-fit">Close review</button></div>`;
    return `
      <div class="card p-5 space-y-3">
        <div class="flex items-center justify-between text-xs text-fg-faint">
          <span>Review ${reviewIdx + 1} / ${list.length} · currently <b class="text-fg">${p.tier}</b></span>
          <span>C core · O other · ← back · → skip · Esc exit</span>
        </div>
        <div class="text-lg font-semibold">${esc(p.name)}</div>
        <div class="text-xs text-fg-faint">${esc(p.path ?? "")} · ${esc(p.stack ?? "")} · ${esc(p.status ?? "")}</div>
        <div class="text-sm text-fg-muted">${esc(p.purpose ?? "")}</div>
        <div class="flex flex-wrap gap-2">
          <button data-review="core" class="rounded-lg btn-accent px-3 py-1.5 text-sm">Core (C)</button>
          <button data-review="other" class="rounded-lg bg-ink-800 hover:bg-ink-700 px-3 py-1.5 text-sm">Other (O)</button>
          <button data-review="back" class="rounded-lg bg-ink-800 hover:bg-ink-700 px-3 py-1.5 text-sm">← Back</button>
          <button data-review="skip" class="rounded-lg bg-ink-800 hover:bg-ink-700 px-3 py-1.5 text-sm">Skip →</button>
          <button id="r-exit" class="rounded-lg bg-ink-800 hover:bg-ink-700 px-3 py-1.5 text-sm">Exit</button>
        </div>
      </div>`;
  }

  function draw(root: HTMLElement) {
    const open = openId ? [...data.core, ...data.other].find((p) => p.id === openId) : undefined;
    const o = data.overall;

    root.innerHTML = `
      <div class="space-y-4 pb-6">
        <div class="flex items-start justify-between gap-3 px-2">
          <div>
            <h1 class="text-2xl font-semibold tracking-tight">Projects</h1>
            <p class="text-sm text-fg-muted mt-1">Everything you're building, and what you'd say about it in a room.</p>
          </div>
          <div class="flex gap-2">
            <button id="p-review" class="shrink-0 rounded-lg bg-ink-800 hover:bg-ink-700 px-3 py-1.5 text-sm">Review all</button>
            <button id="p-export" class="shrink-0 rounded-lg bg-ink-800 hover:bg-ink-700 px-3 py-1.5 text-sm">Export to PROJECTS.md</button>
          </div>
        </div>

        <div class="card p-5 space-y-2">
          ${progressBar(o.percent)}
          <div class="text-sm font-medium">${o.shipped_count} of ${o.total} core projects fully shipped · ${o.percent}% of stories written</div>
          <div class="text-xs text-fg-faint">Closest to shipped first — finish those before starting new ones.</div>
          <div id="p-export-msg" class="text-xs text-fg-muted"></div>
        </div>

        ${reviewing ? reviewPanel() : ""}

        ${open ? detail(open) : ""}

        <div class="flex items-center gap-2 px-2 text-xs text-fg-muted">
          <span>Sort</span>
          ${(["closest", "name", "status"] as Sort[]).map((s) => `
            <button data-sort="${s}" class="rounded-md border px-2 py-0.5 ${sort === s ? "border-brand-500/40 text-brand-400" : "border-line"}">${s}</button>`).join("")}
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
          ${sorted(data.core).map(card).join("")}
        </div>

        <div class="card p-4 space-y-2">
          <button id="p-toggle-other" class="text-sm font-medium">
            ${showOther ? "▾" : "▸"} Other / dormant (${data.other.length})
          </button>
          ${showOther ? `<div class="divide-y divide-line">
            ${data.other.map((p) => `
              <div class="flex items-center justify-between gap-3 py-2">
                <div class="min-w-0">
                  <div class="text-sm truncate">${esc(p.name)}</div>
                  <div class="text-[11px] text-fg-faint truncate">${esc(p.path ?? "")} · ${esc(p.stack ?? "")}</div>
                </div>
                <button class="shrink-0 rounded-md border border-line px-2 py-0.5 text-xs hover:border-brand-500/40" data-tier="${p.id}" data-to="core" title="Move to Core">⇄ core</button>
              </div>`).join("")}
          </div>` : ""}
        </div>
      </div>`;

    wire(root);
  }

  async function refresh(root: HTMLElement) {
    data = await api<Payload>("/projects");
    draw(root);
  }

  async function reviewAct(root: HTMLElement, act: string) {
    const list = reviewList();
    const p = list[reviewIdx];
    if (act === "back") reviewIdx = Math.max(0, reviewIdx - 1);
    else if (act === "skip") reviewIdx += 1;
    else if (p && (act === "core" || act === "other")) {
      const id = p.id;
      if (p.tier !== act) {
        await tryApi(`/projects/${id}/tier`, { method: "PUT", body: JSON.stringify({ tier: act }) });
        data = await api<Payload>("/projects");
      }
      // re-find by id: the list re-sorts when a tier changes
      reviewIdx = reviewList().findIndex((x) => x.id === id) + 1;
    }
    draw(root);
  }

  function bindKeys(root: HTMLElement) {
    if (keyHandler) removeEventListener("keydown", keyHandler);
    keyHandler = (e: KeyboardEvent) => {
      if (!reviewing || (e.target as HTMLElement).closest("input, textarea")) return;
      const map: Record<string, string> = { c: "core", o: "other", ArrowLeft: "back", ArrowRight: "skip" };
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

  function wire(root: HTMLElement) {
    $$(root, "[data-open]").forEach((b) => b.addEventListener("click", () => {
      openId = b.dataset.open === openId ? null : b.dataset.open ?? null;
      draftMsg = ""; bulletSuggestion = "";
      draw(root);
    }));

    $$(root, "#p-close").forEach((b) => b.addEventListener("click", () => {
      openId = null;
      draftMsg = ""; bulletSuggestion = "";
      draw(root);
    }));

    $$(root, "[data-sort]").forEach((b) => b.addEventListener("click", () => {
      sort = (b.dataset.sort as Sort | undefined) ?? "closest";
      draw(root);
    }));

    $$(root, "#p-toggle-other").forEach((b) => b.addEventListener("click", () => {
      showOther = !showOther;
      draw(root);
    }));

    $$(root, "[data-tier]").forEach((b) => b.addEventListener("click", async (e) => {
      e.stopPropagation();
      const res = await tryApi<Project>(`/projects/${b.dataset.tier}/tier`, {
        method: "PUT", body: JSON.stringify({ tier: b.dataset.to }),
      });
      if (res.ok) await refresh(root);
    }));

    $$<HTMLInputElement>(root, "[data-ship]").forEach((el) => el.addEventListener("change", async () => {
      const p = [...data.core, ...data.other].find((x) => x.id === openId);
      if (!p) return;
      const ship = { ...p.ship, [el.dataset.ship as ShipKey]: el.checked };
      const res = await tryApi<Project>(`/projects/${p.id}`, { method: "PUT", body: JSON.stringify({ ship }) });
      if (res.ok) await refresh(root);
    }));

    $$(root, "#p-draft").forEach((b) => b.addEventListener("click", async () => {
      const pid = openId;
      if (!pid || drafting) return;
      drafting = true;
      draftMsg = "Linda is reading the project files…";
      draw(root);
      const res = await tryApi<Draft>(`/projects/${pid}/draft`, { method: "POST" });
      drafting = false;
      // user switched projects mid-request: drop the draft so blur can't save it into the wrong project
      if (openId !== pid) { draw(root); return; }
      if (!res.ok) { draftMsg = `Draft failed: ${res.error}`; draw(root); return; }
      draftMsg = "Draft filled the empty boxes only — edit, then click away to save.";
      bulletSuggestion = res.data.bullet;
      draw(root);
      (["problem", "built", "result"] as const).forEach((k) => {
        const ta = $<HTMLTextAreaElement>(root, `textarea[data-field="${k}"]`);
        if (ta && !ta.value.trim() && res.data[k]) ta.value = res.data[k];
      });
    }));

    $$(root, "#p-review").forEach((b) => b.addEventListener("click", () => {
      reviewing = true; reviewIdx = 0; bindKeys(root); draw(root);
    }));
    $$(root, "#r-exit").forEach((b) => b.addEventListener("click", () => exitReview(root)));
    $$(root, "[data-review]").forEach((b) => b.addEventListener("click", () => void reviewAct(root, b.dataset.review!)));

    // Autosave one field on blur, then redraw so both bars follow the edit.
    $$<HTMLInputElement | HTMLTextAreaElement>(root, "[data-field]").forEach((el) => {
      const initial = el.value;
      el.addEventListener("blur", async () => {
        const field = el.dataset.field;
        if (!field || !openId || el.value === initial) return;
        const res = await tryApi<Project>(`/projects/${openId}`, {
          method: "PUT", body: JSON.stringify({ [field]: el.value }),
        });
        if (res.ok) await refresh(root);
      });
    });

    $$(root, "#p-export").forEach((b) => b.addEventListener("click", async () => {
      const msg = $(root, "#p-export-msg");
      const res = await tryApi<{ path: string }>("/projects/export", { method: "POST" });
      if (msg) msg.textContent = res.ok ? `Written to ${res.data.path}` : `Export failed: ${res.error}`;
    }));
  }
}
