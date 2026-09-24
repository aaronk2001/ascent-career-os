import { api } from "../api";
import type { View } from "../router";
import { $, $$, esc } from "../ui";

type Block = { start: string; min: number; cat: string; title?: string };
type Templates = { weekday: Block[]; saturday: Block[]; sunday: Block[]; bridge_weekday: Block[] };
type ScheduleResp = {
  wake: string;
  hard_stop: string;
  templates: Templates;
  cats: Record<string, { label: string; color: string }>;
};

type SettingsResp = {
  settings: {
    model: string;
    ollama_host: string;
    weekly_target?: number;
    target_date?: string;
    bucket_targets?: Record<string, number>;
    sprint_start?: string;
    offer_date?: string;
    stretch_date?: string;
    runway_end?: string;
    bridge_gate?: string;
    daily_apps?: number;
    bridge_mode?: boolean;
    cert_budget?: number | null;
  };
  ollama: { reachable: boolean; models: string[]; error?: string | null };
  free_ram_gib: number | null;
  fallback_model: string;
  curated: { name: string; tier: string; note: string }[];
  app: { ascent_port: number; output_dir: string };
};

const TEMPLATE_LABEL: Record<keyof Templates, string> = {
  weekday: "Weekday",
  saturday: "Saturday",
  sunday: "Sunday",
  bridge_weekday: "Bridge weekday",
};
const TEMPLATE_KEYS = Object.keys(TEMPLATE_LABEL) as (keyof Templates)[];

