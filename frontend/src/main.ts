import "./style.css";
import { mountShell } from "./shell";
import { startRouter } from "./router";
import { apply } from "./prefs";
import { initMagnetics } from "./motion";
import { mountCommandPalette } from "./cmdk";
import { mountAmbient } from "./ambient";
import { loadModules } from "./modules";

apply();
mountAmbient();

const app = document.getElementById("app");
if (!app) throw new Error("#app missing");
const root = app;

void loadModules().then(() => {
  const content = mountShell(root);
  document.getElementById("boot")?.remove();
  initMagnetics(root);
  mountCommandPalette();
  startRouter(content, (id) =>
    dispatchEvent(new CustomEvent("ascent:route", { detail: id })),
  );
});
