import { create } from "zustand";
import { persist } from "zustand/middleware";

import type { Me, Tokens } from "../types";

interface AuthState {
  access: string | null;
  refresh: string | null;
  user: Me | null;
  /** Vrai quand la session n'a pas pu être renouvelée : l'écran de connexion l'explique au lieu d'une erreur. */
  expiree: boolean;
  setSession: (tokens: Tokens, user: Me) => void;
  setUser: (user: Me) => void;
  setAccess: (access: string) => void;
  clear: () => void;
  /** Déconnexion pour session expirée (jeton non renouvelable) : retour à la connexion avec un message. */
  expire: () => void;
}

export const useAuth = create<AuthState>()(
  persist(
    (set) => ({
      access: null,
      refresh: null,
      user: null,
      expiree: false,
      setSession: (tokens, user) =>
        set({ access: tokens.access, refresh: tokens.refresh, user, expiree: false }),
      setUser: (user) => set({ user }),
      setAccess: (access) => set({ access }),
      clear: () => {
        // Déconnexion : le cache d'API terrain est vidé (le prochain utilisateur ne voit pas ces données).
        if (typeof navigator !== "undefined" && "serviceWorker" in navigator) {
          navigator.serviceWorker.controller?.postMessage("clear-api-cache");
        }
        set({ access: null, refresh: null, user: null });
      },
      expire: () => {
        useAuth.getState().clear();
        set({ expiree: true });
      },
    }),
    { name: "etls.auth" },
  ),
);

export const isAuthenticated = () => Boolean(useAuth.getState().access);