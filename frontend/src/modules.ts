import { api } from "./api";

// Optional modules (settings.yaml `modules:`). Loaded once before the shell mounts
// so the nav never flashes items that are switched off.
export type Modules = { side: boolean; clips: boolean; health: boolean; news: boolean };

const OFF: Modules = { side: false, clips: false, health: false, news: false };
let current: Modules = OFF;

export async function loadModules(): Promise<void> {
  // If the list can't be loaded, every optional module stays off.
  current = { ...OFF, ...(await api<Partial<Modules>>("/modules").catch(() => ({}))) };
}

export const modules = (): Modules => current;
