import { api } from "./api";
import { esc } from "./ui";

type Reminder = {
  id: string;
  kind: string;
  title: string;
  body?: string | null;
  due?: string | null;
  read: number;
  dismissed: number;
};

const KIND_DOT: Record<string, string> = {
  deadline: "bg-warn",
  followup: "bg-brand-500",
  followup_missing: "bg-brand-500",
  cadence: "bg-violet-500",
};

export function mountNotifications(host: HTMLElement) {
  const wrap = document.createElement("div");
  wrap.className = "relative";
  wrap.innerHTML = `
    <button id="bell" class="relative rounded-lg p-2 text-fg-muted hover:text-fg hover:bg-ink-800 transition-colors" aria-label="Notifications">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/></svg>
      <span id="badge" class="hidden absolute top-0 right-0 min-w-[16px] h-4 px-1 rounded-full bg-danger text-[10px] leading-4 text-center nums text-white"></span>
    </button>
    <div id="panel" class="hidden absolute right-0 mt-2 w-80 max-h-[70vh] overflow-y-auto glass z-50 p-2 space-y-1"></div>`;
  host.append(wrap);

  const badge = wrap.querySelector<HTMLElement>("#badge")!;
  const panel = wrap.querySelector<HTMLElement>("#panel")!;
  let items: Reminder[] = [];

  function renderBadge() {
    const unread = items.filter((r) => !r.read).length;
    badge.classList.toggle("hidden", unread === 0);
    badge.textContent = String(unread);
  }

  function itemHtml(r: Reminder): string {
    const dot = KIND_DOT[r.kind] ?? "bg-fg-muted";
    return `<div class="flex gap-2 p-2 rounded-lg ${r.read ? "" : "bg-ink-800/50"}">
      <span class="mt-1.5 h-2 w-2 shrink-0 rounded-full ${dot}"></span>
      <div class="min-w-0 flex-1">
        <div class="text-sm">${esc(r.title)}</div>
        ${r.body ? `<div class="text-xs text-fg-muted">${esc(r.body)}</div>` : ""}
      </div>
      <button data-dismiss="${esc(r.id)}" class="text-fg-faint hover:text-danger text-xs shrink-0">✕</button>
    </div>`;
  }

  function renderPanel() {
    panel.innerHTML = items.length
      ? items.map(itemHtml).join("")
      : `<div class="p-4 text-sm text-fg-muted">No notifications.</div>`;
    panel.querySelectorAll<HTMLButtonElement>("[data-dismiss]").forEach((b) =>
      b.addEventListener("click", async (e) => {
        e.stopPropagation();
        const id = b.dataset.dismiss!;
        items = items.filter((r) => r.id !== id);
        renderBadge();
        renderPanel();
        await api(`/reminders/${id}`, { method: "PUT", body: JSON.stringify({ dismissed: true }) });
      }),
    );
  }

  async function markAllRead() {
    const unread = items.filter((r) => !r.read);
    for (const r of unread) r.read = 1;
    renderBadge();
    await Promise.all(
      unread.map((r) => api(`/reminders/${r.id}`, { method: "PUT", body: JSON.stringify({ read: true }) })),
    );
  }

  async function load() {
    items = await api<Reminder[]>("/reminders");
    renderBadge();
    if (!panel.classList.contains("hidden")) renderPanel();
  }

  wrap.querySelector<HTMLButtonElement>("#bell")!.addEventListener("click", () => {
    const nowHidden = panel.classList.toggle("hidden");
    if (!nowHidden) {
      renderPanel();
      void markAllRead();
    }
  });
  document.addEventListener("click", (e) => {
    if (!wrap.contains(e.target as Node)) panel.classList.add("hidden");
  });

  void load();
  setInterval(() => void load(), 60_000);
}

let toastHost: HTMLElement | null = null;

/** Transient bottom-right toast. tone: info | ok | err. */
export function toast(message: string, tone: "info" | "ok" | "err" = "info") {
  if (!toastHost) {
    toastHost = document.createElement("div");
    toastHost.className = "fixed bottom-4 right-4 z-[100] flex flex-col gap-2 items-end";
    document.body.append(toastHost);
  }
  const border = tone === "ok" ? "border-positive/50" : tone === "err" ? "border-danger/50" : "border-line-strong";
  const el = document.createElement("div");
  el.className = `glass border ${border} px-3 py-2 text-sm text-fg rounded-lg shadow-lg anim-fade-up`;
  el.textContent = message;
  toastHost.append(el);
  setTimeout(() => {
    el.style.transition = "opacity .3s";
    el.style.opacity = "0";
    setTimeout(() => el.remove(), 300);
  }, 2600);
}
