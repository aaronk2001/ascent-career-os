import type { GlobeMarker } from "./globe";

type App = { company: string; role?: string | null; status: string };

const CITIES: Record<string, [number, number]> = {
  phoenix: [33.45, -112.07],
  tempe: [33.42, -111.94],
  chandler: [33.3, -111.84],
  scottsdale: [33.49, -111.92],
  boston: [42.36, -71.06],
  reston: [38.96, -77.36],
  wallingford: [41.46, -72.82],
  seattle: [47.61, -122.33],
  sf: [37.77, -122.42],
  austin: [30.27, -97.74],
  nyc: [40.71, -74.0],
};

// Curated company → site/HQ city. Defaults to Phoenix metro (default target region).
const COMPANY_CITY: [RegExp, string][] = [
  [/tsmc/i, "phoenix"],
  [/honeywell/i, "phoenix"],
  [/amphenol/i, "wallingford"],
  [/general dynamics/i, "reston"],
  [/amazon/i, "boston"],
  [/symbotic/i, "boston"],
];

const STATUS_COLOR: Record<string, string> = {
  offer: "#10b981",
  onsite: "#22d3ee",
  technical: "#22d3ee",
  phone_screen: "#818cf8",
  applied: "#818cf8",
  discovered: "#a78bfa",
  rejected: "#4b5170",
};

function cityFor(company: string): string {
  for (const [re, city] of COMPANY_CITY) if (re.test(company)) return city;
  return "phoenix";
}

export function appMarkers(apps: App[]): GlobeMarker[] {
  const count: Record<string, number> = {};
  return apps.map((a) => {
    const city = cityFor(a.company);
    const base = CITIES[city] ?? CITIES.phoenix;
    const i = (count[city] = (count[city] ?? 0) + 1) - 1;
    // spiral-jitter stacked markers so co-located companies don't overlap
    const ang = i * 2.4;
    const rad = i ? 0.9 + i * 0.4 : 0;
    return {
      lat: base[0] + Math.sin(ang) * rad,
      lon: base[1] + Math.cos(ang) * rad,
      label: `${a.company}${a.role ? " · " + a.role : ""}`,
      color: STATUS_COLOR[a.status] ?? "#818cf8",
    };
  });
}
