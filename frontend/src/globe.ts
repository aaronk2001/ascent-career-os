import * as THREE from "three";
import { feature } from "topojson-client";
import landTopo from "world-atlas/land-110m.json";

const RADIUS = 1.8;
const HOME = { name: "Phoenix", lat: 33.45, lon: -112.07 };

export type GlobeMarker = { lat: number; lon: number; label: string; color: string };

const AMBIENT: GlobeMarker[] = [
  { lat: 47.61, lon: -122.33, label: "Seattle", color: "#8b5cf6" },
  { lat: 37.77, lon: -122.42, label: "SF Bay", color: "#8b5cf6" },
  { lat: 30.27, lon: -97.74, label: "Austin", color: "#8b5cf6" },
  { lat: 42.36, lon: -71.06, label: "Boston", color: "#8b5cf6" },
  { lat: 40.71, lon: -74.0, label: "NYC", color: "#8b5cf6" },
];

function latLonToVec3(lat: number, lon: number, r: number): THREE.Vector3 {
  const phi = (90 - lat) * (Math.PI / 180);
  const theta = (lon + 180) * (Math.PI / 180);
  return new THREE.Vector3(
    -r * Math.sin(phi) * Math.cos(theta),
    r * Math.cos(phi),
    r * Math.sin(phi) * Math.sin(theta),
  );
}

function pointInRing(x: number, y: number, ring: number[][]): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const xi = ring[i][0], yi = ring[i][1];
    const xj = ring[j][0], yj = ring[j][1];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}
function pointOnLand(lon: number, lat: number, polygons: number[][][][]): boolean {
  for (const polygon of polygons) {
    if (pointInRing(lon, lat, polygon[0])) {
      let inHole = false;
      for (let h = 1; h < polygon.length; h++) if (pointInRing(lon, lat, polygon[h])) { inHole = true; break; }
      if (!inHole) return true;
    }
  }
  return false;
}
function landCoords(): number[][][][] {
  const topo = landTopo as unknown as { objects: { land: unknown } };
  const result = feature(topo as never, topo.objects.land as never) as unknown as {
    type: string;
    geometry?: { type: string; coordinates: number[][][][] };
    features?: { geometry: { type: string; coordinates: number[][][][] } }[];
  };
  const geo = result.type === "FeatureCollection" ? result.features?.[0]?.geometry : result.geometry;
  if (!geo) return [];
  return geo.type === "Polygon" ? [geo.coordinates as unknown as number[][][]] : geo.coordinates;
}

function buildLandDots(coords: number[][][][]): THREE.Points {
  const positions: number[] = [];
  const step = 1.5;
  for (let lat = -80; lat <= 80; lat += step) {
    const cosLat = Math.cos((lat * Math.PI) / 180);
    const lonStep = cosLat > 0.1 ? step / cosLat : step * 5;
    for (let lon = -180; lon < 180; lon += Math.min(lonStep, step * 4)) {
      if (pointOnLand(lon, lat, coords)) {
        const p = latLonToVec3(lat, lon, RADIUS + 0.008);
        positions.push(p.x, p.y, p.z);
      }
    }
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  return new THREE.Points(geo, new THREE.PointsMaterial({ color: "#a5b4fc", size: 0.026, transparent: true, opacity: 0.9, sizeAttenuation: true }));
}
function buildOutlines(coords: number[][][][]): THREE.Group {
  const g = new THREE.Group();
  const mat = new THREE.LineBasicMaterial({ color: "#6366f1", transparent: true, opacity: 0.18 });
  for (const polygon of coords) for (const ring of polygon) {
    if (ring.length < 4) continue;
    g.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(ring.map(([lon, lat]) => latLonToVec3(lat, lon, RADIUS + 0.005))), mat));
  }
  return g;
}
function buildArc(from: THREE.Vector3, to: THREE.Vector3): THREE.Line {
  const mid = new THREE.Vector3().addVectors(from, to).multiplyScalar(0.5);
  mid.normalize().multiplyScalar(RADIUS * 1.5);
  const pts = new THREE.QuadraticBezierCurve3(from, mid, to).getPoints(48);
  return new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({ color: "#a78bfa", transparent: true, opacity: 0.3 }));
}

