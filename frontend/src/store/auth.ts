import { create } from "zustand";
import { persist } from "zustand/middleware";

import type { Me, Tokens } from "../types";

interface AuthState {
  access: string | null;
  refresh: string | null;
  user: Me | null;
  setSession: (tokens: Tokens, user: Me) => void;
  setUser: (user: Me) => void;
  setAccess: (access: string) => void;
  clear: () => void;
}

export const useAuth = create<AuthState>()(
  persist(
    (set) => ({
      access: null,
      refresh: null,
      user: null,
      setSession: (tokens, user) =>
        set({ access: tokens.access, refresh: tokens.refresh, user }),
      setUser: (user) => set({ user }),
      setAccess: (access) => set({ access }),
      clear: () => set({ access: null, refresh: null, user: null }),
    }),
    { name: "etls.auth" },
  ),
);

export const isAuthenticated = () => Boolean(useAuth.getState().access);