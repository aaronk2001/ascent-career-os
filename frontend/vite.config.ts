import { defineConfig, type Plugin } from "vite";
import tailwindcss from "@tailwindcss/vite";

const BASE = "/static/dist/";

// Every route is a dynamic import, so Vite emits no modulepreload hints and the
// browser only discovers the default route's chunk after parsing the entry —
// HTML → entry → view → API, three serial hops. Preload the Today chunk (and the
// shared visuals chunk it pulls) to collapse one of them.
function preloadDefaultRoute(): Plugin {
  return {
    name: "ascent-preload-default-route",
    apply: "build",
    transformIndexHtml: {
      order: "post",
      handler(html, ctx) {
        const files = Object.keys(ctx.bundle ?? {})
          .filter((f) => /^assets\/(today|visuals)-[^/]+\.js$/.test(f));
        return {
          html,
          tags: files.map((f) => ({
            tag: "link",
            attrs: { rel: "modulepreload", crossorigin: "", href: BASE + f },
            injectTo: "head" as const,
          })),
        };
      },
    },
  };
}

export default defineConfig(({ command }) => ({
  // build → served by Flask under /static/dist/; dev → served at root by Vite
  base: command === "build" ? BASE : "/",
  plugins: [tailwindcss(), preloadDefaultRoute()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": "http://127.0.0.1:5001",
    },
  },
  build: {
    outDir: "../static/dist",
    emptyOutDir: true,
    // Desktop-only target (pywebview = modern Edge/WebView2), so skip legacy
    // transpilation → smaller, faster-parsing chunks.
    target: "esnext",
    // The lazily loaded Three.js globe chunk is ~570 kB by itself; it never blocks first paint.
    chunkSizeWarningLimit: 700,
  },
}));
