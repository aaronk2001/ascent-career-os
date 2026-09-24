import { api } from "../api";
import type { View } from "../router";
import { $, $$, esc } from "../ui";

type Entry = { term: string; def: string; domain: string; formula?: string | null };

const DOMAINS: { id: string; label: string; dot: string }[] = [
  { id: "controls", label: "Controls", dot: "bg-brand-500" },
  { id: "ml", label: "ML / CV", dot: "bg-violet-500" },
  { id: "electrical", label: "Electrical", dot: "bg-warn" },
  { id: "mechanical", label: "Mechanical", dot: "bg-positive" },
  { id: "mechanisms", label: "Mechanisms", dot: "bg-cyan-400" },
  { id: "general", label: "General", dot: "bg-fg-muted" },
];
const LABEL: Record<string, string> = Object.fromEntries(DOMAINS.map((d) => [d.id, d.label]));
const DOT: Record<string, string> = Object.fromEntries(DOMAINS.map((d) => [d.id, d.dot]));

export default function glossary(): View {
  let entries: Entry[] = [];
  let q = "";
  let domain = "all";

  return {
    async render(root) {
      root.innerHTML = `<div class="p-2 text-fg-muted">Loading…</div>`;
      entries = (await api<{ terms: Entry[] }>("/glossary")).terms;
      entries.sort((a, b) => a.term.localeCompare(b.term));
      const seed = sessionStorage.getItem("ascent:glossary-q");
      if (seed) { q = seed; sessionStorage.removeItem("ascent:glossary-q"); }
      draw(root);
    },
  };

  function entryCard(e: Entry): string {
    return `<div class="card p-3">
      <div class="flex items-baseline justify-between gap-3">
        <span class="text-sm font-medium">${esc(e.term)}</span>
        ${e.formula ? `<code class="shrink-0 rounded-md bg-ink-800 border border-line px-2 py-0.5 text-xs accent-text font-mono whitespace-nowrap">${esc(e.formula)}</code>` : ""}
      </div>
      <div class="mt-1 text-xs text-fg-muted">${esc(e.def)}</div>
    </div>`;
  }

  function draw(root: HTMLElement) {
    const ql = q.toLowerCase();
    const filtered = entries.filter((e) =>
      (domain === "all" || e.domain === domain) &&
      (!ql || e.term.toLowerCase().includes(ql) || e.def.toLowerCase().includes(ql) || (e.formula || "").toLowerCase().includes(ql)));

    const order = DOMAINS.map((d) => d.id);
    const groups = new Map<string, Entry[]>();
    for (const e of filtered) (groups.get(e.domain) ?? groups.set(e.domain, []).get(e.domain)!).push(e);
    const sections = order.filter((d) => groups.has(d)).map((d) =>
      `<div class="space-y-2">
        <div class="px-1 text-xs uppercase tracking-wide text-fg-faint flex items-center gap-2"><span class="h-2 w-2 rounded-full ${DOT[d]}"></span>${esc(LABEL[d] ?? d)} <span class="nums text-fg-faint">${groups.get(d)!.length}</span></div>
        <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2.5">${groups.get(d)!.map(entryCard).join("")}</div>
      </div>`).join("");

    const chip = (id: string, label: string) =>
      `<button data-domain="${id}" class="rounded-full border px-3 py-1 text-xs transition-colors ${domain === id ? "accent-bg text-white border-transparent" : "border-line-strong text-fg-muted hover:text-fg"}">${esc(label)}</button>`;

    root.innerHTML = `
      <div class="space-y-4 pb-6">
        <div class="px-2">
          <h1 class="text-2xl font-semibold tracking-tight">Glossary</h1>
          <div class="text-xs text-fg-faint nums">${entries.length} terms · controls · ML/CV · electrical · mechanical · mechanisms</div>
        </div>
        <div class="px-2 flex flex-wrap items-center gap-2">
          <input id="q" value="${esc(q)}" placeholder="Search terms, definitions, formulas…" class="flex-1 min-w-56 bg-ink-800 rounded-lg px-3 py-2 text-sm" />
          ${chip("all", "All")}${DOMAINS.map((d) => chip(d.id, d.label)).join("")}
        </div>
        <div class="text-xs text-fg-faint px-2">${filtered.length} match${filtered.length === 1 ? "" : "es"}</div>
        <div class="space-y-5">${sections || '<div class="card p-8 text-center text-fg-muted">No matches.</div>'}</div>
      </div>`;

    const input = $(root, "#q") as HTMLInputElement | null;
    input?.addEventListener("input", () => {
      q = input.value;
      // re-render list only, keep focus
      draw(root);
      const i2 = $(root, "#q") as HTMLInputElement | null;
      if (i2) { i2.focus(); i2.setSelectionRange(i2.value.length, i2.value.length); }
    });
    $$(root, "[data-domain]").forEach((b) => b.addEventListener("click", () => { domain = b.dataset.domain!; draw(root); }));
  }
}
