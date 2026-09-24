import { gsap } from "gsap";

const reduce = () =>
  matchMedia("(prefers-reduced-motion: reduce)").matches ||
  document.documentElement.classList.contains("no-motion");

/** Staggered fade-up of a view's top-level blocks on mount.
 * CSS-keyframe driven (compositor) so content is ALWAYS visible even if the
 * animation never runs — never gate visibility on JS animation state. */
export function enter(root: HTMLElement) {
  if (reduce()) return;
  const scope = root.children.length === 1 && root.firstElementChild ? root.firstElementChild : root;
  const targets = Array.from(scope.children) as HTMLElement[];
  targets.forEach((el, i) => {
    el.classList.add("anim-fade-up");
    el.style.animationDelay = `${i * 0.055}s`;
  });
}

/** Slide a shared highlight pill to a target element within a container. */
export function slidePill(pill: HTMLElement, target: HTMLElement, container: HTMLElement) {
  const c = container.getBoundingClientRect();
  const t = target.getBoundingClientRect();
  gsap.to(pill, {
    y: t.top - c.top,
    height: t.height,
    duration: reduce() ? 0 : 0.35,
    ease: "power3.out",
  });
}

/** Animate an element's text from 0 to `to`. */
export function countUp(el: HTMLElement, to: number, opts: { suffix?: string; prefix?: string } = {}) {
  const { suffix = "", prefix = "" } = opts;
  const set = (v: number) => (el.textContent = `${prefix}${Math.round(v)}${suffix}`);
  if (reduce()) return set(to);
  const obj = { v: 0 };
  gsap.to(obj, { v: to, duration: 0.9, ease: "power2.out", onUpdate: () => set(obj.v) });
}

/** Grow progress-bar fills from 0 to their inline width. */
export function growBars(scope: ParentNode) {
  const bars = scope.querySelectorAll<HTMLElement>(".bar-fill");
  if (!bars.length) return;
  if (reduce()) return;
  bars.forEach((b) => gsap.from(b, { width: 0, duration: 0.8, ease: "power3.out" }));
}

/** Quick fade-out for a crossfade between views. */
export function exit(root: HTMLElement): Promise<void> {
  if (reduce()) return Promise.resolve();
  return new Promise((res) => {
    gsap.to(root, { opacity: 0, duration: 0.12, ease: "power1.in", onComplete: () => res() });
  });
}

/** Make an element drift toward the cursor while hovered. */
export function magnetic(el: HTMLElement, strength = 0.3) {
  if (reduce()) return;
  const xTo = gsap.quickTo(el, "x", { duration: 0.4, ease: "power3" });
  const yTo = gsap.quickTo(el, "y", { duration: 0.4, ease: "power3" });
  el.addEventListener("pointermove", (e) => {
    const r = el.getBoundingClientRect();
    xTo((e.clientX - (r.left + r.width / 2)) * strength);
    yTo((e.clientY - (r.top + r.height / 2)) * strength);
  });
  el.addEventListener("pointerleave", () => {
    xTo(0);
    yTo(0);
  });
}

/** Wire magnetism onto accent buttons / opted-in elements within a scope (idempotent). */
export function initMagnetics(scope: ParentNode) {
  scope.querySelectorAll<HTMLElement>(".btn-accent, [data-magnetic]").forEach((el) => {
    if (el.dataset.mag) return;
    el.dataset.mag = "1";
    magnetic(el, el.dataset.magnetic ? Number(el.dataset.magnetic) : 0.3);
  });
}

export { gsap };
