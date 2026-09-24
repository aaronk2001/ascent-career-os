import { NAV } from "./router";
import { api } from "./api";
import { esc } from "./ui";
import { getPrefs, setPrefs } from "./prefs";

type Cmd = { label: string; group: string; hint?: string; run: () => void };

export function mountCommandPalette() {
  const overlay = document.createElement("div");
  overlay.className = "fixed inset-0 z-[60] bg-black/50 backdrop-blur-sm opacity-0 pointer-events-none transition-opacity duration-200 grid place-items-start justify-center pt-[14vh]";
  overlay.innerHTML = `
    <div id="cmdk" class="glass w-[560px] max-w-[92vw] p-2 scale-95 transition-transform duration-200">
      <div class="flex items-center gap-2 px-2 py-1.5 border-b border-line">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-fg-faint"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4-4"/></svg>
        <input id="cmdk-input" placeholder="Search or jump to…" class="flex-1 bg-transparent text-sm py-1 focus:outline-none" />
        <span class="text-[10px] rounded bg-ink-800 px-1.5 py-0.5 text-fg-faint">esc</span>
      </div>
      <div id="cmdk-list" class="mt-1 max-h-[50vh] overflow-y-auto"></div>
    </div>`;
  document.body.append(overlay);

  const panel = overlay.querySelector<HTMLElement>("#cmdk")!;
  const input = overlay.querySelector<HTMLInputElement>("#cmdk-input")!;
  const list = overlay.querySelector<HTMLElement>("#cmdk-list")!;

  let isOpen = false;
  let appCmds: Cmd[] = [];
  let filtered: Cmd[] = [];
  let sel = 0;

  const base = (): Cmd[] => [
    ...NAV.map((n) => ({ label: `Go to ${n.label}`, group: "Navigate", run: () => (location.hash = `#/${n.id}`) })),
    { label: "Today's plan", group: "Actions", run: () => (location.hash = "#/today") },
    { label: "Log clips / side revenue", group: "Actions", run: () => (location.hash = "#/side") },
    { label: "Profile links checklist", group: "Actions", run: () => (location.hash = "#/links") },
    { label: "Add application", group: "Actions", run: () => (location.hash = "#/applications") },
    { label: "Ask Linda", group: "Actions", run: () => (location.hash = "#/linda") },
    { label: "Open Customize", group: "Actions", run: () => dispatchEvent(new Event("ascent:customize")) },
    { label: `Motion: turn ${getPrefs().motion ? "off" : "on"}`, group: "Actions", run: () => setPrefs({ motion: !getPrefs().motion }) },
  ];

  function score(q: string, text: string): number {
    const t = text.toLowerCase();
    q = q.toLowerCase();
    if (!q) return 1;
    if (t.includes(q)) return 2 - t.indexOf(q) / 100;
    // subsequence match
    let i = 0;
    for (const ch of t) if (ch === q[i]) i++;
    return i === q.length ? 0.5 : 0;
  }

  function render() {
    const q = input.value.trim();
    const all = [...base(), ...appCmds];
    filtered = all
      .map((c) => ({ c, s: score(q, c.label + " " + (c.hint ?? "")) }))
      .filter((x) => x.s > 0)
      .sort((a, b) => b.s - a.s)
      .map((x) => x.c)
      .slice(0, 40);
    if (sel >= filtered.length) sel = Math.max(0, filtered.length - 1);

    let html = "", group = "";
    filtered.forEach((c, i) => {
      if (c.group !== group) {
        group = c.group;
        html += `<div class="px-2 pt-2 pb-1 text-[10px] uppercase tracking-wide text-fg-faint">${esc(group)}</div>`;
      }
      html += `<div data-i="${i}" class="flex items-center gap-2 px-2 py-2 rounded-lg cursor-default text-sm ${i === sel ? "bg-ink-800 text-fg" : "text-fg-muted"}">
        <span class="flex-1">${esc(c.label)}</span>${c.hint ? `<span class="text-[11px] text-fg-faint">${esc(c.hint)}</span>` : ""}</div>`;
    });
    list.innerHTML = html || `<div class="px-2 py-6 text-center text-sm text-fg-faint">No matches</div>`;
    list.querySelectorAll<HTMLElement>("[data-i]").forEach((el) =>
      el.addEventListener("click", () => choose(Number(el.dataset.i))));
  }

  function choose(i: number) {
    const c = filtered[i];
    if (!c) return;
    close();
    c.run();
  }

  async function open() {
    if (isOpen) return;
    isOpen = true;
    overlay.classList.remove("opacity-0", "pointer-events-none");
    panel.classList.remove("scale-95");
    input.value = "";
    sel = 0;
    render();
    input.focus();
    if (!appCmds.length) {
      try {
        const apps = await api<{ company: string; role: string; status: string }[]>("/applications");
        appCmds = apps.map((a) => ({ label: `${a.company} · ${a.role}`, hint: a.status, group: "Applications", run: () => (location.hash = "#/applications") }));
        if (isOpen) render();
      } catch {
        /* offline ok */
      }
    }
  }
  function close() {
    isOpen = false;
    overlay.classList.add("opacity-0", "pointer-events-none");
    panel.classList.add("scale-95");
  }

  input.addEventListener("input", () => { sel = 0; render(); });
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); sel = Math.min(sel + 1, filtered.length - 1); render(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); sel = Math.max(sel - 1, 0); render(); }
    else if (e.key === "Enter") { e.preventDefault(); choose(sel); }
    else if (e.key === "Escape") close();
  });
  overlay.addEventListener("click", (e) => { if (e.target === overlay) close(); });
  addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); isOpen ? close() : void open(); }
  });
  addEventListener("ascent:cmdk", () => void open());
}
