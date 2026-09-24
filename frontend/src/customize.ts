import { NAV } from "./router";
import { ACCENTS, getPrefs, setPrefs, resetPrefs } from "./prefs";

function fullOrder(): string[] {
  const all = NAV.map((n) => n.id);
  const p = getPrefs();
  const order = p.navOrder.filter((id) => all.includes(id));
  for (const id of all) if (!order.includes(id)) order.push(id);
  return order;
}
const label = (id: string) => NAV.find((n) => n.id === id)?.label ?? id;

const eye = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>`;
const eyeOff = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17.9 17.9A10.4 10.4 0 0112 20C5 20 1 12 1 12a18 18 0 015-5.9M9.9 4.2A10 10 0 0112 4c7 0 11 8 11 8a18 18 0 01-2.2 3.2M1 1l22 22"/></svg>`;

function seg(key: string, cur: string, opts: [string, string][]): string {
  return `<div class="flex gap-1.5">${opts.map(([v, lbl]) =>
    `<button data-set="${key}" data-val="${v}" class="flex-1 rounded-lg px-2.5 py-1.5 text-xs transition-colors ${v === cur ? "accent-bg text-white" : "bg-ink-800 text-fg-muted hover:text-fg"}">${lbl}</button>`).join("")}</div>`;
}
function sw(id: string, on: boolean): string {
  return `<button id="${id}" role="switch" aria-checked="${on}" class="relative h-6 w-11 rounded-full transition-colors ${on ? "accent-bg" : "bg-ink-700"}"><span class="absolute top-0.5 h-5 w-5 rounded-full bg-white transition-all" style="left:${on ? "22px" : "2px"}"></span></button>`;
}

