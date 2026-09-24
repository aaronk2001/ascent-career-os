// Reusable lightweight animated visuals (SVG/canvas/CSS) — cheap, motion-gated.
// The globe (globe.ts) stays the only WebGL scene.

export const reduced = () =>
  matchMedia("(prefers-reduced-motion: reduce)").matches || document.documentElement.classList.contains("no-motion");
export const accent = () => getComputedStyle(document.documentElement).getPropertyValue("--accent").trim() || "#6366f1";
export const accent2 = () => getComputedStyle(document.documentElement).getPropertyValue("--accent-2").trim() || "#8b5cf6";

/** Animated SVG progress ring. Returns markup; call mountRings() after insert. */
export function ring(pct: number, opts: { size?: number; stroke?: number; color?: string; label?: string } = {}): string {
  const size = opts.size ?? 64;
  const sw = opts.stroke ?? 6;
  const r = (size - sw) / 2;
  const C = 2 * Math.PI * r;
  const p = Math.max(0, Math.min(100, pct));
  const offset = C * (1 - p / 100);
  const color = opts.color ?? "var(--accent)";
  const center = opts.label != null
    ? `<div class="absolute inset-0 grid place-items-center text-xs font-semibold nums">${opts.label}</div>` : "";
  return `<div class="relative shrink-0" style="width:${size}px;height:${size}px">
    <svg width="${size}" height="${size}" class="-rotate-90">
      <circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="var(--color-ink-700)" stroke-width="${sw}"/>
      <circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="${color}" stroke-width="${sw}" stroke-linecap="round"
        stroke-dasharray="${C.toFixed(1)}" stroke-dashoffset="${C.toFixed(1)}" data-ring="${offset.toFixed(1)}"
        style="transition: stroke-dashoffset .9s cubic-bezier(.22,1,.36,1); filter: drop-shadow(0 0 4px color-mix(in oklab, ${color} 55%, transparent))"/>
    </svg>${center}</div>`;
}

export function mountRings(scope: ParentNode) {
  const els = scope.querySelectorAll<SVGCircleElement>("[data-ring]");
  const inst = reduced();
  els.forEach((el) => {
    const to = el.dataset.ring!;
    if (inst) { el.style.transition = "none"; el.style.strokeDashoffset = to; }
    else requestAnimationFrame(() => requestAnimationFrame(() => { el.style.strokeDashoffset = to; }));
  });
}

/** Particle flow band — dots drifting left→right in lanes. */
export function mountFlow(el: HTMLElement, height = 60): () => void {
  const canvas = document.createElement("canvas");
  canvas.className = "block w-full";
  canvas.style.height = `${height}px`;
  el.appendChild(canvas);
  const ctx = canvas.getContext("2d");
  if (!ctx) return () => canvas.remove();
  const LANES = 5;
  const parts = Array.from({ length: 64 }, (_, i) => ({
    x: ((i * 131) % 100) / 100, lane: i % LANES, v: 0.0009 + (i % 5) * 0.0004, r: 1 + (i % 3) * 0.5,
  }));
  let w = 0, h = height, raf = 0;
  const resize = () => {
    const dpr = Math.min(devicePixelRatio, 2);
    w = el.clientWidth; canvas.width = w * dpr; canvas.height = h * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  };
  resize();
  addEventListener("resize", resize);
  const tick = () => {
    raf = requestAnimationFrame(tick);
    ctx.clearRect(0, 0, w, h);
    if (reduced()) return;
    const col = accent();
    for (const p of parts) {
      p.x += p.v;
      if (p.x > 1.05) p.x = -0.05;
      const x = p.x * w;
      const y = ((p.lane + 0.5) / LANES) * h;
      ctx.globalAlpha = 0.12;
      ctx.strokeStyle = col;
      ctx.beginPath(); ctx.moveTo(x - 10, y); ctx.lineTo(x, y); ctx.stroke();
      ctx.globalAlpha = 0.7;
      ctx.fillStyle = col;
      ctx.beginPath(); ctx.arc(x, y, p.r, 0, Math.PI * 2); ctx.fill();
    }
    ctx.globalAlpha = 1;
  };
  tick();
  return () => { cancelAnimationFrame(raf); removeEventListener("resize", resize); canvas.remove(); };
}

/** Pulsing reactive orb (canvas). active() → faster/brighter pulses. */
export function mountOrb(el: HTMLElement, active: () => boolean, size = 120): () => void {
  const canvas = document.createElement("canvas");
  canvas.style.cssText = `width:${size}px;height:${size}px`;
  el.appendChild(canvas);
  const ctx = canvas.getContext("2d");
  if (!ctx) return () => canvas.remove();
  const dpr = Math.min(devicePixelRatio, 2);
  canvas.width = size * dpr; canvas.height = size * dpr;
  ctx.scale(dpr, dpr);
  const cx = size / 2, cy = size / 2;
  const rings = [0, 0.33, 0.66];
  let t = 0, raf = 0;
  const tick = () => {
    raf = requestAnimationFrame(tick);
    ctx.clearRect(0, 0, size, size);
    const speed = active() ? 0.03 : 0.012;
    t += speed;
    const col = accent(), col2 = accent2();
    // expanding rings
    if (!reduced()) {
      for (const phase of rings) {
        const f = (t + phase) % 1;
        const rad = 14 + f * (size / 2 - 14);
        ctx.globalAlpha = (1 - f) * (active() ? 0.5 : 0.3);
        ctx.strokeStyle = col;
        ctx.lineWidth = 2;
        ctx.beginPath(); ctx.arc(cx, cy, rad, 0, Math.PI * 2); ctx.stroke();
      }
    }
    // core
    const pulse = reduced() ? 1 : 1 + Math.sin(t * 4) * 0.08;
    const grad = ctx.createRadialGradient(cx, cy, 2, cx, cy, 16 * pulse);
    grad.addColorStop(0, col2);
    grad.addColorStop(1, col);
    ctx.globalAlpha = 1;
    ctx.fillStyle = grad;
    ctx.beginPath(); ctx.arc(cx, cy, 14 * pulse, 0, Math.PI * 2); ctx.fill();
    ctx.globalAlpha = 0.25;
    ctx.fillStyle = col;
    ctx.beginPath(); ctx.arc(cx, cy, 22 * pulse, 0, Math.PI * 2); ctx.fill();
    ctx.globalAlpha = 1;
  };
  tick();
  return () => { cancelAnimationFrame(raf); canvas.remove(); };
}
