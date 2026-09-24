export type WidgetPref = { id: string; span: number; hidden: boolean };

export type Prefs = {
  accent: string;
  accent2: string;
  accentName: string;
  density: "comfortable" | "compact";
  motion: boolean;
  navOrder: string[];
  hidden: string[];
  widgets: WidgetPref[];
  font: "system" | "mono" | "serif";
  card: "glass" | "solid" | "outline";
  radius: number;
  glow: boolean;
  aurora: number;
  particles: boolean;
  globe: boolean;
};

export const ACCENTS: { name: string; a: string; b: string }[] = [
  { name: "Indigo", a: "#6366f1", b: "#8b5cf6" },
  { name: "Cyan", a: "#22d3ee", b: "#6366f1" },
  { name: "Magenta", a: "#8b5cf6", b: "#e879f9" },
  { name: "Emerald", a: "#10b981", b: "#22d3ee" },
];

const KEY = "ascent:prefs";
const DEFAULTS: Prefs = {
  accent: "#6366f1",
  accent2: "#8b5cf6",
  accentName: "Indigo",
  density: "comfortable",
  motion: true,
  navOrder: [],
  hidden: [],
  widgets: [],
  font: "system",
  card: "glass",
  radius: 18,
  glow: true,
  aurora: 1,
  particles: true,
  globe: true,
};

function load(): Prefs {
  try {
    return { ...DEFAULTS, ...(JSON.parse(localStorage.getItem(KEY) || "{}") as Partial<Prefs>) };
  } catch {
    return { ...DEFAULTS };
  }
}

let prefs: Prefs = load();
const subs = new Set<(p: Prefs) => void>();

export function getPrefs(): Prefs {
  return prefs;
}

export function setPrefs(patch: Partial<Prefs>) {
  prefs = { ...prefs, ...patch };
  localStorage.setItem(KEY, JSON.stringify(prefs));
  apply();
  for (const f of subs) f(prefs);
}

export function resetPrefs() {
  prefs = { ...DEFAULTS };
  localStorage.removeItem(KEY);
  apply();
  for (const f of subs) f(prefs);
}

export function onPrefs(f: (p: Prefs) => void): () => void {
  subs.add(f);
  return () => {
    subs.delete(f);
  };
}

export function apply() {
  const r = document.documentElement;
  r.style.setProperty("--accent", prefs.accent);
  r.style.setProperty("--accent-2", prefs.accent2);
  r.style.fontSize = prefs.density === "compact" ? "14.5px" : "16px";
  r.style.setProperty("--radius-card", `${prefs.radius}px`);
  r.style.setProperty("--aurora-opacity", String(prefs.aurora));
  r.classList.toggle("no-motion", !prefs.motion);
  r.classList.toggle("no-glow", !prefs.glow);
  r.dataset.font = prefs.font;
  r.dataset.card = prefs.card;
}

/** NAV ids in the user's saved order, hidden ones removed. `allIds` is the full set. */
export function orderedVisible(allIds: string[]): string[] {
  const order = prefs.navOrder.filter((id) => allIds.includes(id));
  for (const id of allIds) if (!order.includes(id)) order.push(id);
  return order.filter((id) => id === "dashboard" || !prefs.hidden.includes(id));
}