export default function settings(): View {
  let sched: ScheduleResp | null = null;

  return {
    async render(root) {
      root.innerHTML = `<div class="p-2 text-fg-muted">Loading…</div>`;
      const [d, s] = await Promise.all([api<SettingsResp>("/settings"), api<ScheduleResp>("/schedule")]);
      sched = s;
      draw(root, d);
    },
  };

  function draw(root: HTMLElement, d: SettingsResp) {
    const curatedNotes = new Map(d.curated.map((c) => [c.name, c.note]));
    const models = [...new Set([...curatedNotes.keys(), ...d.ollama.models, d.settings.model])].filter(Boolean);
    const opts = models
      .map((m) => {
        const note = curatedNotes.get(m);
        return `<option value="${esc(m)}" ${m === d.settings.model ? "selected" : ""}>${esc(m)}${note ? ` — ${esc(note)}` : ""}</option>`;
      })
      .join("");
    const dot = d.ollama.reachable ? "text-positive" : "text-danger";
    const bt = d.settings.bucket_targets || { az: 5, remote: 3 };
    const weekly = d.settings.weekly_target ?? 8;
    const tdate = d.settings.target_date ?? "";
    const bktInput = (id: string, label: string, v: number) =>
      `<label class="flex flex-col gap-1 text-xs text-fg-muted">${esc(label)}
        <input id="${id}" type="number" min="0" value="${v}" class="w-20 bg-ink-800 rounded-lg px-3 py-2 text-sm" /></label>`;

    const s = sched!;

    root.innerHTML = `
      <div class="space-y-4 max-w-xl">
        <h1 class="text-2xl font-semibold tracking-tight px-2">Settings</h1>
        <div class="mx-2 h-1 rounded-full" style="background:linear-gradient(90deg,var(--accent),var(--accent-2),var(--accent));background-size:200% 100%;animation:shimmer 3s linear infinite"></div>

        <div class="card p-4 space-y-3">
          <label class="block text-xs uppercase tracking-wide text-fg-faint">Job sprint</label>
          <div class="flex flex-wrap gap-3">
            <label class="flex flex-col gap-1 text-xs text-fg-muted">Sprint start
              <input id="js-start" type="date" value="${esc(d.settings.sprint_start ?? "")}" class="bg-ink-800 rounded-lg px-3 py-2 text-sm" /></label>
            <label class="flex flex-col gap-1 text-xs text-fg-muted">Offer date
              <input id="js-offer" type="date" value="${esc(d.settings.offer_date ?? "")}" class="bg-ink-800 rounded-lg px-3 py-2 text-sm" /></label>
            <label class="flex flex-col gap-1 text-xs text-fg-muted">Stretch (first offer)
              <input id="js-stretch" type="date" value="${esc(d.settings.stretch_date ?? "")}" class="bg-ink-800 rounded-lg px-3 py-2 text-sm" /></label>
            <label class="flex flex-col gap-1 text-xs text-fg-muted">Runway end
              <input id="js-runway" type="date" value="${esc(d.settings.runway_end ?? "")}" class="bg-ink-800 rounded-lg px-3 py-2 text-sm" /></label>
            <label class="flex flex-col gap-1 text-xs text-fg-muted">Bridge gate
              <input id="js-bridge" type="date" value="${esc(d.settings.bridge_gate ?? "")}" class="bg-ink-800 rounded-lg px-3 py-2 text-sm" /></label>
            <label class="flex flex-col gap-1 text-xs text-fg-muted">Apps / day
              <input id="js-daily-apps" type="number" min="0" value="${d.settings.daily_apps ?? 0}" class="w-20 bg-ink-800 rounded-lg px-3 py-2 text-sm" /></label>
            <label class="block space-y-1"><span class="text-xs text-fg-muted">Cert budget (USD, blank = none)</span>
              <input id="js-cert-budget" type="number" min="0" value="${d.settings.cert_budget ?? ""}" class="bg-ink-800 rounded-lg px-3 py-2 text-sm w-32" /></label>
          </div>
          <label class="flex items-center gap-2 text-xs text-fg-muted pt-1">
            <input id="js-bridge-mode" type="checkbox" ${d.settings.bridge_mode ? "checked" : ""} class="h-4 w-4" />
            Bridge mode — weekdays use the 6-hour bridge template
          </label>
          <button id="js-save" class="rounded-lg btn-accent px-3 py-1.5 text-sm">Save</button>
          <span id="js-msg" class="ml-2 text-xs text-positive"></span>
        </div>

        <div class="card p-4 space-y-3">
          <label class="block text-xs uppercase tracking-wide text-fg-faint">Job-search targets</label>
          <div class="flex flex-wrap gap-3">
            <label class="flex flex-col gap-1 text-xs text-fg-muted">Apps / week
              <input id="t-weekly" type="number" min="0" value="${weekly}" class="w-24 bg-ink-800 rounded-lg px-3 py-2 text-sm" /></label>
            <label class="flex flex-col gap-1 text-xs text-fg-muted">Plan target date
              <input id="t-date" type="date" value="${esc(tdate)}" class="bg-ink-800 rounded-lg px-3 py-2 text-sm" /></label>
          </div>
          <label class="block text-xs uppercase tracking-wide text-fg-faint pt-1">Pipeline targets by bucket</label>
          <div class="flex flex-wrap gap-3">
            ${bktInput("t-az", "Arizona", bt.az ?? 5)}
            ${bktInput("t-rem", "Remote", bt.remote ?? 3)}
          </div>
          <button id="t-save" class="rounded-lg btn-accent px-3 py-1.5 text-sm">Save targets</button>
          <span id="t-msg" class="ml-2 text-xs text-positive"></span>
        </div>

        <div class="card p-4 space-y-3">
          <label class="block text-xs uppercase tracking-wide text-fg-faint">Model</label>
          <select id="s-model" class="w-full bg-ink-800 rounded-lg px-3 py-2 text-sm">${opts}</select>
          <label class="block text-xs uppercase tracking-wide text-fg-faint">Ollama host</label>
          <input id="s-host" value="${esc(d.settings.ollama_host)}" class="w-full bg-ink-800 rounded-lg px-3 py-2 text-sm" />
          <button id="s-save" class="rounded-lg btn-accent px-3 py-1.5 text-sm">Save</button>
          <span id="s-msg" class="ml-2 text-xs text-positive"></span>
        </div>

        <div class="card p-4 space-y-4">
          <label class="block text-xs uppercase tracking-wide text-fg-faint">Day templates</label>
          <div class="flex flex-wrap gap-3">
            <label class="flex flex-col gap-1 text-xs text-fg-muted">Wake
              <input id="sc-wake" type="time" value="${esc(s.wake)}" class="bg-ink-800 rounded-lg px-3 py-2 text-sm" /></label>
            <label class="flex flex-col gap-1 text-xs text-fg-muted">Hard stop
              <input id="sc-hardstop" type="time" value="${esc(s.hard_stop)}" class="bg-ink-800 rounded-lg px-3 py-2 text-sm" /></label>
          </div>
          ${TEMPLATE_KEYS.map(
            (key) => `<div class="space-y-1.5 pt-2 border-t border-line">
              <div class="text-xs font-medium text-fg-muted">${esc(TEMPLATE_LABEL[key])}</div>
              <div id="tmpl-wrap-${key}">${templateBlockHtml(key, s.templates[key], s.cats)}</div>
            </div>`,
          ).join("")}
          <button id="sc-save" class="rounded-lg btn-accent px-3 py-1.5 text-sm">Save templates</button>
          <span id="sc-msg" class="ml-2 text-xs text-positive"></span>
          <div class="text-xs text-fg-faint">Regenerate Today after changing templates (Today → Regenerate).</div>
        </div>

        <div class="card p-4 text-sm space-y-1 text-fg-muted">
          <div>Ollama: <span class="${dot}">${d.ollama.reachable ? "reachable" : "unreachable"}</span>${d.ollama.error ? ` · ${esc(d.ollama.error)}` : ""}</div>
          <div>Free RAM: <span class="nums text-fg">${d.free_ram_gib != null ? `${d.free_ram_gib} GiB` : "n/a"}</span></div>
          <div>Fallback model: <span class="text-fg">${esc(d.fallback_model)}</span></div>
          <div>Port: <span class="nums text-fg">${d.app.ascent_port}</span></div>
        </div>
      </div>`;

    wire(root);
  }

  function wire(root: HTMLElement) {
    $(root, "#js-save")?.addEventListener("click", async () => {
      const sprint_start = ($(root, "#js-start") as HTMLInputElement).value;
      const offer_date = ($(root, "#js-offer") as HTMLInputElement).value;
      const stretch_date = ($(root, "#js-stretch") as HTMLInputElement).value;
      const runway_end = ($(root, "#js-runway") as HTMLInputElement).value;
      const bridge_gate = ($(root, "#js-bridge") as HTMLInputElement).value;
      const daily_apps = Number(($(root, "#js-daily-apps") as HTMLInputElement).value) || 0;
      const bridge_mode = ($(root, "#js-bridge-mode") as HTMLInputElement).checked;
      const certBudgetRaw = ($(root, "#js-cert-budget") as HTMLInputElement).value.trim();
      const cert_budget = certBudgetRaw === "" ? null : Number(certBudgetRaw);
      const msg = $(root, "#js-msg");
      try {
        await api("/settings", {
          method: "POST",
          body: JSON.stringify({ sprint_start, offer_date, stretch_date, runway_end, bridge_gate, daily_apps, bridge_mode, cert_budget }),
        });
        if (msg) { msg.textContent = "Saved"; msg.className = "ml-2 text-xs text-positive"; }
      } catch (e) {
        if (msg) { msg.textContent = `Save failed: ${e instanceof Error ? e.message : String(e)}`; msg.className = "ml-2 text-xs text-danger"; }
      }
    });

    $(root, "#t-save")?.addEventListener("click", async () => {
      const weekly_target = Number(($(root, "#t-weekly") as HTMLInputElement).value) || 0;
      const target_date = ($(root, "#t-date") as HTMLInputElement).value;
      const bucket_targets = {
        az: Number(($(root, "#t-az") as HTMLInputElement).value) || 0,
        remote: Number(($(root, "#t-rem") as HTMLInputElement).value) || 0,
      };
      const msg = $(root, "#t-msg");
      try {
        await api("/settings", { method: "POST", body: JSON.stringify({ weekly_target, target_date, bucket_targets }) });
        if (msg) { msg.textContent = "Saved"; msg.className = "ml-2 text-xs text-positive"; }
      } catch (e) {
        if (msg) { msg.textContent = `Save failed: ${e instanceof Error ? e.message : String(e)}`; msg.className = "ml-2 text-xs text-danger"; }
      }
    });

    $(root, "#s-save")?.addEventListener("click", async () => {
      const model = ($(root, "#s-model") as HTMLSelectElement).value;
      const ollama_host = ($(root, "#s-host") as HTMLInputElement).value.trim();
      const msg = $(root, "#s-msg");
      try {
        await api("/settings", { method: "POST", body: JSON.stringify({ model, ollama_host }) });
        if (msg) {
          msg.textContent = "Saved";
          msg.className = "ml-2 text-xs text-positive";
        }
      } catch (e) {
        if (msg) {
          msg.textContent = `Save failed: ${e instanceof Error ? e.message : String(e)}`;
          msg.className = "ml-2 text-xs text-danger";
        }
      }
    });

    TEMPLATE_KEYS.forEach((key) => wireTemplateBlock(root, key));

    $(root, "#sc-save")?.addEventListener("click", async () => {
      if (!sched) return;
      const wake = ($(root, "#sc-wake") as HTMLInputElement).value;
      const hard_stop = ($(root, "#sc-hardstop") as HTMLInputElement).value;
      const templates: Templates = {
        weekday: readTemplateRows(root, "weekday"),
        saturday: readTemplateRows(root, "saturday"),
        sunday: readTemplateRows(root, "sunday"),
        bridge_weekday: readTemplateRows(root, "bridge_weekday"),
      };
      const msg = $(root, "#sc-msg");
      try {
        await api("/schedule", { method: "PUT", body: JSON.stringify({ wake, hard_stop, templates }) });
        sched = { ...sched, wake, hard_stop, templates };
        if (msg) { msg.textContent = "Saved"; msg.className = "ml-2 text-xs text-positive"; }
      } catch (e) {
        if (msg) { msg.textContent = `Save failed: ${e instanceof Error ? e.message : String(e)}`; msg.className = "ml-2 text-xs text-danger"; }
      }
    });
  }

  function wireTemplateBlock(root: HTMLElement, key: keyof Templates) {
    const wrap = $(root, `#tmpl-wrap-${key}`);
    if (!wrap || !sched) return;
    $(wrap, `[data-add-tmpl="${key}"]`)?.addEventListener("click", () => {
      if (!sched) return;
      const rows = readTemplateRows(root, key);
      const firstCat = Object.keys(sched.cats)[0] ?? "";
      rows.push({ start: "09:00", min: 30, cat: firstCat });
      sched.templates[key] = rows;
      wrap.innerHTML = templateBlockHtml(key, rows, sched.cats);
      wireTemplateBlock(root, key);
    });
    $$(wrap, "[data-remove-row]").forEach((btn) => {
      btn.addEventListener("click", () => {
        if (!sched) return;
        const rows = readTemplateRows(root, key);
        const row = btn.closest<HTMLElement>("[data-row]");
        const idx = Number(row?.dataset.idx ?? -1);
        if (idx < 0) return;
        rows.splice(idx, 1);
        sched.templates[key] = rows;
        wrap.innerHTML = templateBlockHtml(key, rows, sched.cats);
        wireTemplateBlock(root, key);
      });
    });
  }

  function readTemplateRows(root: HTMLElement, key: keyof Templates): Block[] {
    return $$(root, `#tmpl-${key} [data-row]`).map((r) => {
      const title = ($(r, '[data-f="title"]') as HTMLInputElement).value.trim();
      return {
        start: ($(r, '[data-f="start"]') as HTMLInputElement).value,
        min: Number(($(r, '[data-f="min"]') as HTMLInputElement).value) || 0,
        cat: ($(r, '[data-f="cat"]') as HTMLSelectElement).value,
        ...(title ? { title } : {}),
      };
    });
  }
}

