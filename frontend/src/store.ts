type Listener<T> = (value: T) => void;

export function createStore<T extends object>(initial: T) {
  let state = initial;
  const listeners = new Set<Listener<T>>();
  return {
    get: () => state,
    set(patch: Partial<T>) {
      state = { ...state, ...patch };
      for (const l of listeners) l(state);
    },
    subscribe(l: Listener<T>): () => void {
      listeners.add(l);
      return () => {
        listeners.delete(l);
      };
    },
  };
}

export type Store<T extends object> = ReturnType<typeof createStore<T>>;
