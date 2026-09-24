import type { GlobeHome, GlobeMarker } from "./globe";

type App = { company: string; role?: string | null; status: string; location?: string | null };

// Coarse lookup: the first known city/metro named in an application's location
// text. No network geocoding; unknown or remote locations fall back to the user's
// most common known city so their markers still cluster "at home".
const CITIES: Record<string, [number, number]> = {
  // Front Range
  denver: [39.74, -104.99], aurora: [39.73, -104.83], boulder: [40.01, -105.27], golden: [39.76, -105.22],
  lakewood: [39.7, -105.08], englewood: [39.65, -104.99], littleton: [39.61, -105.02],
  "colorado springs": [38.83, -104.82], "fort collins": [40.59, -105.08],
  // Southwest
  phoenix: [33.45, -112.07], tempe: [33.42, -111.94], chandler: [33.3, -111.84], scottsdale: [33.49, -111.92],
  mesa: [33.42, -111.83], gilbert: [33.35, -111.79], glendale: [33.54, -112.19], tucson: [32.22, -110.97],
  albuquerque: [35.08, -106.65], "las vegas": [36.17, -115.14], "salt lake": [40.76, -111.89],
  // Other US metros
  seattle: [47.61, -122.33], portland: [45.52, -122.68], "san francisco": [37.77, -122.42],
  "san jose": [37.34, -121.89], "los angeles": [34.05, -118.24], "san diego": [32.72, -117.16],
  austin: [30.27, -97.74], dallas: [32.78, -96.8], houston: [29.76, -95.37], chicago: [41.88, -87.63],
  detroit: [42.33, -83.05], pittsburgh: [40.44, -80], atlanta: [33.75, -84.39], boston: [42.36, -71.06],
  "new york": [40.71, -74], reston: [38.96, -77.36], raleigh: [35.78, -78.64], minneapolis: [44.98, -93.27],
};

const STATUS_COLOR: Record<string, string> = {
  offer: "#10b981",
  onsite: "#22d3ee",
  technical: "#22d3ee",
  phone_screen: "#818cf8",
  applied: "#818cf8",
  discovered: "#a78bfa",
  rejected: "#4b5170",
};

function cityFor(location?: string | null): string | null {
  const loc = (location || "").toLowerCase();
  return Object.keys(CITIES).find((c) => loc.includes(c)) ?? null;
}

function homeCity(known: (string | null)[]): string | undefined {
  const tally: Record<string, number> = {};
  for (const c of known) if (c) tally[c] = (tally[c] ?? 0) + 1;
  return Object.entries(tally).sort((a, b) => b[1] - a[1])[0]?.[0];
}

/** The most common known city across applications: the globe's "home" pin. */
export function appHome(apps: App[]): GlobeHome | undefined {
  const c = homeCity(apps.map((a) => cityFor(a.location)));
  return c ? { name: c.replace(/\b\w/g, (ch) => ch.toUpperCase()), lat: CITIES[c][0], lon: CITIES[c][1] } : undefined;
}

export function appMarkers(apps: App[]): GlobeMarker[] {
  const known = apps.map((a) => cityFor(a.location));
  const home = homeCity(known);
  const count: Record<string, number> = {};
  return apps.flatMap((a, idx) => {
    const city = known[idx] ?? home;
    if (!city) return [];
    const base = CITIES[city];
    const i = (count[city] = (count[city] ?? 0) + 1) - 1;
    // spiral-jitter stacked markers so co-located companies don't overlap
    const ang = i * 2.4;
    const rad = i ? 0.9 + i * 0.4 : 0;
    return [{
      lat: base[0] + Math.sin(ang) * rad,
      lon: base[1] + Math.cos(ang) * rad,
      label: `${a.company}${a.role ? " · " + a.role : ""}`,
      color: STATUS_COLOR[a.status] ?? "#818cf8",
    }];
  });
}