function templateBlockHtml(key: keyof Templates, blocks: Block[], cats: Record<string, { label: string; color: string }>): string {
  const catOpts = (sel: string) =>
    Object.entries(cats).map(([id, c]) => `<option value="${esc(id)}" ${id === sel ? "selected" : ""}>${esc(c.label)}</option>`).join("");
  const rows = blocks
    .map(
      (b, i) => `<div data-row data-idx="${i}" class="flex flex-wrap items-center gap-1.5 py-1">
        <input data-f="start" type="time" value="${esc(b.start)}" class="w-24 bg-ink-800 rounded-lg px-2 py-1.5 text-xs" />
        <input data-f="min" type="number" min="0" step="5" value="${b.min}" class="w-16 bg-ink-800 rounded-lg px-2 py-1.5 text-xs" />
        <select data-f="cat" class="bg-ink-800 rounded-lg px-2 py-1.5 text-xs">${catOpts(b.cat)}</select>
        <input data-f="title" value="${esc(b.title ?? "")}" placeholder="title (optional)" class="flex-1 min-w-24 bg-ink-800 rounded-lg px-2 py-1.5 text-xs" />
        <button data-remove-row class="text-fg-faint hover:text-danger text-xs px-1">×</button>
      </div>`,
    )
    .join("");
  return `<div id="tmpl-${key}" class="space-y-1">${rows}</div>
    <button data-add-tmpl="${key}" class="mt-1 rounded-lg bg-ink-800 hover:bg-ink-700 px-2.5 py-1 text-xs">+ block</button>`;
}
