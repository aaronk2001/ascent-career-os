import "./style.css";
import { mountShell } from "./shell";
import { startRouter } from "./router";
import { apply } from "./prefs";
import { initMagnetics } from "./motion";
import { mountCommandPalette } from "./cmdk";
import { mountAmbient } from "./ambient";

apply();
mountAmbient();

const app = document.getElementById("app");
if (!app) throw new Error("#app missing");

const content = mountShell(app);
document.getElementById("boot")?.remove();
initMagnetics(app);
mountCommandPalette();
startRouter(content, (id) =>
  dispatchEvent(new CustomEvent("ascent:route", { detail: id })),
);