export function mountCustomize(host: HTMLElement) {
  const btn = document.createElement("button");
  btn.className = "rounded-lg p-2 text-fg-muted hover:text-fg hover:bg-ink-800 transition-colors";
  btn.setAttribute("aria-label", "Customize");
  btn.innerHTML = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6"/></svg>`;
  host.append(btn);

  const overlay = document.createElement("div");
  overlay.className = "fixed inset-0 z-40 bg-black/50 opacity-0 pointer-events-none transition-opacity duration-300";
  const panel = document.createElement("aside");
  panel.className = "fixed top-0 right-0 z-50 h-full w-[360px] max-w-[92vw] glass p-5 overflow-y-auto translate-x-full transition-transform duration-300";
  panel.style.borderRadius = "0";
  document.body.append(overlay, panel);

  const open = () => { render(); overlay.classList.remove("opacity-0", "pointer-events-none"); panel.classList.remove("translate-x-full"); };
  const close = () => { overlay.classList.add("opacity-0", "pointer-events-none"); panel.classList.add("translate-x-full"); };
  btn.addEventListener("click", open);
  addEventListener("ascent:customize", open);
  overlay.addEventListener("click", close);
  addEventListener("keydown", (e) => { if (e.key === "Escape") close(); });

  function section(title: string, body: string): string {
    return `<section><div class="text-xs uppercase tracking-wide text-fg-faint mb-2.5">${title}</div>${body}</section>`;
  }

  function render() {
    const p = getPrefs();
    const swatches = ACCENTS.map((a) =>
      `<button data-accent="${a.name}" class="h-8 w-8 rounded-full transition-transform hover:scale-110" style="background:linear-gradient(135deg, ${a.a}, ${a.b}); box-shadow:${a.name === p.accentName ? "0 0 0 2px var(--color-ink-900), 0 0 0 4px " + a.a : "none"}"></button>`).join("");

    const tabRows = fullOrder().map((id) => {
      const hidden = id !== "dashboard" && p.hidden.includes(id);
      const lock = id === "dashboard";
      return `<div draggable="true" data-tab="${id}" class="flex items-center gap-2 rounded-lg bg-ink-800/60 px-2.5 py-2 ${hidden ? "opacity-50" : ""}">
        <svg class="text-fg-faint cursor-grab" width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><circle cx="9" cy="6" r="1.5"/><circle cx="15" cy="6" r="1.5"/><circle cx="9" cy="12" r="1.5"/><circle cx="15" cy="12" r="1.5"/><circle cx="9" cy="18" r="1.5"/><circle cx="15" cy="18" r="1.5"/></svg>
        <span class="text-sm flex-1">${label(id)}</span>
        ${lock ? `<span class="text-[10px] text-fg-faint">home</span>` : `<button data-toggle="${id}" class="text-fg-faint hover:text-fg">${hidden ? eyeOff : eye}</button>`}</div>`;
    }).join("");

    panel.innerHTML = `
      <div class="flex items-center justify-between mb-5">
        <h2 class="text-lg font-semibold tracking-tight brandtype">Customize</h2>
        <button id="cz-close" class="text-fg-faint hover:text-fg">✕</button>
      </div>
      <div class="space-y-6">
        ${section("Accent", `<div class="flex items-center gap-3 flex-wrap">${swatches}
          <label class="flex items-center gap-1.5 text-xs text-fg-muted">A <input id="cz-a1" type="color" value="${p.accent}" class="h-7 w-7 rounded bg-transparent border-0 cursor-pointer"></label>
          <label class="flex items-center gap-1.5 text-xs text-fg-muted">B <input id="cz-a2" type="color" value="${p.accent2}" class="h-7 w-7 rounded bg-transparent border-0 cursor-pointer"></label></div>`)}
        ${section("Type", seg("font", p.font, [["system", "System"], ["mono", "Mono"], ["serif", "Serif"]]))}
        ${section("Cards", `${seg("card", p.card, [["glass", "Glass"], ["solid", "Solid"], ["outline", "Outline"]])}
          <div class="flex items-center justify-between mt-3"><span class="text-sm">Corner radius</span><input id="cz-radius" type="range" min="8" max="28" step="1" value="${p.radius}" class="w-32 accent-[var(--accent)]"></div>
          <div class="flex items-center justify-between mt-2"><span class="text-sm">Glow</span>${sw("cz-glow", p.glow)}</div>`)}
        ${section("Background", `<div class="flex items-center justify-between"><span class="text-sm">Aurora</span><input id="cz-aurora" type="range" min="0" max="1" step="0.1" value="${p.aurora}" class="w-32 accent-[var(--accent)]"></div>
          <div class="flex items-center justify-between mt-2"><span class="text-sm">Particles</span>${sw("cz-particles", p.particles)}</div>
          <div class="flex items-center justify-between mt-2"><div><div class="text-sm">3D globe</div><div class="text-[11px] text-fg-faint">Dashboard hero · heavier on GPU</div></div>${sw("cz-globe", p.globe)}</div>`)}
        ${section("Density", seg("density", p.density, [["comfortable", "Comfortable"], ["compact", "Compact"]]))}
        <section><div class="flex items-center justify-between"><span class="text-sm">Motion &amp; animations</span>${sw("cz-motion", p.motion)}</div></section>
        ${section("Tabs — drag to reorder, eye to hide", `<div id="cz-tabs" class="space-y-1.5">${tabRows}</div>`)}
        <button id="cz-reset" class="text-xs text-fg-faint hover:text-danger">Reset to defaults</button>
      </div>`;

    wire(p);
  }

  function wire(_p: ReturnType<typeof getPrefs>) {
    panel.querySelector("#cz-close")?.addEventListener("click", close);
    panel.querySelectorAll<HTMLButtonElement>("[data-accent]").forEach((b) => b.addEventListener("click", () => {
      const a = ACCENTS.find((x) => x.name === b.dataset.accent)!;
      setPrefs({ accent: a.a, accent2: a.b, accentName: a.name }); render();
    }));
    panel.querySelectorAll<HTMLButtonElement>("[data-set]").forEach((b) => b.addEventListener("click", () => {
      setPrefs({ [b.dataset.set!]: b.dataset.val } as never); render();
    }));
    (panel.querySelector("#cz-a1") as HTMLInputElement | null)?.addEventListener("input", (e) =>
      setPrefs({ accent: (e.target as HTMLInputElement).value, accentName: "Custom" }));
    (panel.querySelector("#cz-a2") as HTMLInputElement | null)?.addEventListener("input", (e) =>
      setPrefs({ accent2: (e.target as HTMLInputElement).value, accentName: "Custom" }));
    (panel.querySelector("#cz-radius") as HTMLInputElement | null)?.addEventListener("input", (e) =>
      setPrefs({ radius: Number((e.target as HTMLInputElement).value) }));
    (panel.querySelector("#cz-aurora") as HTMLInputElement | null)?.addEventListener("input", (e) =>
      setPrefs({ aurora: Number((e.target as HTMLInputElement).value) }));
    panel.querySelector("#cz-glow")?.addEventListener("click", () => { setPrefs({ glow: !getPrefs().glow }); render(); });
    panel.querySelector("#cz-particles")?.addEventListener("click", () => { setPrefs({ particles: !getPrefs().particles }); render(); });
    panel.querySelector("#cz-globe")?.addEventListener("click", () => { setPrefs({ globe: !getPrefs().globe }); render(); });
    panel.querySelector("#cz-motion")?.addEventListener("click", () => { setPrefs({ motion: !getPrefs().motion }); render(); });
    panel.querySelectorAll<HTMLButtonElement>("[data-toggle]").forEach((b) => b.addEventListener("click", () => {
      const id = b.dataset.toggle!; const h = getPrefs().hidden;
      setPrefs({ hidden: h.includes(id) ? h.filter((x) => x !== id) : [...h, id] }); render();
    }));
    panel.querySelector("#cz-reset")?.addEventListener("click", () => { resetPrefs(); render(); });
    wireDrag();
  }

  function wireDrag() {
    let dragId: string | null = null;
    panel.querySelectorAll<HTMLElement>("[data-tab]").forEach((row) => {
      row.addEventListener("dragstart", () => { dragId = row.dataset.tab ?? null; row.classList.add("opacity-40"); });
      row.addEventListener("dragend", () => row.classList.remove("opacity-40"));
      row.addEventListener("dragover", (e) => e.preventDefault());
      row.addEventListener("drop", (e) => {
        e.preventDefault();
        const targetId = row.dataset.tab;
        if (!dragId || !targetId || dragId === targetId) return;
        const order = fullOrder().filter((id) => id !== dragId);
        order.splice(order.indexOf(targetId), 0, dragId);
        setPrefs({ navOrder: order }); render();
      });
    });
  }
}
