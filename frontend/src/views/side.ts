import { api, tryApi } from "../api";
import type { View } from "../router";
import { $, $$, esc, progressBar } from "../ui";

type SideSource = "clips" | "freelance" | "bridge" | "other";
type SideEntry = {
  id: string; date: string; source: SideSource; platform: string | null;
  posts: number; followers: number; views: number; revenue: number; note: string | null;
};
type SideSummary = {
  latest_followers: Record<string, { followers: number; date: string }>;
  posts_mtd: number; revenue_mtd: number; posts_total: number; revenue_total: number;
  streak_days: number; entries: number;
};

export default function side(): View {
  let entries: SideEntry[] = [];
  let summary: SideSummary | undefined;

  return {
    async render(root) {
      root.innerHTML = `<div class="p-2 text-fg-muted">Loading…</div>`;
      try {
        [entries, summary] = await Promise.all([
          api<SideEntry[]>("/side?limit=30"),
          api<SideSummary>("/side/summary"),
        ]);
        draw(root);
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        root.innerHTML = `<div class="space-y-3 p-2">
          <h1 class="text-2xl font-semibold tracking-tight">Side Hustle</h1>
          <div class="card p-5 space-y-2">
            <div class="text-sm text-danger">Couldn't load side hustle data.</div>
            <div class="text-xs text-fg-muted">${esc(msg)}</div>
            <button id="s-retry" class="rounded-lg btn-accent px-3 py-1.5 text-sm w-fit">Retry</button>
          </div></div>`;
        $$(root, "#s-retry").forEach((b) => b.addEventListener("click", () => void this.render(root)));
      }
    },
  };

  function draw(root: HTMLElement) {
    if (!summary) return;
    const s = summary;

    root.innerHTML = `
      <div class="space-y-4 pb-6">
        <div class="flex items-start justify-between gap-3 px-2">
          <div>
            <h1 class="text-2xl font-semibold tracking-tight">Side Hustle</h1>
            <p class="text-sm text-fg-muted mt-1">Clips (engineering/robotics/PLC niche) · freelance · bridge income</p>
          </div>
          <a href="http://127.0.0.1:8000" target="_blank" class="shrink-0 text-xs accent-text hover:underline">Open Phantom Clips ↗</a>
        </div>

        ${statTiles(s)}

        <div class="grid grid-cols-1 lg:grid-cols-2 gap-3">
          ${targetsCard(s)}
          ${bridgeCard()}
        </div>

        ${formCard()}

        <div class="card overflow-x-auto">
          <table class="w-full text-sm">
            <thead><tr class="text-left text-[11px] uppercase tracking-wide text-fg-faint">
              <th class="py-2 px-3 font-normal">Date</th><th class="py-2 pr-3 font-normal">Source</th>
              <th class="py-2 pr-3 font-normal">Platform</th><th class="py-2 pr-3 font-normal text-right">Posts</th>
              <th class="py-2 pr-3 font-normal text-right">Followers</th><th class="py-2 pr-3 font-normal text-right">Views</th>
              <th class="py-2 pr-3 font-normal text-right">Revenue</th><th class="py-2 pr-3 font-normal">Note</th>
              <th class="py-2 pr-3 font-normal"></th>
            </tr></thead>
            <tbody>${tableRows() || `<tr><td class="p-4 text-fg-muted" colspan="9">No entries yet.</td></tr>`}</tbody>
          </table>
        </div>

        ${followersTrend()}
      </div>`;

    wire(root);
  }

  function statTiles(s: SideSummary): string {
    const followersSum = Object.values(s.latest_followers).reduce((a, f) => a + f.followers, 0);
    const chips = Object.entries(s.latest_followers)
      .map(([platform, f]) => `<span class="rounded-full border border-line px-2 py-0.5 text-[10px] text-fg-muted">${esc(platform)} ${f.followers}</span>`)
      .join("");
    return `<div class="grid grid-cols-2 md:grid-cols-4 gap-3">
      <div class="card p-4"><div class="text-xs uppercase tracking-wide text-fg-faint">Posts MTD</div><div class="mt-1 text-3xl font-semibold nums">${s.posts_mtd}</div></div>
      <div class="card p-4"><div class="text-xs uppercase tracking-wide text-fg-faint">Streak</div><div class="mt-1 text-3xl font-semibold nums">${s.streak_days}<span class="text-sm text-fg-faint"> d</span></div></div>
      <div class="card p-4"><div class="text-xs uppercase tracking-wide text-fg-faint">Revenue MTD</div><div class="mt-1 text-3xl font-semibold nums text-positive">$${s.revenue_mtd.toFixed(0)}</div></div>
      <div class="card p-4"><div class="text-xs uppercase tracking-wide text-fg-faint">Followers</div><div class="mt-1 text-3xl font-semibold nums">${followersSum}</div>
        ${chips ? `<div class="mt-2 flex flex-wrap gap-1">${chips}</div>` : ""}</div>
    </div>`;
  }

  function targetsCard(s: SideSummary): string {
    const postsPct = Math.min(100, (s.posts_total / 30) * 100);
    const maxFollowers = Math.max(0, ...Object.values(s.latest_followers).map((f) => f.followers));
    const followersPct = Math.min(100, (maxFollowers / 1000) * 100);
    const revenuePct = s.revenue_total > 0 ? 100 : 0;
    const row = (label: string, pct: number) => `<div>
      <div class="flex items-center justify-between text-xs text-fg-muted mb-1"><span>${esc(label)}</span><span class="nums">${Math.round(pct)}%</span></div>
      ${progressBar(pct)}
    </div>`;
    return `<div class="card p-4 space-y-3">
      <div class="text-sm font-medium">Targets</div>
      ${row("30 posts by Oct 10", postsPct)}
      ${row("1k followers on one platform", followersPct)}
      ${row("First side-revenue dollar by Nov 1", revenuePct)}
    </div>`;
  }

  function bridgeCard(): string {
    return `<div class="card p-4 space-y-2">
      <div class="text-sm font-medium">Bridge income</div>
      <p class="text-sm text-fg-muted">Bridge-income gate (set in Settings): if no interviews are scheduled by then, line up part-time contract work through engineering staffing agencies while the search continues.</p>
      <a href="#/settings" class="text-xs accent-text hover:underline">Flip bridge mode in Settings →</a>
    </div>`;
  }

  function formCard(): string {
    const today = localIso();
    return `<div class="card p-4 space-y-3">
      <div class="text-sm font-medium">Log an entry</div>
      <div class="grid grid-cols-2 md:grid-cols-4 gap-2">
        <input data-f-date type="date" value="${today}" class="bg-ink-800 rounded-lg px-3 py-1.5 text-sm" />
        <select data-f-source class="bg-ink-800 rounded-lg px-3 py-1.5 text-sm">
          <option value="clips">Clips</option>
          <option value="freelance">Freelance</option>
          <option value="bridge">Bridge</option>
          <option value="other">Other</option>
        </select>
        <select data-f-platform class="bg-ink-800 rounded-lg px-3 py-1.5 text-sm">
          <option value="tiktok">TikTok</option>
          <option value="youtube">YouTube</option>
          <option value="instagram">Instagram</option>
          <option value="x">X</option>
          <option value="upwork">Upwork</option>
          <option value="other">Other</option>
        </select>
        <input data-f-note type="text" placeholder="Note…" class="bg-ink-800 rounded-lg px-3 py-1.5 text-sm" />
        <input data-f-posts type="number" min="0" placeholder="Posts" class="bg-ink-800 rounded-lg px-3 py-1.5 text-sm" />
        <input data-f-followers type="number" min="0" placeholder="Followers" class="bg-ink-800 rounded-lg px-3 py-1.5 text-sm" />
        <input data-f-views type="number" min="0" placeholder="Views" class="bg-ink-800 rounded-lg px-3 py-1.5 text-sm" />
        <input data-f-revenue type="number" min="0" step="0.01" placeholder="Revenue $" class="bg-ink-800 rounded-lg px-3 py-1.5 text-sm" />
      </div>
      <button data-f-submit class="rounded-lg btn-accent px-3 py-1.5 text-sm">Log</button>
    </div>`;
  }

  function tableRows(): string {
    return entries.map((e) => `<tr data-row="${esc(e.id)}" class="border-t border-line">
      <td class="py-2 px-3 nums text-fg-muted whitespace-nowrap">${esc(e.date)}</td>
      <td class="py-2 pr-3">${esc(e.source)}</td>
      <td class="py-2 pr-3 text-fg-muted">${esc(e.platform ?? "—")}</td>
      <td class="py-2 pr-3 nums text-right">${e.posts}</td>
      <td class="py-2 pr-3 nums text-right">${e.followers}</td>
      <td class="py-2 pr-3 nums text-right">${e.views}</td>
      <td class="py-2 pr-3 nums text-right">$${e.revenue.toFixed(2)}</td>
      <td class="py-2 pr-3 text-fg-muted max-w-[16rem] truncate">${esc(e.note ?? "")}</td>
      <td class="py-2 pr-3 text-right"><button data-del="${esc(e.id)}" class="text-fg-faint hover:text-danger text-xs">✕</button></td>
    </tr>`).join("");
  }

  function sparkline(values: number[]): string {
    if (values.length < 2) return `<div class="h-[60px] grid place-items-center text-[11px] text-fg-faint">Not enough data yet</div>`;
    const w = 200, h = 60, pad = 4;
    const min = Math.min(...values), max = Math.max(...values);
    const range = max - min || 1;
    const step = (w - pad * 2) / (values.length - 1);
    const points = values.map((v, i) => {
      const x = pad + i * step;
      const y = h - pad - ((v - min) / range) * (h - pad * 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(" ");
    return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" class="block w-full" style="height:${h}px">
      <polyline points="${points}" fill="none" stroke="var(--accent)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>`;
  }

  function followersTrend(): string {
    const byPlatform = new Map<string, { date: string; followers: number }[]>();
    for (const e of entries) {
      if (!e.platform || !e.followers) continue;
      const arr = byPlatform.get(e.platform) ?? [];
      arr.push({ date: e.date, followers: e.followers });
      byPlatform.set(e.platform, arr);
    }
    const cards = [...byPlatform.entries()].map(([platform, pts]) => {
      const sorted = [...pts].sort((a, b) => a.date.localeCompare(b.date));
      return `<div class="card p-3">
        <div class="text-xs text-fg-faint mb-1">${esc(platform)}</div>
        ${sparkline(sorted.map((p) => p.followers))}
      </div>`;
    }).join("");
    if (!cards) return "";
    return `<div>
      <div class="text-sm text-fg-muted px-2 mb-2">Followers trend</div>
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">${cards}</div>
    </div>`;
  }

  async function refresh(root: HTMLElement) {
    const [e, sum] = await Promise.all([
      api<SideEntry[]>("/side?limit=30").catch(() => entries),
      api<SideSummary>("/side/summary").catch(() => summary),
    ]);
    entries = e;
    summary = sum;
    draw(root);
  }

  async function submitEntry(root: HTMLElement) {
    const date = ($(root, "[data-f-date]") as HTMLInputElement).value || localIso();
    const source = ($(root, "[data-f-source]") as HTMLSelectElement).value as SideSource;
    const platform = ($(root, "[data-f-platform]") as HTMLSelectElement).value || null;
    const posts = Number(($(root, "[data-f-posts]") as HTMLInputElement).value) || 0;
    const followers = Number(($(root, "[data-f-followers]") as HTMLInputElement).value) || 0;
    const views = Number(($(root, "[data-f-views]") as HTMLInputElement).value) || 0;
    const revenue = Number(($(root, "[data-f-revenue]") as HTMLInputElement).value) || 0;
    const note = ($(root, "[data-f-note]") as HTMLInputElement).value.trim() || null;
    const r = await tryApi<SideEntry>("/side", {
      method: "POST",
      body: JSON.stringify({ date, source, platform, posts, followers, views, revenue, note }),
    });
    if (!r.ok) { alert(`Could not log entry: ${r.error}`); return; }
    await refresh(root);
  }

  async function deleteEntry(root: HTMLElement, id: string) {
    const r = await tryApi(`/side/${id}`, { method: "DELETE" });
    if (!r.ok) { alert(`Could not delete entry: ${r.error}`); return; }
    await refresh(root);
  }

  function wire(root: HTMLElement) {
    $(root, "[data-f-submit]")?.addEventListener("click", () => submitEntry(root));
    $$(root, "[data-del]").forEach((b) => b.addEventListener("click", () => deleteEntry(root, b.dataset.del!)));
  }
}

function localIso(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
