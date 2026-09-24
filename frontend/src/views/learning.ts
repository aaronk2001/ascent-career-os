import { api } from "../api";
import type { View } from "../router";
import { $, $$, esc } from "../ui";
import { growBars } from "../motion";
import { ring, mountRings } from "../visuals";

type Week = {
  id: number; title: string; status: string; objective?: string;
  vocab?: string[]; can_explain?: string[]; deliverables?: string[];
  primary_resource?: { label: string; url: string };
  objectives_done?: string[]; can_explain_done?: string[];
  hours?: number; notes?: string | null; parked?: boolean;
  sandbox_path?: string; lab_path?: string; scene?: string; est_hours?: number;
};
type Cert = { id: string; title: string; provider?: string | null; status: string; track?: string | null; url?: string | null };
type Track = { id?: string; title?: string; weeks?: Week[]; lab_dir?: string | null };
type TrackMeta = {
  id: string; title: string; schedule: string; category?: string;
  active: boolean; daily_hours: number | null; days: string[] | null; resume_after: string | null;
};

const NEXT: Record<string, string> = { not_started: "in_progress", in_progress: "completed", completed: "not_started" };
const DOT: Record<string, string> = { completed: "bg-positive", in_progress: "bg-brand-500", not_started: "bg-ink-600" };
const CHECK = '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="3"><path d="M5 13l4 4L19 7"/></svg>';

const isParked = (w: Week) => w.parked === true || /^\s*\[parked\]/i.test(w.title);
const cleanTitle = (t: string) => t.replace(/^\s*\[parked\]\s*/i, "");

