import { create } from "zustand";
import { api } from "./api";
import type { DeskState } from "./types";

interface DeskStore {
  state: DeskState | null;
  error: string | null;
  load: () => Promise<DeskState | null>;
}

// Shared by the top nav (active engagement, budget) and the desk page.
export const useDesk = create<DeskStore>((set) => ({
  state: null,
  error: null,
  async load() {
    try {
      const state = await api.state();
      set({ state, error: null });
      return state;
    } catch (err) {
      set({ error: (err as Error).message });
      return null;
    }
  },
}));
