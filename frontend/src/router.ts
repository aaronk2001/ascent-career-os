import { enter, initMagnetics } from "./motion";
import { modules, type Modules } from "./modules";
import { esc } from "./ui";

export type View = {
  render: (root: HTMLElement) => void | Promise<void>;
  cleanup?: () => void;
};

type ViewModule = { default: () => View };

const routes: Record<string, () => Promise<ViewModule>> = {
  today: () => import("./views/today"),
  dashboard: () => import("./views/dashboard"),
  focus: () => import("./views/focus"),
  applications: () => import("./views/applications"),
  links: () => import("./views/links"),
  side: () => import("./views/side"),
  health: () => import("./views/health"),
  tracks: () => import("./views/learning"),
  skills: () => import("./views/skills"),
  roadmap: () => import("./views/roadmap"),
  projects: () => import("./views/projects"),
  certs: () => import("./views/certs"),
  glossary: () => import("./views/glossary"),
  timeline: () => import("./views/timeline"),
  linda: () => import("./views/linda"),
  settings: () => import("./views/settings"),
};

// Nav entries owned by an optional module; hidden while that module is off.
const NAV_MODULE: Partial<Record<string, keyof Modules>> = { side: "side", health: "health" };

/** NAV minus entries whose module is switched off. */
export function navItems() {
  const on = modules();
  return NAV.filter((n) => { const m = NAV_MODULE[n.id]; return !m || on[m]; });
}

export const NAV: { id: string; label: string; icon: string }[] = [
  { id: "today", label: "Today", icon: "M3 5h18v16H3zM3 9h18M8 3v4M16 3v4M8 14h3v3H8z" },
  { id: "dashboard", label: "Dashboard", icon: "M3 12l9-9 9 9M5 10v10h5v-6h4v6h5V10" },
  { id: "focus", label: "Focus", icon: "M12 2v4M12 18v4M2 12h4M18 12h4M12 7a5 5 0 100 10 5 5 0 000-10z" },
  { id: "applications", label: "Applications", icon: "M3 7h18M3 12h18M3 17h18" },
  { id: "links", label: "Profile Links", icon: "M10 13a5 5 0 007 0l3-3a5 5 0 00-7-7l-1 1M14 11a5 5 0 00-7 0l-3 3a5 5 0 007 7l1-1" },
  { id: "side", label: "Side Hustle", icon: "M12 2v20M17 6H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6" },
  { id: "health", label: "Health", icon: "M20.8 5.6a5.5 5.5 0 00-7.8 0l-1 1-1-1a5.5 5.5 0 00-7.8 7.8l8.8 8.8 8.8-8.8a5.5 5.5 0 000-7.8z" },
  { id: "tracks", label: "Learning", icon: "M12 3L2 8l10 5 10-5-10-5zM2 13l10 5 10-5" },
  { id: "skills", label: "Skills", icon: "M13 2L3 14h7l-1 8 10-12h-7l1-8z" },
  { id: "roadmap", label: "Roadmap", icon: "M3 6l6-2 6 2 6-2v14l-6 2-6-2-6 2zM9 4v14M15 6v14" },
  { id: "projects", label: "Projects", icon: "M3 7h6l2 2h10v10H3zM3 7V5h6l2 2" },
  { id: "certs", label: "Certifications", icon: "M12 2a7 7 0 100 14 7 7 0 000-14zM8 14l-2 8 6-3 6 3-2-8" },
  { id: "glossary", label: "Glossary", icon: "M4 19.5A2.5 2.5 0 016.5 17H20M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z" },
  { id: "timeline", label: "Timeline", icon: "M3 12h4l3-9 4 18 3-9h4" },
  { id: "linda", label: "Linda", icon: "M12 2a5 5 0 015 5v3a5 5 0 01-10 0V7a5 5 0 015-5zM5 11a7 7 0 0014 0M12 18v3" },
  { id: "settings", label: "Settings", icon: "M12 8a4 4 0 100 8 4 4 0 000-8zM2 12h3M19 12h3M12 2v3M12 19v3" },
];

const DEFAULT = "today";

export function currentRoute(): string {
  return location.hash.replace(/^#\/?/, "").split("?")[0] || DEFAULT;
}

export function routeParam(name: string): string | null {
  const q = location.hash.split("?")[1];
  return q ? new URLSearchParams(q).get(name) : null;
}

export function startRouter(root: HTMLElement, onChange?: (id: string) => void) {
  let active: View | undefined;

  async function resolve() {
    const id = currentRoute();
    onChange?.(id);
    active?.cleanup?.();
    root.replaceChildren();
    const loader = Object.hasOwn(routes, id) ? routes[id] : undefined;
    if (!loader) {
      root.innerHTML = `<div class="p-8 text-fg-muted">Coming in a later phase: <span class="text-fg">${esc(id)}</span></div>`;
      return;
    }
    active = (await loader()).default();
    await active.render(root);
    enter(root);
    initMagnetics(root);
  }

  addEventListener("hashchange", resolve);
  void resolve();
}