type Pulse = { mesh: THREE.Mesh; ring: THREE.Mesh; seed: number };

function buildMarker(pos: THREE.Vector3, color: string, label: string, home: boolean): { group: THREE.Group; pulse: Pulse; hit: THREE.Mesh } {
  const group = new THREE.Group();
  group.position.copy(pos);
  const mesh = new THREE.Mesh(new THREE.SphereGeometry(home ? 0.05 : 0.034, 14, 14), new THREE.MeshBasicMaterial({ color }));
  mesh.userData.label = label;
  const ring = new THREE.Mesh(new THREE.RingGeometry(home ? 0.07 : 0.052, home ? 0.1 : 0.075, 28), new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.35, side: THREE.DoubleSide }));
  ring.lookAt(new THREE.Vector3(0, 0, 0));
  const light = new THREE.PointLight(color, home ? 0.9 : 0.5, 0.9, 2);
  group.add(mesh, ring, light);
  return { group, pulse: { mesh, ring, seed: pos.x * 5 + pos.y * 3 }, hit: mesh };
}

export function createGlobe(container: HTMLElement, opts: { markers?: GlobeMarker[] } = {}): () => void {
  const w = container.clientWidth || 600;
  const h = container.clientHeight || 420;

  let renderer: THREE.WebGLRenderer;
  try {
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    if (!renderer.getContext()) throw new Error("no webgl context");
  } catch {
    // WebGL unavailable — degrade to a static CSS globe so the hero isn't blank.
    const fallback = document.createElement("div");
    fallback.className = "absolute inset-0";
    fallback.style.background =
      "radial-gradient(circle at 68% 46%, color-mix(in oklab, var(--accent) 34%, transparent), color-mix(in oklab, var(--accent-2) 18%, transparent) 38%, transparent 62%)";
    container.appendChild(fallback);
    return () => fallback.remove();
  }
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.setSize(w, h);
  container.appendChild(renderer.domElement);

  const tip = document.createElement("div");
  tip.className = "pointer-events-none absolute z-10 hidden rounded-md bg-ink-800 border border-line px-2 py-1 text-[11px] text-fg whitespace-nowrap";
  container.appendChild(tip);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(38, w / h, 0.1, 100);
  camera.position.set(0, 0.25, 4.85);
  scene.add(new THREE.AmbientLight(0xffffff, 0.25));
  const dir = new THREE.DirectionalLight(0x93c5fd, 0.35);
  dir.position.set(5, 3, 5);
  scene.add(dir);

  const globe = new THREE.Group();
  globe.rotation.x = 0.35;
  scene.add(globe);

  for (const [r, col, op] of [[1.18, 0x4f46e5, 0.05], [1.06, 0x6366f1, 0.07]] as const)
    globe.add(new THREE.Mesh(new THREE.SphereGeometry(RADIUS * r, 48, 48), new THREE.MeshBasicMaterial({ color: col, transparent: true, opacity: op, side: THREE.BackSide, blending: THREE.AdditiveBlending })));
  globe.add(new THREE.Mesh(new THREE.SphereGeometry(RADIUS, 36, 18), new THREE.MeshBasicMaterial({ color: 0x312e81, wireframe: true, transparent: true, opacity: 0.1 })));
  globe.add(new THREE.Mesh(new THREE.SphereGeometry(RADIUS - 0.01, 48, 48), new THREE.MeshStandardMaterial({ color: 0x070713, roughness: 0.95, metalness: 0.05 })));

  const coords = landCoords();
  globe.add(buildLandDots(coords));
  globe.add(buildOutlines(coords));

  const pulses: Pulse[] = [];
  const pickable: THREE.Mesh[] = [];
  const homePos = latLonToVec3(HOME.lat, HOME.lon, RADIUS + 0.02);
  const home = buildMarker(homePos, "#a5b4fc", `${HOME.name} (home)`, true);
  globe.add(home.group);
  pulses.push(home.pulse);
  pickable.push(home.hit);

  const data = opts.markers?.length ? opts.markers : AMBIENT;
  for (const m of data) {
    const pos = latLonToVec3(m.lat, m.lon, RADIUS + 0.02);
    const mk = buildMarker(pos, m.color, m.label, false);
    globe.add(mk.group);
    pulses.push(mk.pulse);
    pickable.push(mk.hit);
    if (pos.distanceTo(homePos) > 0.08) globe.add(buildArc(homePos, pos));
  }

  // Pointer parallax + raycast hover
  const ray = new THREE.Raycaster();
  const ndc = new THREE.Vector2();
  let targetX = 0, targetY = 0, px = -1, py = -1;
  const onMove = (e: PointerEvent) => {
    const r = container.getBoundingClientRect();
    px = e.clientX - r.left;
    py = e.clientY - r.top;
    targetX = (px / r.width - 0.5) * 0.5;
    targetY = (py / r.height - 0.5) * 0.3;
    ndc.x = (px / r.width) * 2 - 1;
    ndc.y = -(py / r.height) * 2 + 1;
  };
  const onLeave = () => { px = -1; tip.classList.add("hidden"); };
  container.addEventListener("pointermove", onMove);
  container.addEventListener("pointerleave", onLeave);

  const clock = new THREE.Clock();
  let raf = 0, running = true;
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;

  function tick() {
    if (!running) return;
    raf = requestAnimationFrame(tick);
    const t = clock.getElapsedTime();
    if (!reduce) globe.rotation.y += 0.0016;
    globe.rotation.z += (targetY * 0.15 - globe.rotation.z) * 0.05;
    camera.position.x += (targetX * 1.2 - camera.position.x) * 0.05;
    camera.lookAt(0, 0, 0);
    for (const p of pulses) {
      p.mesh.scale.setScalar(1 + Math.sin(t * 2 + p.seed) * 0.25);
      p.ring.scale.setScalar(1 + Math.sin(t * 1.5 + p.seed) * 0.5);
      (p.ring.material as THREE.MeshBasicMaterial).opacity = 0.4 - Math.sin(t * 1.5 + p.seed) * 0.3;
    }
    if (px >= 0) {
      ray.setFromCamera(ndc, camera);
      const hit = ray.intersectObjects(pickable, false)[0];
      if (hit) {
        tip.textContent = (hit.object.userData.label as string) ?? "";
        tip.style.left = `${px + 12}px`;
        tip.style.top = `${py + 12}px`;
        tip.classList.remove("hidden");
      } else {
        tip.classList.add("hidden");
      }
    }
    renderer.render(scene, camera);
  }
  tick();

  const onResize = () => {
    const nw = container.clientWidth, nh = container.clientHeight;
    if (!nw || !nh) return;
    camera.aspect = nw / nh;
    camera.updateProjectionMatrix();
    renderer.setSize(nw, nh);
  };
  const ro = new ResizeObserver(onResize);
  ro.observe(container);

  return () => {
    running = false;
    cancelAnimationFrame(raf);
    ro.disconnect();
    container.removeEventListener("pointermove", onMove);
    container.removeEventListener("pointerleave", onLeave);
    tip.remove();
    renderer.dispose();
    renderer.domElement.remove();
    scene.traverse((o) => {
      const any = o as THREE.Mesh;
      any.geometry?.dispose?.();
      const mat = any.material;
      if (Array.isArray(mat)) mat.forEach((m) => m.dispose());
      else mat?.dispose?.();
    });
  };
}
