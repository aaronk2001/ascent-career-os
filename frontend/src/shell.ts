import { NAV, currentRoute } from "./router";
import { mountNotifications } from "./notifications";
import { mountCustomize } from "./customize";
import { slidePill } from "./motion";
import { orderedVisible, onPrefs } from "./prefs";

export function mountShell(app: HTMLElement): HTMLElement {
  app.className = "grid grid-cols-[244px_1fr] grid-rows-[100%] h-screen p-2 gap-2 overflow-hidden";

  // ── Sidebar ──────────────────────────────────────────────────────────────
  const sidebar = document.createElement("aside");
  sidebar.className = "glass flex flex-col p-3 overflow-hidden";

  const brand = document.createElement("div");
  brand.className = "flex items-center gap-2.5 px-2 py-2 mb-3";
  brand.innerHTML = `
    <div data-magnetic="0.4" class="grid place-items-center h-8 w-8 rounded-xl accent-bg glow shrink-0">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5" stroke-linejoin="round"><path d="M12 3l9 16H3z"/></svg>
    </div>
    <div class="leading-tight">
      <div class="text-base font-semibold tracking-tight">Ascent</div>
      <div class="text-[10px] uppercase tracking-[0.18em] text-fg-faint">Career OS</div>
    </div>`;
  sidebar.append(brand);

  const navWrap = document.createElement("nav");
  navWrap.className = "relative flex flex-col gap-0.5 flex-1";

  const pill = document.createElement("div");
  pill.className = "absolute left-0 right-0 top-0 rounded-lg accent-bg pointer-events-none";
  pill.style.height = "36px";
  pill.style.opacity = "0.16";
  pill.style.boxShadow = "0 0 0 1px color-mix(in oklab, var(--accent) 45%, transparent)";
  navWrap.append(pill);

  let links: HTMLAnchorElement[] = [];
  function renderNav() {
    for (const a of links) a.remove();
    links = [];
    const ids = orderedVisible(NAV.map((n) => n.id));
    for (const id of ids) {
      const item = NAV.find((n) => n.id === id)!;
      const a = document.createElement("a");
      a.href = `#/${item.id}`;
      a.dataset.route = item.id;
      a.className =
        "relative z-10 flex items-center gap-3 h-9 px-3 rounded-lg text-sm text-fg-muted hover:text-fg transition-colors";
      a.innerHTML = `<svg class="shrink-0" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="${item.icon}"/></svg><span>${item.label}</span>`;
      links.push(a);
      navWrap.append(a);
    }
    highlight(currentRoute());
  }

  sidebar.append(navWrap);

  const foot = document.createElement("div");
  foot.className = "px-2 pt-3";
  foot.innerHTML = `<div class="hairline mb-3"></div><div class="text-[11px] text-fg-faint">Ascent · Career OS</div>`;
  sidebar.append(foot);

  // ── Right column ───────────────────────────────────────────────────────────
  const right = document.createElement("div");
  right.className = "flex flex-col min-w-0 min-h-0";

  const topbar = document.createElement("header");
  topbar.className = "flex items-center gap-1.5 h-12 px-1 shrink-0";
  const search = document.createElement("button");
  search.className = "flex items-center gap-2 h-9 px-3 rounded-xl glass text-sm text-fg-faint hover:text-fg-muted transition-colors w-72 max-w-[40vw]";
  search.innerHTML = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4-4"/></svg><span>Search or jump to…</span><span class="ml-auto text-[10px] rounded bg-ink-800 px-1.5 py-0.5">⌘K</span>`;
  search.addEventListener("click", () => dispatchEvent(new Event("ascent:cmdk")));
  topbar.append(search, Object.assign(document.createElement("div"), { className: "flex-1" }));
  mountCustomize(topbar);
  mountNotifications(topbar);

  const main = document.createElement("main");
  main.className = "flex-1 min-h-0 overflow-y-auto pr-1";

  right.append(topbar, main);
  app.append(sidebar, right);

  function highlight(id: string) {
    const active = links.find((a) => a.dataset.route === id) ?? links[0];
    if (!active) return;
    for (const a of links) a.classList.toggle("text-fg", a === active);
    slidePill(pill, active, navWrap);
  }
  addEventListener("ascent:route", (e) => highlight((e as CustomEvent<string>).detail));
  onPrefs(renderNav);
  renderNav();

  return main;
}
