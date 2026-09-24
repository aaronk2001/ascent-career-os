import { api, tryApi } from "../api";
import type { View } from "../router";
import { $, $$, esc, titleCase, progressBar } from "../ui";

type App = {
  id: string;
  company: string;
  role: string;
  status: string;
  url?: string | null;
  salary_range?: string | null;
  follow_up_date?: string | null;
  applied_date?: string | null;
  notes?: string | null;
  bucket?: string | null;
  location?: string | null;
  source?: string | null;
  contact_name?: string | null;
  contact_email?: string | null;
  next_action?: string | null;
  next_action_due?: string | null;
  last_contacted?: string | null;
  fit_score?: number | null;
  job_run_date?: string | null;
};

type FollowupItem = {
  id: string; company: string; role: string;
  bucket: string; due: string; overdue: boolean; action: string;
};
type NoReplyItem = {
  id: string; company: string; role: string;
  bucket: string; applied_date: string; since: string; days: number;
};
type Cadence = {
  weekly_target: number;
  bucket_targets: Record<string, number>;
  week_total: number;
  week_by_bucket: Record<string, number>;
  by_bucket: Record<string, number>;
  needs_followup: FollowupItem[];
  no_reply: NoReplyItem[];
  local_label?: string;
};

const COLUMNS = [
  "discovered", "applied", "phone_screen", "technical", "onsite", "offer", "rejected",
] as const;
const STAGE_RANK: Record<string, number> = Object.fromEntries(COLUMNS.map((c, i) => [c, i]));

const BUCKETS = ["", "local", "remote", "other"];
const BUCKET_TONE: Record<string, string> = {
  local: "text-violet-400 border-violet-400/40 bg-violet-400/10",
  remote: "text-cyan-400 border-cyan-400/40 bg-cyan-400/10",
  other: "text-fg-faint border-line bg-ink-800/40",
};
// Older rows may hold "az" (the old local-market key) or "houston" (a retired
// target); db.norm_bucket maps them the same way server-side.
const BUCKET_ALIAS: Record<string, string> = { az: "local", houston: "other" };
const normBucket = (b?: string | null) => { const k = (b || "").trim().toLowerCase(); return BUCKET_ALIAS[k] ?? k; };
let localLabel = "Local"; // settings.yaml local_label, delivered with /applications/cadence
const bucketLabel = (b?: string | null) => { const k = normBucket(b) || "other"; return k === "local" ? localLabel : titleCase(k); };
function bucketBadge(b?: string | null): string {
  const key = normBucket(b);
  if (!key || key === "other") return "";
  const tone = BUCKET_TONE[key] || BUCKET_TONE.other;
  return `<span class="inline-flex items-center rounded-full border px-1.5 py-0.5 text-[10px] ${tone}">${esc(bucketLabel(key))}</span>`;
}

// Local calendar date (matches the Python backend's date.today()), TZ-independent.
const todayISO = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
function addDays(iso: string, n: number): string {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d + n)).toISOString().slice(0, 10);
}

const VIEW_KEY = "ascent.apps.view";
type Mode = "board" | "table";
const getMode = (): Mode => (localStorage.getItem(VIEW_KEY) === "table" ? "table" : "board");

