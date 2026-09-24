// Lightweight 2D-canvas particle field behind the app — drifting dots + faint
// links, accent-tinted. Cheap (no WebGL), motion-gated, fixed behind content.
import { getPrefs } from "./prefs";

export function mountAmbient() {
  if (matchMedia("(prefers-reduced-motion: reduce)").matches || document.documentElement.classList.contains("no-motion")) return;

  const canvas = document.createElement("canvas");
  canvas.style.cssText = "position:fixed;inset:0;z-index:-1;pointer-events:none;opacity:0.5";
  document.body.appendChild(canvas);
  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  let w = 0, h = 0, raf = 0;
  const N = 56;
  const pts = Array.from({ length: N }, (_, i) => ({
    x: 0, y: 0, vx: (((i * 73) % 100) / 100 - 0.5) * 0.18, vy: (((i * 37) % 100) / 100 - 0.5) * 0.18,
  }));

  function accent(): string {
    return getComputedStyle(document.documentElement).getPropertyValue("--accent").trim() || "#6366f1";
  }
  function resize() {
    const dpr = Math.min(devicePixelRatio, 2);
    w = innerWidth; h = innerHeight;
    canvas.width = w * dpr; canvas.height = h * dpr;
    ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
    for (const p of pts) {
      if (!p.x) p.x = ((p.vx * 9973) % 1 + 1) % 1 * w;
      if (!p.y) p.y = ((p.vy * 9973) % 1 + 1) % 1 * h;
    }
  }
  resize();
  addEventListener("resize", resize);

  function tick() {
    raf = requestAnimationFrame(tick);
    ctx!.clearRect(0, 0, w, h);
    if (!getPrefs().particles) return;
    const col = accent();
    for (const p of pts) {
      p.x += p.vx; p.y += p.vy;
      if (p.x < 0) p.x += w; else if (p.x > w) p.x -= w;
      if (p.y < 0) p.y += h; else if (p.y > h) p.y -= h;
    }
    // faint links
    ctx!.strokeStyle = col;
    for (let i = 0; i < N; i++) {
      for (let j = i + 1; j < N; j++) {
        const dx = pts[i].x - pts[j].x, dy = pts[i].y - pts[j].y;
        const d2 = dx * dx + dy * dy;
        if (d2 < 140 * 140) {
          ctx!.globalAlpha = (1 - d2 / (140 * 140)) * 0.10;
          ctx!.beginPath();
          ctx!.moveTo(pts[i].x, pts[i].y);
          ctx!.lineTo(pts[j].x, pts[j].y);
          ctx!.stroke();
        }
      }
    }
    ctx!.globalAlpha = 0.5;
    ctx!.fillStyle = col;
    for (const p of pts) {
      ctx!.beginPath();
      ctx!.arc(p.x, p.y, 1.3, 0, Math.PI * 2);
      ctx!.fill();
    }
    ctx!.globalAlpha = 1;
  }
  tick();

  return () => {
    cancelAnimationFrame(raf);
    removeEventListener("resize", resize);
    canvas.remove();
  };
}
