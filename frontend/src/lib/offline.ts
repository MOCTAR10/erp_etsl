/** Branchement runtime du mode hors-ligne : file persistante, synchro auto, service worker. */
import { useEffect, useState, useSyncExternalStore } from "react";

import { postIdempotent } from "../api/client";
import { useAuth } from "../store/auth";
import { createQueue, idbStorage, memoryStorage, type QueuedRequest } from "./offlineQueue";

const storage = typeof indexedDB !== "undefined" ? idbStorage() : memoryStorage();

/** File unique de l'application : chaque envoi rejoue la saisie avec SA clé d'idempotence. */
export const offlineQueue = createQueue(storage, async (item: QueuedRequest) => {
  await postIdempotent(item.path, item.body, item.key);
});

const owner = () => useAuth.getState().user?.id ?? "";

/** Met en file puis tente une synchronisation immédiate (sans effet si hors-ligne). */
export async function submitOffline(input: { path: string; body: unknown; label: string }) {
  const item = await offlineQueue.enqueue({ owner: owner(), ...input });
  void syncNow();
  return item;
}

export function syncNow() {
  const who = owner();
  return who ? offlineQueue.flush(who) : Promise.resolve({ sent: 0, failed: 0, remaining: 0, stopped: false });
}

function subscribeOnline(cb: () => void) {
  window.addEventListener("online", cb);
  window.addEventListener("offline", cb);
  return () => {
    window.removeEventListener("online", cb);
    window.removeEventListener("offline", cb);
  };
}

export function useOnline(): boolean {
  return useSyncExternalStore(subscribeOnline, () => navigator.onLine, () => true);
}

/** Saisies de l'utilisateur courant encore sur l'appareil (en attente ou en échec). */
export function useQueueItems(): QueuedRequest[] {
  const [items, setItems] = useState<QueuedRequest[]>([]);
  const user = useAuth((s) => s.user);
  useEffect(() => {
    let live = true;
    const refresh = () => void offlineQueue.list(user?.id ?? "").then((l) => live && setItems(l));
    refresh();
    const off = offlineQueue.subscribe(refresh);
    return () => {
      live = false;
      off();
    };
  }, [user?.id]);
  return items;
}

/** Synchronisation automatique : au retour du réseau, au démarrage et toutes les 60 s si des saisies attendent. */
export function startAutoSync(): () => void {
  // Au retour du réseau, la première tentative peut précéder la reconnexion réelle : on réessaie 2 fois.
  const run = async () => {
    for (const delay of [0, 1500, 5000]) {
      if (delay) await new Promise((r) => setTimeout(r, delay));
      if (!(await syncNow()).stopped) return;
    }
  };
  const trigger = () => void run();
  window.addEventListener("online", trigger);
  const timer = window.setInterval(trigger, 60_000);
  trigger();
  return () => {
    window.removeEventListener("online", trigger);
    window.clearInterval(timer);
  };
}

export function registerServiceWorker() {
  if (!import.meta.env.PROD || !("serviceWorker" in navigator)) return;
  window.addEventListener("load", () => {
    void navigator.serviceWorker.register(`${import.meta.env.BASE_URL}sw.js`).catch(() => undefined);
  });
}

/** À la déconnexion : le cache d'API (données terrain) est vidé ; les saisies en attente restent à leur auteur. */
export function clearOfflineCaches() {
  if ("serviceWorker" in navigator) navigator.serviceWorker.controller?.postMessage("clear-api-cache");
}
