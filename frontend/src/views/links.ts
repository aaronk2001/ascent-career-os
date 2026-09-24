import { api, tryApi } from "../api";
import type { View } from "../router";
import { $, $$, esc } from "../ui";
import { ring, mountRings } from "../visuals";

type ChecklistItem = { text: string; done: boolean };
type LinkStatus = "todo" | "in_progress" | "done";
type Link = {
  id: string; key: string; label: string; url: string | null;
  status: LinkStatus; checklist: ChecklistItem[]; due: string | null;
  notes: string | null; sort: number;
};

const STATUS_LABEL: Record<LinkStatus, string> = { todo: "To do", in_progress: "In progress", done: "Done" };
const STATUS_NEXT: Record<LinkStatus, LinkStatus> = { todo: "in_progress", in_progress: "done", done: "todo" };
const STATUS_TONE: Record<LinkStatus, string> = {
  todo: "text-fg-muted border-line",
  in_progress: "text-brand-400 border-brand-500/40",
  done: "text-positive border-positive/40",
};
const CHECK = '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="3"><path d="M5 13l4 4L19 7"/></svg>';

export default function links(): View {
  let items: Link[] = [];

  return {
    async render(root) {
      root.innerHTML = `<div class="p-2 text-fg-muted">Loading…</div>`;
      try {
        items = (await api<Link[]>("/links")).sort((a, b) => a.sort - b.sort);
        draw(root);
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        root.innerHTML = `<div class="space-y-3 p-2">
          <h1 class="text-2xl font-semibold tracking-tight">Profile Links</h1>
          <div class="card p-5 space-y-2">
            <div class="text-sm text-danger">Couldn't load links.</div>
            <div class="text-xs text-fg-muted">${esc(msg)}</div>
            <button id="l-retry" class="rounded-lg btn-accent px-3 py-1.5 text-sm w-fit">Retry</button>
          </div></div>`;
        $$(root, "#l-retry").forEach((b) => b.addEventListener("click", () => void this.render(root)));
      }
    },
  };

  function draw(root: HTMLElement) {
    const total = items.length;
    const done = items.filter((l) => l.status === "done").length;
    const pct = total ? (done / total) * 100 : 0;

    root.innerHTML = `
      <div class="space-y-4 pb-6">
        <div class="flex items-start justify-between gap-3 px-2">
          <div>
            <h1 class="text-2xl font-semibold tracking-tight">Profile Links</h1>
            <p class="text-sm text-fg-muted mt-1">Every application form asks for these — get to 5/5.</p>
          </div>
          <button id="l-copy" class="shrink-0 rounded-lg bg-ink-800 hover:bg-ink-700 px-3 py-1.5 text-sm">Copy all links</button>
        </div>

        <div class="card p-5 flex items-center gap-4">
          ${ring(pct, { size: 64, stroke: 6, label: `${done}/${total}` })}
          <div>
            <div class="text-sm font-medium">${done}/${total} complete</div>
            <div class="text-xs text-fg-faint">Fill in the URL and finish each checklist to mark a link done.</div>
          </div>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-2 gap-3">
          ${items.map(linkCard).join("") || '<div class="card p-8 text-center text-fg-muted">No links tracked yet.</div>'}
        </div>
      </div>`;

    mountRings(root);
    wire(root);
  }

  function checkRow(idx: number, text: string, checked: boolean): string {
    return `<label data-check="${idx}" class="flex items-start gap-2.5 py-1 text-sm">
      <span class="mt-0.5 grid place-items-center h-4 w-4 rounded border ${checked ? "accent-bg border-transparent" : "border-line-strong"} shrink-0">${checked ? CHECK : ""}</span>
      <span class="${checked ? "text-fg-faint line-through" : ""}">${esc(text)}</span></label>`;
  }

  function dueLabel(due: string | null): { text: string; cls: string } {
    if (!due) return { text: "", cls: "" };
    const [y, m, d] = due.slice(0, 10).split("-").map(Number);
    const now = new Date();
    const days = Math.round((Date.UTC(y, m - 1, d) - Date.UTC(now.getFullYear(), now.getMonth(), now.getDate())) / 86400000);
    const dateStr = new Date(`${due.slice(0, 10)}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" });
    if (days < 0) return { text: `${dateStr} — ${Math.abs(days)}d late`, cls: "text-danger" };
    if (days === 0) return { text: `${dateStr} — due today`, cls: "text-warn" };
    if (days <= 3) return { text: `${dateStr} — in ${days}d`, cls: "text-warn" };
    return { text: `${dateStr} — in ${days}d`, cls: "text-fg-faint" };
  }

  function linkCard(l: Link): string {
    const doneCount = l.checklist.filter((c) => c.done).length;
    const total = l.checklist.length;
    const due = dueLabel(l.due);
    const checklistHtml = l.checklist.map((c, i) => checkRow(i, c.text, c.done)).join("");

    return `<div class="card p-4 space-y-3" data-id="${esc(l.id)}">
      <div class="flex items-start justify-between gap-3">
        <div class="min-w-0">
          <div class="text-sm font-medium">${esc(l.label)}</div>
          ${total ? `<div class="text-[11px] text-fg-faint nums mt-0.5">${doneCount}/${total} checklist</div>` : ""}
        </div>
        <button data-status class="shrink-0 rounded-full border px-2.5 py-1 text-[11px] transition-colors ${STATUS_TONE[l.status]}">${STATUS_LABEL[l.status]}</button>
      </div>

      ${due.text ? `<div class="text-xs ${due.cls}">${due.text}</div>` : ""}

      <div class="flex items-center gap-2">
        <input data-url type="text" placeholder="https://…" value="${esc(l.url ?? "")}" class="flex-1 bg-ink-800 rounded-lg px-3 py-1.5 text-sm min-w-0" />
        ${l.url ? `<a href="${esc(l.url)}" target="_blank" class="shrink-0 text-xs accent-text hover:underline">Open ↗</a>` : ""}
      </div>

      ${checklistHtml ? `<div class="space-y-0.5">${checklistHtml}</div>` : ""}

      <input data-due type="date" value="${l.due ? esc(l.due.slice(0, 10)) : ""}" class="bg-ink-800 rounded-lg px-3 py-1.5 text-xs" />

      <textarea data-notes rows="2" placeholder="Notes…" class="w-full bg-ink-800 rounded-lg px-3 py-2 text-sm resize-y">${esc(l.notes ?? "")}</textarea>
    </div>`;
  }

  function replaceLink(rec: Link) {
    const i = items.findIndex((l) => l.id === rec.id);
    if (i >= 0) items[i] = rec;
  }

  async function cycleStatus(root: HTMLElement, l: Link) {
    const status = STATUS_NEXT[l.status];
    const r = await tryApi<Link>(`/links/${l.id}`, { method: "PUT", body: JSON.stringify({ status }) });
    if (!r.ok) { alert(`Could not update status: ${r.error}`); return; }
    replaceLink(r.data);
    draw(root);
  }

  async function saveUrl(root: HTMLElement, l: Link, url: string) {
    const body: Record<string, unknown> = { url: url || null };
    const allDone = l.checklist.length > 0 && l.checklist.every((c) => c.done);
    if (allDone && url) body.status = "done";
    const r = await tryApi<Link>(`/links/${l.id}`, { method: "PUT", body: JSON.stringify(body) });
    if (!r.ok) { alert(`Could not save URL: ${r.error}`); return; }
    replaceLink(r.data);
    draw(root);
  }

  async function saveDue(root: HTMLElement, l: Link, due: string | null) {
    const r = await tryApi<Link>(`/links/${l.id}`, { method: "PUT", body: JSON.stringify({ due }) });
    if (!r.ok) { alert(`Could not save due date: ${r.error}`); return; }
    replaceLink(r.data);
    draw(root);
  }

  async function saveNotes(root: HTMLElement, l: Link, notes: string) {
    const r = await tryApi<Link>(`/links/${l.id}`, { method: "PUT", body: JSON.stringify({ notes }) });
    if (!r.ok) { alert(`Could not save notes: ${r.error}`); return; }
    replaceLink(r.data);
    draw(root);
  }

  async function toggleChecklist(root: HTMLElement, l: Link, idx: number) {
    const checklist = l.checklist.map((c, i) => (i === idx ? { ...c, done: !c.done } : c));
    const body: Record<string, unknown> = { checklist };
    if (checklist.length > 0 && checklist.every((c) => c.done) && l.url) body.status = "done";
    const r = await tryApi<Link>(`/links/${l.id}`, { method: "PUT", body: JSON.stringify(body) });
    if (!r.ok) { alert(`Could not update checklist: ${r.error}`); return; }
    replaceLink(r.data);
    draw(root);
  }

  function copyAll(root: HTMLElement) {
    const lines = [...items].sort((a, b) => a.sort - b.sort)
      .filter((l) => l.url)
      .map((l) => `${l.label}: ${l.url}`);
    if (!lines.length) return;
    navigator.clipboard.writeText(lines.join("\n")).then(() => {
      const btn = $(root, "#l-copy");
      if (!btn) return;
      const prev = btn.textContent;
      btn.textContent = "Copied";
      setTimeout(() => { if (btn.isConnected) btn.textContent = prev; }, 1500);
    }).catch(() => {});
  }

  function wire(root: HTMLElement) {
    $(root, "#l-copy")?.addEventListener("click", () => copyAll(root));

    $$(root, "[data-id]").forEach((el) => {
      const id = el.dataset.id!;
      const link = () => items.find((l) => l.id === id)!;

      $(el, "[data-status]")?.addEventListener("click", () => cycleStatus(root, link()));

      const urlInput = $(el, "[data-url]") as HTMLInputElement | null;
      urlInput?.addEventListener("blur", () => saveUrl(root, link(), urlInput.value.trim()));

      const dueInput = $(el, "[data-due]") as HTMLInputElement | null;
      dueInput?.addEventListener("change", () => saveDue(root, link(), dueInput.value || null));

      const notesInput = $(el, "[data-notes]") as HTMLTextAreaElement | null;
      notesInput?.addEventListener("blur", () => saveNotes(root, link(), notesInput.value));

      $$(el, "[data-check]").forEach((c) => c.addEventListener("click", (e) => {
        e.preventDefault();
        toggleChecklist(root, link(), Number(c.dataset.check));
      }));
    });
  }
}