export default function applications(): View {
  let apps: App[] = [];
  let cadence: Cadence | undefined;
  let mode: Mode = getMode();

  return {
    async render(root) {
      root.innerHTML = `<div class="p-2 text-fg-muted">Loading…</div>`;
      await reload();
      draw(root);
    },
  };

  async function reload() {
    const [a, c] = await Promise.all([
      api<App[]>("/applications"),
      api<Cadence>("/applications/cadence").catch(() => undefined),
    ]);
    apps = a;
    cadence = c;
    if (c?.local_label) localLabel = c.local_label;
  }
  async function syncCadence(root: HTMLElement) {
    cadence = await api<Cadence>("/applications/cadence").catch(() => cadence);
    draw(root);
  }

  // ── card / column (board) ──────────────────────────────────────────────────
  function cardHtml(a: App): string {
    const today = todayISO();
    const salary = a.salary_range
      ? `<span class="text-[11px] text-positive nums">${esc(a.salary_range)}</span>` : "";
    const due = a.next_action_due
      ? `<span class="text-[11px] nums ${a.next_action_due.slice(0, 10) < today ? "text-danger" : "text-warn"}">${esc(a.next_action || "Follow up")} ${esc(a.next_action_due.slice(0, 10))}</span>` : "";
    const recruiter = a.contact_name
      ? `<span class="text-[11px] text-fg-faint truncate">${esc(a.contact_name)}</span>` : "";
    const meta = [salary, due, recruiter].filter(Boolean).join('<span class="text-fg-faint">·</span>');
    return `<div draggable="true" data-id="${esc(a.id)}" class="card card-hover p-3 select-none">
      <div class="flex items-start justify-between gap-2">
        <div class="text-sm font-medium leading-tight">${esc(a.company)}</div>
        ${bucketBadge(a.bucket)}
      </div>
      <div class="text-xs text-fg-muted">${esc(a.role)}</div>
      ${meta ? `<div class="mt-1 flex flex-wrap items-center gap-x-1.5 gap-y-0.5">${meta}</div>` : ""}
    </div>`;
  }
  function columnHtml(status: string, list: App[]): string {
    return `<div class="flex flex-col gap-2 min-w-[210px] flex-1" data-col="${status}">
      <div class="flex items-center justify-between px-1 text-xs uppercase tracking-wide text-fg-faint">
        <span>${esc(titleCase(status))}</span><span class="nums">${list.length}</span>
      </div>
      <div class="dropzone flex flex-col gap-2 rounded-card bg-ink-900/40 p-2 min-h-24 flex-1
                  border border-transparent transition-colors" data-status="${status}">
        ${list.map(cardHtml).join("")}
      </div>
    </div>`;
  }

  // ── table ───────────────────────────────────────────────────────────────────
  function tableHtml(): string {
    const today = todayISO();
    const rows = [...apps]
      .sort((a, b) => (STAGE_RANK[a.status] ?? 0) - (STAGE_RANK[b.status] ?? 0)
        || a.company.localeCompare(b.company))
      .map((a) => {
        const due = a.next_action_due?.slice(0, 10);
        const dueCell = due
          ? `<span class="nums ${due < today ? "text-danger" : "text-warn"}">${esc(due)}</span>` : "";
        return `<tr data-id="${esc(a.id)}" class="border-t border-line hover:bg-ink-800/50 transition-colors">
          <td class="py-2 pr-3 font-medium">${esc(a.company)}</td>
          <td class="py-2 pr-3 text-fg-muted">${esc(a.role)}</td>
          <td class="py-2 pr-3 text-fg-muted">${esc(titleCase(a.status))}</td>
          <td class="py-2 pr-3">${bucketBadge(a.bucket) || '<span class="text-fg-faint">—</span>'}</td>
          <td class="py-2 pr-3 text-fg-muted">${esc(a.next_action || "")}</td>
          <td class="py-2 pr-3">${dueCell}</td>
          <td class="py-2 pr-3 nums text-fg-faint">${esc(a.applied_date?.slice(0, 10) || "")}</td>
        </tr>`;
      }).join("");
    return `<div class="card overflow-x-auto">
      <table class="w-full text-sm">
        <thead><tr class="text-left text-[11px] uppercase tracking-wide text-fg-faint">
          <th class="py-2 px-3 font-normal">Company</th><th class="py-2 pr-3 font-normal">Role</th>
          <th class="py-2 pr-3 font-normal">Stage</th><th class="py-2 pr-3 font-normal">Bucket</th>
          <th class="py-2 pr-3 font-normal">Next action</th><th class="py-2 pr-3 font-normal">Due</th>
          <th class="py-2 pr-3 font-normal">Applied</th>
        </tr></thead>
        <tbody>${rows || `<tr><td class="p-4 text-fg-muted" colspan="7">No applications yet.</td></tr>`}</tbody>
      </table></div>`;
  }

  // ── targets + follow-up widgets ───────────────────────────────────────────────
  function targetsHtml(): string {
    if (!cadence) return "";
    const c = cadence;
    const weekPct = c.weekly_target ? (c.week_total / c.weekly_target) * 100 : 0;
    const chips = Object.keys(c.bucket_targets).map((b) => {
      const have = c.by_bucket[b] ?? 0;
      const target = c.bucket_targets[b] ?? 0;
      const pct = target ? (have / target) * 100 : 0;
      const tone = b === "other" ? "bg-ink-600" : b === "remote" ? "bg-cyan-400" : "bg-violet-400";
      return `<div class="flex-1 min-w-[120px]">
        <div class="flex items-center justify-between text-[11px] mb-1">
          <span class="text-fg-muted">${esc(bucketLabel(b))}</span>
          <span class="nums text-fg-faint">${have}/${target}</span>
        </div>${progressBar(pct, tone)}</div>`;
    }).join("");
    return `<div class="card p-4 space-y-3">
      <div class="flex items-end justify-between">
        <div>
          <div class="text-xs uppercase tracking-wide text-fg-faint">Applications this week</div>
          <div class="text-2xl font-semibold nums">${c.week_total}<span class="text-fg-faint text-base font-normal"> / ${c.weekly_target}</span></div>
        </div>
        <div class="w-40">${progressBar(weekPct, "accent-bg")}</div>
      </div>
      <div class="flex flex-wrap gap-4 pt-1">${chips}</div>
    </div>`;
  }

  function followupHtml(): string {
    const items = cadence?.needs_followup ?? [];
    if (!items.length) return "";
    const overdue = items.filter((i) => i.overdue).length;
    const row = (i: FollowupItem) => `<div class="flex items-center gap-2 py-1.5" data-fu="${esc(i.id)}">
      <span class="w-1.5 h-1.5 rounded-full ${i.overdue ? "bg-danger" : "bg-warn"} shrink-0"></span>
      <div class="min-w-0 flex-1">
        <div class="text-sm truncate"><span class="font-medium">${esc(i.company)}</span>
          <span class="text-fg-muted">· ${esc(i.role)}</span></div>
        <div class="text-[11px] text-fg-faint">${esc(i.action)} · <span class="nums ${i.overdue ? "text-danger" : "text-warn"}">${esc(i.due)}</span></div>
      </div>
      ${bucketBadge(i.bucket)}
      <button data-fu-done class="rounded-lg bg-ink-800 hover:bg-positive/20 hover:text-positive px-2 py-1 text-[11px] transition-colors">Done</button>
      <button data-fu-snooze class="rounded-lg bg-ink-800 hover:bg-ink-700 px-2 py-1 text-[11px] transition-colors">+3d</button>
    </div>`;
    return `<div class="card p-4">
      <div class="flex items-center gap-2 mb-2">
        <h2 class="text-sm font-semibold tracking-tight">Needs follow-up</h2>
        <span class="nums text-[11px] text-fg-faint">${items.length}${overdue ? ` · <span class="text-danger">${overdue} overdue</span>` : ""}</span>
      </div>
      <div class="divide-y divide-line">${items.map(row).join("")}</div>
    </div>`;
  }

  // ── no reply / ghosted (auto-collected after 14 days silent) ──────────────────
  function noReplyHtml(): string {
    const items = cadence?.no_reply ?? [];
    if (!items.length) return "";
    const row = (i: NoReplyItem) => `<div class="flex items-center gap-2 py-1.5" data-nr="${esc(i.id)}">
      <span class="w-1.5 h-1.5 rounded-full ${i.days >= 21 ? "bg-danger" : "bg-warn"} shrink-0"></span>
      <div class="min-w-0 flex-1">
        <div class="text-sm truncate"><span class="font-medium">${esc(i.company)}</span>
          <span class="text-fg-muted">· ${esc(i.role)}</span></div>
        <div class="text-[11px] text-fg-faint">silent <span class="nums ${i.days >= 21 ? "text-danger" : "text-warn"}">${i.days}d</span>${i.applied_date ? ` · applied ${esc(i.applied_date)}` : ""}</div>
      </div>
      ${bucketBadge(i.bucket)}
      <button data-nr-followed class="rounded-lg bg-ink-800 hover:bg-positive/20 hover:text-positive px-2 py-1 text-[11px] transition-colors">Followed up</button>
      <button data-nr-close class="rounded-lg bg-ink-800 hover:bg-danger/20 hover:text-danger px-2 py-1 text-[11px] transition-colors">Close</button>
    </div>`;
    return `<div class="card p-4">
      <div class="flex items-center gap-2 mb-2">
        <h2 class="text-sm font-semibold tracking-tight">No reply</h2>
        <span class="nums text-[11px] text-fg-faint">${items.length} · applied 2+ weeks ago, silent</span>
      </div>
      <div class="divide-y divide-line">${items.map(row).join("")}</div>
    </div>`;
  }

  // ── render ──────────────────────────────────────────────────────────────────
  function draw(root: HTMLElement) {
    const toggle = (m: Mode, label: string) =>
      `<button data-mode="${m}" class="px-2.5 py-1 text-xs rounded-md transition-colors ${mode === m ? "btn-accent" : "bg-ink-800 hover:bg-ink-700 text-fg-muted"}">${label}</button>`;
    const noReplyIds = new Set((cadence?.no_reply ?? []).map((i) => i.id));
    // Ghosted apps auto-leave the "Applied" column and collect in the No-reply section.
    const inColumn = (a: App, c: string) => a.status === c && !(c === "applied" && noReplyIds.has(a.id));
    const body = mode === "board"
      ? `<div class="flex gap-3 overflow-x-auto pb-2">${COLUMNS.map((c) => columnHtml(c, apps.filter((a) => inColumn(a, c)))).join("")}</div>`
      : tableHtml();

    root.innerHTML = `
      <div class="space-y-4">
        <div class="flex flex-wrap items-center justify-between gap-3 px-2">
          <h1 class="text-2xl font-semibold tracking-tight">Applications</h1>
          <div class="flex items-center gap-2">
            <div class="flex gap-1 rounded-lg bg-ink-900/60 p-0.5">${toggle("board", "Board")}${toggle("table", "Table")}</div>
            <button id="add-app" class="rounded-lg btn-accent px-3 py-1.5 text-sm font-medium">+ Add</button>
          </div>
        </div>
        ${targetsHtml()}
        ${followupHtml()}
        ${noReplyHtml()}
        <div id="addform" class="hidden card p-4">
          <div class="grid grid-cols-2 gap-2">
            <input id="f-company" placeholder="Company" class="bg-ink-800 rounded-lg px-3 py-2 text-sm" />
            <input id="f-role" placeholder="Role" class="bg-ink-800 rounded-lg px-3 py-2 text-sm" />
            <input id="f-salary" placeholder="Salary range" class="bg-ink-800 rounded-lg px-3 py-2 text-sm" />
            <input id="f-location" placeholder="Location" class="bg-ink-800 rounded-lg px-3 py-2 text-sm" />
            <input id="f-url" placeholder="Job URL" class="bg-ink-800 rounded-lg px-3 py-2 text-sm col-span-2" />
            <label class="flex flex-col gap-1 text-xs text-fg-muted">Bucket
              <select id="f-bucket" class="bg-ink-800 rounded-lg px-3 py-2 text-sm">${BUCKETS.map((b) => `<option value="${b}">${b ? bucketLabel(b) : "—"}</option>`).join("")}</select></label>
          </div>
          <div class="mt-3 flex gap-2">
            <button id="f-save" class="rounded-lg btn-accent px-3 py-1.5 text-sm">Save</button>
            <button id="f-cancel" class="rounded-lg bg-ink-800 hover:bg-ink-700 px-3 py-1.5 text-sm">Cancel</button>
          </div>
        </div>
        ${body}
      </div>`;

    wireViewToggle(root);
    wireAddForm(root);
    wireFollowup(root);
    wireNoReply(root);
    if (mode === "board") { wireDnd(root); wireCardClicks(root); }
    else wireRowClicks(root);
  }

  function wireViewToggle(root: HTMLElement) {
    $$(root, "[data-mode]").forEach((b) => b.addEventListener("click", () => {
      const m = b.dataset.mode as Mode;
      if (m === mode) return;
      mode = m;
      localStorage.setItem(VIEW_KEY, m);
      draw(root);
    }));
  }

  function wireRowClicks(root: HTMLElement) {
    $$(root, "tr[data-id]").forEach((tr) => tr.addEventListener("click", () => {
      const app = apps.find((a) => a.id === tr.dataset.id);
      if (app) openEditor(root, app);
    }));
  }

  function wireCardClicks(root: HTMLElement) {
    let dragging = false;
    $$(root, "[data-id]").forEach((card) => {
      card.addEventListener("dragstart", () => { dragging = true; });
      card.addEventListener("dragend", () => { setTimeout(() => { dragging = false; }, 0); });
      card.addEventListener("click", () => {
        if (dragging) return;
        const app = apps.find((a) => a.id === card.dataset.id);
        if (app) openEditor(root, app);
      });
    });
  }

  function wireFollowup(root: HTMLElement) {
    $$(root, "[data-fu]").forEach((rowEl) => {
      const id = rowEl.dataset.fu!;
      const app = apps.find((a) => a.id === id);
      $(rowEl, "[data-fu-done]")?.addEventListener("click", async (e) => {
        e.stopPropagation();
        const r = await tryApi<App>(`/applications/${id}`, {
          method: "PUT",
          body: JSON.stringify({ last_contacted: todayISO(), next_action_due: null, next_action: null }),
        });
        if (!r.ok) return alert(`Could not update: ${r.error}`);
        if (app) Object.assign(app, r.data);
        await syncCadence(root);
      });
      $(rowEl, "[data-fu-snooze]")?.addEventListener("click", async (e) => {
        e.stopPropagation();
        const due = app?.next_action_due?.slice(0, 10) || app?.follow_up_date?.slice(0, 10) || todayISO();
        const r = await tryApi<App>(`/applications/${id}`, {
          method: "PUT",
          body: JSON.stringify({ next_action_due: addDays(due, 3) }),
        });
        if (!r.ok) return alert(`Could not snooze: ${r.error}`);
        if (app) Object.assign(app, r.data);
        await syncCadence(root);
      });
    });
  }

  function wireNoReply(root: HTMLElement) {
    $$(root, "[data-nr]").forEach((rowEl) => {
      const id = rowEl.dataset.nr!;
      const app = apps.find((a) => a.id === id);
      const patch = async (body: object, label: string) => {
        const r = await tryApi<App>(`/applications/${id}`, { method: "PUT", body: JSON.stringify(body) });
        if (!r.ok) return alert(`Could not ${label}: ${r.error}`);
        if (app) Object.assign(app, r.data);
        await syncCadence(root);
      };
      // Followed up → resets the silence clock; card returns to the Applied column.
      $(rowEl, "[data-nr-followed]")?.addEventListener("click", () => void patch({ last_contacted: todayISO() }, "update"));
      // Close → mark rejected; card moves to the Rejected column.
      $(rowEl, "[data-nr-close]")?.addEventListener("click", () => void patch({ status: "rejected" }, "close"));
    });
  }

  // ── editor ────────────────────────────────────────────────────────────────
  function openEditor(root: HTMLElement, app: App) {
    const overlay = document.createElement("div");
    overlay.className = "fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4";
    const close = () => overlay.remove();

    const opt = (s: string) => `<option value="${s}" ${s === app.status ? "selected" : ""}>${esc(titleCase(s))}</option>`;
    const bOpt = (b: string) => `<option value="${b}" ${b === normBucket(app.bucket) ? "selected" : ""}>${b ? bucketLabel(b) : "—"}</option>`;
    const field = (id: string, label: string, value: unknown, type = "text") =>
      `<label class="flex flex-col gap-1 text-xs text-fg-muted">${esc(label)}
        <input id="${id}" type="${type}" value="${esc(value ?? "")}"
          class="bg-ink-800 rounded-lg px-3 py-2 text-sm text-fg" /></label>`;

    overlay.innerHTML = `
      <div class="glass w-[520px] max-w-[94vw] max-h-[90vh] overflow-y-auto rounded-card p-5 space-y-3" role="dialog" aria-modal="true">
        <div class="flex items-center justify-between">
          <h2 class="text-lg font-semibold tracking-tight">Edit application</h2>
          <button id="e-x" class="text-fg-faint hover:text-fg">✕</button>
        </div>
        <div class="grid grid-cols-2 gap-2">
          ${field("e-company", "Company", app.company)}
          ${field("e-role", "Role", app.role)}
          ${field("e-salary", "Salary range", app.salary_range)}
          ${field("e-location", "Location", app.location)}
          <label class="flex flex-col gap-1 text-xs text-fg-muted">Status
            <select id="e-status" class="bg-ink-800 rounded-lg px-3 py-2 text-sm text-fg">${COLUMNS.map(opt).join("")}</select></label>
          <label class="flex flex-col gap-1 text-xs text-fg-muted">Bucket
            <select id="e-bucket" class="bg-ink-800 rounded-lg px-3 py-2 text-sm text-fg">${BUCKETS.map(bOpt).join("")}</select></label>
          ${field("e-applied", "Applied date", app.applied_date, "date")}
          ${field("e-follow", "Follow-up date", app.follow_up_date, "date")}
          ${field("e-contact", "Recruiter / contact", app.contact_name)}
          ${field("e-email", "Contact email", app.contact_email)}
          ${field("e-action", "Next action", app.next_action)}
          ${field("e-actiondue", "Next action due", app.next_action_due, "date")}
          ${field("e-contacted", "Last contacted", app.last_contacted, "date")}
        </div>
        ${field("e-url", "Job URL", app.url)}
        <label class="flex flex-col gap-1 text-xs text-fg-muted">Notes
          <textarea id="e-notes" rows="3" class="bg-ink-800 rounded-lg px-3 py-2 text-sm text-fg">${esc(app.notes ?? "")}</textarea></label>
        ${app.source ? `<div class="text-[11px] text-fg-faint">Source: ${esc(app.source)}${app.job_run_date ? ` · run ${esc(String(app.job_run_date).slice(0, 10))}` : ""}</div>` : ""}
        <div class="flex items-center justify-between pt-1">
          <button id="e-delete" class="rounded-lg bg-ink-800 hover:bg-danger/20 text-danger px-3 py-1.5 text-sm transition-colors">Delete</button>
          <div class="flex gap-2">
            <button id="e-cancel" class="rounded-lg bg-ink-800 hover:bg-ink-700 px-3 py-1.5 text-sm">Cancel</button>
            <button id="e-save" class="rounded-lg btn-accent px-3 py-1.5 text-sm">Save</button>
          </div>
        </div>
      </div>`;

    overlay.addEventListener("click", (e) => { if (e.target === overlay) close(); });
    document.body.appendChild(overlay);

    const val = (id: string) =>
      ($(overlay, id) as HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement | null)?.value.trim() ?? "";

    $(overlay, "#e-x")?.addEventListener("click", close);
    $(overlay, "#e-cancel")?.addEventListener("click", close);

    $(overlay, "#e-save")?.addEventListener("click", async () => {
      const company = val("#e-company");
      const role = val("#e-role");
      if (!company || !role) return;
      const patch = {
        company, role,
        salary_range: val("#e-salary") || null,
        location: val("#e-location") || null,
        url: val("#e-url") || null,
        status: val("#e-status"),
        bucket: val("#e-bucket") || null,
        applied_date: val("#e-applied") || null,
        follow_up_date: val("#e-follow") || null,
        contact_name: val("#e-contact") || null,
        contact_email: val("#e-email") || null,
        next_action: val("#e-action") || null,
        next_action_due: val("#e-actiondue") || null,
        last_contacted: val("#e-contacted") || null,
        notes: val("#e-notes") || null,
      };
      const r = await tryApi<App>(`/applications/${app.id}`, { method: "PUT", body: JSON.stringify(patch) });
      if (!r.ok) return alert(`Could not save changes: ${r.error}`);
      Object.assign(app, r.data);
      close();
      await syncCadence(root);
    });

    $(overlay, "#e-delete")?.addEventListener("click", async () => {
      if (!confirm(`Delete ${app.company} — ${app.role}?`)) return;
      const r = await tryApi(`/applications/${app.id}`, { method: "DELETE" });
      if (!r.ok) return alert(`Could not delete: ${r.error}`);
      apps = apps.filter((a) => a.id !== app.id);
      close();
      await syncCadence(root);
    });
  }

  // ── add (with dedup) ─────────────────────────────────────────────────────────
  function wireAddForm(root: HTMLElement) {
    const form = $(root, "#addform");
    $(root, "#add-app")?.addEventListener("click", () => form?.classList.toggle("hidden"));
    $(root, "#f-cancel")?.addEventListener("click", () => form?.classList.add("hidden"));
    $(root, "#f-save")?.addEventListener("click", async () => {
      const v = (id: string) => ($(root, id) as HTMLInputElement | HTMLSelectElement | null)?.value.trim() ?? "";
      const company = v("#f-company");
      const role = v("#f-role");
      const url = v("#f-url");
      if (!company || !role) return;

      const dup = await api<{ duplicate: boolean; existing: App | null }>(
        `/applications/duplicate?company=${encodeURIComponent(company)}&role=${encodeURIComponent(role)}&url=${encodeURIComponent(url)}`,
      ).catch(() => ({ duplicate: false, existing: null }));
      if (dup.duplicate && dup.existing &&
          !confirm(`Looks like a duplicate of ${dup.existing.company} — ${dup.existing.role} (${titleCase(dup.existing.status)}). Add anyway?`)) return;

      const r = await tryApi<App>("/applications", {
        method: "POST",
        body: JSON.stringify({
          company, role,
          salary_range: v("#f-salary") || null,
          location: v("#f-location") || null,
          url: url || null,
          bucket: v("#f-bucket") || null,
          source: "manual",
          status: "discovered",
        }),
      });
      if (!r.ok) return alert(`Could not save application: ${r.error}`);
      apps.push(r.data);
      await syncCadence(root);
    });
  }

  // ── drag-and-drop (board) ─────────────────────────────────────────────────────
  function wireDnd(root: HTMLElement) {
    let dragId: string | null = null;
    $$(root, "[data-id]").forEach((card) => {
      card.addEventListener("dragstart", () => { dragId = card.dataset.id ?? null; card.classList.add("opacity-40"); });
      card.addEventListener("dragend", () => card.classList.remove("opacity-40"));
    });
    $$(root, ".dropzone").forEach((zone) => {
      zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.classList.add("border-brand-500/50"); });
      zone.addEventListener("dragleave", () => zone.classList.remove("border-brand-500/50"));
      zone.addEventListener("drop", async (e) => {
        e.preventDefault();
        zone.classList.remove("border-brand-500/50");
        const status = zone.dataset.status;
        if (!dragId || !status) return;
        const app = apps.find((a) => a.id === dragId);
        if (!app || app.status === status) return;
        const prev = { ...app };
        // optimistic local move + follow-up automation mirroring the backend create()
        const patch: Partial<App> = { status, last_contacted: todayISO() };
        if (status !== "discovered" && status !== "rejected") {
          if (status === "applied" && !app.applied_date) patch.applied_date = todayISO();
          if (!app.next_action_due && (app.applied_date || patch.applied_date)) {
            patch.next_action_due = addDays((app.applied_date || patch.applied_date)!.slice(0, 10), 3);
            patch.next_action = app.next_action || "Follow up";
          }
        }
        Object.assign(app, patch);
        draw(root);
        const r = await tryApi<App>(`/applications/${app.id}`, { method: "PUT", body: JSON.stringify(patch) });
        if (!r.ok) {
          Object.assign(app, prev);
          draw(root);
          return alert(`Could not move card: ${r.error}`);
        }
        Object.assign(app, r.data);
        await syncCadence(root);
      });
    });
  }
}