export default function learning(): View {
  let tracks: TrackMeta[] = [];
  let active = "";
  const cache: Record<string, Track> = {};
  const expanded: Record<string, number> = {};
  let quiz: { deck: string[]; i: number; known: number; flipped: boolean } | null = null;
  let certs: Cert[] = [];
  let defs: Record<string, { def: string; formula?: string | null }> = {};

  return {
    async render(root) {
      await show(root);
    },
  };

  function weeks(): Week[] {
    return cache[active]?.weeks ?? [];
  }
  function pickCurrent(): number {
    const w = weeks().filter((x) => !isParked(x));
    return (w.find((x) => x.status === "in_progress") ?? w.find((x) => x.status !== "completed") ?? w[0])?.id ?? weeks()[0]?.id ?? 0;
  }

  async function show(root: HTMLElement) {
    if (!tracks.length) {
      root.innerHTML = `<div class="p-2 text-fg-muted">Loading…</div>`;
      tracks = await api<TrackMeta[]>("/tracks").catch(() => []);
      if (!active) active = (tracks.find((t) => t.active) ?? tracks[0])?.id ?? "";
    }
    if (active && !cache[active]) {
      root.innerHTML = `<div class="p-2 text-fg-muted">Loading…</div>`;
      cache[active] = await api<Track>(`/tracks/${active}`);
      expanded[active] = pickCurrent();
    }
    if (!certs.length) certs = await api<Cert[]>("/certifications").catch(() => []);
    if (!Object.keys(defs).length) {
      const g = await api<{ terms: { term: string; def: string; formula?: string | null }[] }>("/glossary").catch(() => ({ terms: [] }));
      defs = Object.fromEntries(g.terms.map((t) => [t.term, { def: t.def, formula: t.formula }]));
    }
    draw(root);
  }

  function draw(root: HTMLElement) {
    const w = weeks();
    const activeW = w.filter((x) => !isParked(x));
    const done = activeW.filter((x) => x.status === "completed").length;
    const pct = activeW.length ? (done / activeW.length) * 100 : 0;
    const hours = w.reduce((a, x) => a + (x.hours || 0), 0);
    const untouched = activeW.filter((x) => x.status === "not_started" && !(x.hours || 0)).length;
    const cur = w.find((x) => x.id === expanded[active]) ?? w[0];

    const tab = (t: TrackMeta) =>
      `<button data-tab="${esc(t.id)}" class="rounded-lg px-3 py-1.5 text-sm transition-colors inline-flex items-center gap-1.5 ${active === t.id ? "bg-ink-800 text-fg" : "text-fg-muted hover:text-fg"}">${t.schedule === "flexible" ? '<span class="h-1.5 w-1.5 rounded-full bg-ink-600"></span>' : ""}${esc(t.title)}</button>`;
    const parkedTab = (t: TrackMeta) =>
      `<button data-tab="${esc(t.id)}" class="rounded-lg px-3 py-1.5 text-sm transition-colors inline-flex items-center gap-1.5 opacity-60 ${active === t.id ? "bg-ink-800 text-fg" : "text-fg-muted hover:text-fg"}">${esc(t.title)}<span class="text-[10px] rounded-full bg-ink-800 px-1.5 py-0.5 text-fg-faint">after offer</span></button>`;
    const activeTracks = tracks.filter((t) => t.active);
    const parkedTracks = tracks.filter((t) => !t.active);
    const activeMeta = tracks.find((t) => t.id === active);
    const cadenceLine = activeMeta?.active
      ? `${activeMeta.daily_hours ?? "–"} h/day · ${(activeMeta.days ?? []).join(" ")}`
      : "Parked until a signed offer";

    const steps = w.map((x) => {
      const on = x.id === cur?.id;
      const parked = isParked(x);
      return `<button data-step="${x.id}" class="group flex flex-col items-center gap-1.5 shrink-0 ${parked ? "opacity-45" : ""}">
        <div class="h-2.5 w-2.5 rounded-full ${DOT[x.status] ?? "bg-ink-600"} ${on ? "ring-2 ring-[color-mix(in_oklab,var(--accent)_60%,transparent)]" : ""}"></div>
        <span class="text-[10px] ${on ? "text-fg" : "text-fg-faint"} whitespace-nowrap">W${x.id}</span>
      </button>`;
    }).join('<div class="flex-1 h-px bg-line-strong mt-[5px] min-w-3"></div>');

    root.innerHTML = `
      <div class="space-y-4 pb-6">
        <div class="flex items-center gap-2 px-2 flex-wrap">
          <h1 class="text-2xl font-semibold tracking-tight mr-2">Learning</h1>
          ${activeTracks.map(tab).join("")}
          ${parkedTracks.length ? `<div class="w-px h-5 bg-line-strong mx-1 shrink-0"></div>${parkedTracks.map(parkedTab).join("")}` : ""}
        </div>
        <div class="px-2 text-xs text-fg-faint">${esc(cadenceLine)}</div>

        <div class="card p-4">
          <div class="flex items-center gap-5 mb-4">
            ${ring(pct, { size: 78, stroke: 7, label: `${Math.round(pct)}%` })}
            <div class="grid grid-cols-2 gap-x-8 gap-y-1 flex-1">
              <div><div class="text-xs text-fg-faint">Weeks done</div><div class="text-2xl font-semibold nums">${done}/${activeW.length}</div></div>
              <div><div class="text-xs text-fg-faint">Hours logged</div><div class="text-2xl font-semibold nums">${hours}</div></div>
              ${untouched ? `<div><div class="text-xs text-fg-faint">Untouched</div><div class="text-2xl font-semibold nums text-warn">${untouched}</div></div>` : ""}
            </div>
          </div>
          <div class="mt-1 flex items-center gap-1 overflow-x-auto pb-1">${steps}</div>
        </div>

        ${cur ? weekPanel(cur) : '<div class="card p-8 text-center text-fg-muted">No weeks defined.</div>'}
        ${trackCerts()}
      </div>`;

    wire(root);
  }

  function trackCerts(): string {
    const rel = certs.filter((c) => (c.track || "").toLowerCase() === active || (active === "ml" && (c.track || "").toLowerCase().includes("ml")));
    if (!rel.length) return "";
    const order: Record<string, number> = { in_progress: 0, wishlist: 1, completed: 2 };
    rel.sort((a, b) => (order[a.status] ?? 9) - (order[b.status] ?? 9));
    const rows = rel.slice(0, 8).map((c) => {
      const tone = c.status === "completed" ? "text-positive" : c.status === "in_progress" ? "accent-text" : "text-fg-muted";
      const title = c.url ? `<a href="${esc(c.url)}" target="_blank" class="hover:text-fg">${esc(c.title)}</a>` : esc(c.title);
      return `<div class="flex items-center gap-2 py-1.5 text-sm"><span class="h-1.5 w-1.5 rounded-full ${c.status === "completed" ? "bg-positive" : c.status === "in_progress" ? "accent-bg" : "bg-ink-600"}"></span><span class="flex-1">${title}</span><span class="text-[11px] ${tone}">${esc(c.status.replace("_", " "))}</span></div>`;
    }).join("");
    return `<div class="card p-4"><div class="flex items-center justify-between mb-1"><div class="text-sm text-fg-muted">Certifications for this track</div><a href="#/certs" class="text-xs accent-text hover:underline">All certs →</a></div>${rows}</div>`;
  }

  function checkRow(kind: "deliv" | "explain", text: string, checked: boolean, n?: number): string {
    const num = n == null ? "" :
      `<span class="mt-0.5 w-6 shrink-0 text-right nums text-[11px] ${checked ? "text-fg-faint" : "text-fg-muted"}">${n}.</span>`;
    return `<label data-${kind}="${esc(text)}" class="flex items-start gap-2.5 py-1.5 text-sm">
      ${num}<span class="mt-0.5 grid place-items-center h-4 w-4 rounded border ${checked ? "accent-bg border-transparent" : "border-line-strong"} shrink-0">${checked ? CHECK : ""}</span>
      <span class="${checked ? "text-fg-faint line-through" : ""}">${esc(text)}</span></label>`;
  }

  function weekPanel(wk: Week): string {
    if (quiz) return quizPanel(wk);
    const parked = isParked(wk);
    const delivs = wk.deliverables ?? [];
    const cans = wk.can_explain ?? [];
    const objSet = new Set(wk.objectives_done ?? []);
    const canSet = new Set(wk.can_explain_done ?? []);
    const deliverables = delivs.map((d, i) => checkRow("deliv", d, objSet.has(d), i + 1)).join("");
    const explain = cans.map((e) => checkRow("explain", e, canSet.has(e))).join("");
    const allChecked = delivs.length + cans.length > 0 && delivs.every((d) => objSet.has(d)) && cans.every((e) => canSet.has(e));
    const res = wk.primary_resource;
    const resLink = res
      ? (res.url?.startsWith("http")
          ? `<a href="${esc(res.url)}" target="_blank" class="text-sm accent-text hover:underline">${esc(res.label)} ↗</a>`
          : `<span class="text-sm text-fg-muted">📄 ${esc(res.label)} <span class="text-fg-faint">(${esc(res.url)})</span></span>`)
      : "";
    const vocab = (wk.vocab ?? []).map((v) => {
      const d = defs[v];
      return `<div data-vocab="${esc(v)}" title="Open in glossary" class="rounded-lg bg-ink-800/50 hover:bg-ink-800 border border-line px-3 py-2 transition-colors">
        <div class="flex items-baseline justify-between gap-2">
          <span class="text-sm font-medium">${esc(v)}</span>
          ${d?.formula ? `<code class="shrink-0 rounded-md bg-ink-900 border border-line px-1.5 py-0.5 text-[11px] accent-text font-mono whitespace-nowrap">${esc(d.formula)}</code>` : ""}
        </div>
        <div class="mt-0.5 text-xs ${d ? "text-fg-muted" : "text-fg-faint italic"}">${esc(d?.def || "Definition coming soon")}</div>
      </div>`;
    }).join("");
    const labRow = wk.lab_path ? `<div class="text-xs text-fg-faint">Lab <span class="text-fg-muted">${esc(wk.lab_path)}</span></div>` : "";
    const sceneRow = wk.scene ? `<div class="text-xs text-fg-faint">Factory IO scene <span class="text-fg-muted">${esc(wk.scene)}</span></div>` : "";

    return `<div class="card p-5 space-y-5" data-week="${wk.id}">
      <div class="flex items-start justify-between gap-3">
        <div>
          <div class="text-[11px] uppercase tracking-wide text-fg-faint">Week ${wk.id}${wk.est_hours ? ` · ~${wk.est_hours} h` : ""}${parked ? ' · <span class="text-fg-muted">parked</span>' : ""}</div>
          <h2 class="text-lg font-semibold tracking-tight">${esc(cleanTitle(wk.title))}</h2>
        </div>
        <button data-cycle data-status="${esc(wk.status)}" class="shrink-0 rounded-lg px-3 py-1.5 text-xs ${wk.status === "completed" ? "bg-positive/15 text-positive" : wk.status === "in_progress" ? "accent-bg text-white" : "bg-ink-800 text-fg-muted"}">${esc(wk.status.replace("_", " "))}</button>
      </div>
      ${parked ? '<div class="rounded-lg bg-ink-800/40 border border-line px-3 py-2 text-xs text-fg-muted">Parked — resumes after the offer. Preview only.</div>' : ""}
      ${wk.objective ? `<p class="text-sm text-fg-muted">${esc(wk.objective)}</p>` : ""}

      ${deliverables ? `<div><div class="text-xs uppercase tracking-wide text-fg-faint mb-1">Deliverables</div>${deliverables}</div>` : ""}
      ${explain ? `<div><div class="text-xs uppercase tracking-wide text-fg-faint mb-1.5">You should be able to explain</div>${explain}</div>` : ""}

      ${allChecked && wk.status !== "completed" ? '<button data-complete class="btn-accent rounded-lg px-3 py-1.5 text-sm">Mark week complete ✓</button>' : ""}

      <div>
        <div class="text-xs uppercase tracking-wide text-fg-faint mb-1.5">Notes</div>
        <textarea data-notes rows="2" placeholder="Jot a note for this week…" class="w-full bg-ink-800 rounded-lg px-3 py-2 text-sm resize-y">${esc(wk.notes || "")}</textarea>
        <button data-save-notes class="mt-1 text-xs text-fg-faint hover:text-fg">Save note</button>
      </div>

      <div class="flex flex-wrap items-center gap-4 justify-between">
        <div class="flex flex-wrap items-center gap-4 text-sm">${resLink}${labRow}${sceneRow}</div>
        <div class="flex items-center gap-2">
          <span class="text-xs text-fg-faint">Hours: <span class="text-fg nums">${wk.hours || 0}</span></span>
          <button data-hr="0.5" class="rounded-lg bg-ink-800 hover:bg-ink-700 px-2 py-1 text-xs">+0.5</button>
          <button data-hr="1" class="rounded-lg bg-ink-800 hover:bg-ink-700 px-2 py-1 text-xs">+1</button>
        </div>
      </div>

      ${vocab ? `<div><div class="flex items-center justify-between mb-1.5"><div class="text-xs uppercase tracking-wide text-fg-faint">Vocab (${(wk.vocab ?? []).length})</div><button data-quiz class="text-xs accent-text hover:underline">Quiz me →</button></div><div class="grid grid-cols-1 sm:grid-cols-2 gap-2">${vocab}</div></div>` : ""}
    </div>`;
  }

  function quizPanel(wk: Week): string {
    const q = quiz!;
    if (q.i >= q.deck.length) {
      return `<div class="card p-8 text-center space-y-4" data-week="${wk.id}">
        <div class="text-sm text-fg-faint uppercase tracking-wide">Recall complete</div>
        <div class="text-4xl font-semibold nums accent-text">${q.known}/${q.deck.length}</div>
        <div class="text-sm text-fg-muted">terms you recalled</div>
        <div class="flex gap-2 justify-center"><button data-quiz-again class="btn-accent rounded-lg px-3 py-1.5 text-sm">Again</button><button data-quiz-done class="rounded-lg bg-ink-800 hover:bg-ink-700 px-3 py-1.5 text-sm">Done</button></div>
      </div>`;
    }
    const term = q.deck[q.i];
    return `<div class="card p-8 text-center space-y-5 select-none" data-week="${wk.id}">
      <div class="flex items-center justify-between text-xs text-fg-faint"><span>${q.i + 1} / ${q.deck.length}</span><button data-quiz-done class="hover:text-fg">exit</button></div>
      <div class="py-8">
        <div class="text-2xl font-semibold">${esc(term)}</div>
        ${q.flipped
          ? `<div class="mt-3 max-w-md mx-auto"><div class="text-sm text-fg-muted">${esc(defs[term]?.def || "(no definition yet)")}</div>${defs[term]?.formula ? `<div class="mt-2"><code class="rounded-md bg-ink-800 border border-line px-2 py-0.5 text-xs accent-text font-mono">${esc(defs[term]!.formula!)}</code></div>` : ""}<div class="mt-3"><button data-quiz-glossary class="text-xs accent-text hover:underline">Open in Glossary →</button></div></div>`
          : `<div class="mt-3 text-xs text-fg-faint">Recall it, then flip.</div>`}
      </div>
      ${q.flipped
        ? `<div class="flex gap-2 justify-center"><button data-rate="1" class="btn-accent rounded-lg px-4 py-1.5 text-sm">Got it</button><button data-rate="0" class="rounded-lg bg-ink-800 hover:bg-ink-700 px-4 py-1.5 text-sm">Review again</button></div>`
        : `<button data-flip class="btn-accent rounded-lg px-5 py-2 text-sm">Flip</button>`}
    </div>`;
  }

  async function setStatus(root: HTMLElement, wk: Week, status: string) {
    wk.status = status;
    draw(root);
    await api(`/tracks/${active}/week/${wk.id}`, { method: "PUT", body: JSON.stringify({ status }) }).catch(() => {});
  }

  function wire(root: HTMLElement) {
    $$(root, "[data-tab]").forEach((b) => b.addEventListener("click", () => { active = b.dataset.tab!; quiz = null; void show(root); }));
    $$(root, "[data-step]").forEach((b) => b.addEventListener("click", () => { expanded[active] = Number(b.dataset.step); quiz = null; draw(root); }));
    growBars(root);
    mountRings(root);

    const goGloss = (term: string) => { sessionStorage.setItem("ascent:glossary-q", term); location.hash = "#/glossary"; };
    $$(root, "[data-vocab]").forEach((b) => b.addEventListener("click", () => goGloss(b.dataset.vocab!)));
    $(root, "[data-quiz-glossary]")?.addEventListener("click", () => { if (quiz) goGloss(quiz.deck[quiz.i]); });

    const wk = weeks().find((x) => x.id === expanded[active]);
    if (!wk) return;

    $(root, "[data-cycle]")?.addEventListener("click", () => setStatus(root, wk, NEXT[wk.status] ?? "in_progress"));
    $(root, "[data-complete]")?.addEventListener("click", () => setStatus(root, wk, "completed"));

    $$(root, "[data-deliv]").forEach((el) => el.addEventListener("click", async (e) => {
      e.preventDefault();
      const d = el.dataset.deliv!;
      const set = new Set(wk.objectives_done ?? []);
      set.has(d) ? set.delete(d) : set.add(d);
      wk.objectives_done = [...set];
      draw(root);
      await api(`/tracks/${active}/week/${wk.id}/detail`, { method: "PUT", body: JSON.stringify({ objectives_done: wk.objectives_done }) }).catch(() => {});
    }));

    $$(root, "[data-explain]").forEach((el) => el.addEventListener("click", async (e) => {
      e.preventDefault();
      const x = el.dataset.explain!;
      const set = new Set(wk.can_explain_done ?? []);
      set.has(x) ? set.delete(x) : set.add(x);
      wk.can_explain_done = [...set];
      draw(root);
      await api(`/tracks/${active}/week/${wk.id}/detail`, { method: "PUT", body: JSON.stringify({ can_explain_done: wk.can_explain_done }) }).catch(() => {});
    }));

    $$(root, "[data-hr]").forEach((b) => b.addEventListener("click", async () => {
      wk.hours = Math.round(((wk.hours || 0) + Number(b.dataset.hr)) * 2) / 2;
      draw(root);
      await api(`/tracks/${active}/week/${wk.id}/detail`, { method: "PUT", body: JSON.stringify({ hours: wk.hours }) }).catch(() => {});
    }));

    $(root, "[data-save-notes]")?.addEventListener("click", async () => {
      const ta = $(root, "[data-notes]") as HTMLTextAreaElement | null;
      if (!ta) return;
      wk.notes = ta.value;
      const btn = $(root, "[data-save-notes]");
      if (btn) btn.textContent = "Saved ✓";
      await api(`/tracks/${active}/week/${wk.id}`, { method: "PUT", body: JSON.stringify({ status: wk.status, notes: wk.notes }) }).catch(() => {});
    });

    $(root, "[data-quiz]")?.addEventListener("click", () => { quiz = { deck: [...(wk.vocab ?? [])], i: 0, known: 0, flipped: false }; draw(root); });
    $(root, "[data-flip]")?.addEventListener("click", () => { quiz!.flipped = true; draw(root); });
    $$(root, "[data-rate]").forEach((b) => b.addEventListener("click", () => { if (b.dataset.rate === "1") quiz!.known++; quiz!.i++; quiz!.flipped = false; draw(root); }));
    $(root, "[data-quiz-again]")?.addEventListener("click", () => { quiz = { deck: [...(wk.vocab ?? [])], i: 0, known: 0, flipped: false }; draw(root); });
    $(root, "[data-quiz-done]")?.addEventListener("click", () => { quiz = null; draw(root); });
  }
}
