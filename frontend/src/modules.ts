import { api } from "./api";

// Optional modules (settings.yaml `modules:`). Loaded once before the shell mounts
// so the nav never flashes items that are switched off.
export type Modules = { side: boolean; clips: boolean; health: boolean };

let current: Modules = { side: false, clips: false, health: false };

export async function loadModules(): Promise<void> {
  // A backend from before module flags existed has no /api/modules: show everything,
  // as that backend did.
  current = await api<Modules>("/modules").catch(() => ({ side: true, clips: true, health: true }));
}

export const modules = (): Modules => current;
