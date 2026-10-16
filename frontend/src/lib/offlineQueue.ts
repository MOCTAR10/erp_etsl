/**
 * File d'attente des saisies terrain hors-ligne (CL-OM-08).
 *
 * Principe : toute saisie terrain (pointage, réception, test gaz, contrôle/CND) est d'abord écrite
 * localement (IndexedDB) avec une clé d'idempotence, puis envoyée dans l'ordre de saisie dès que le
 * réseau est là. Un rejeu (coupure en plein envoi) réutilise la MÊME clé : le serveur ne duplique pas.
 *
 * Règles de synchronisation :
 * - succès → retiré de la file ;
 * - erreur réseau, 401 (session expirée), 5xx → on s'arrête, tout est conservé (on réessaiera) ;
 * - autre 4xx (validation, droits) → marqué « échec » avec le message du serveur, la suite continue.
 *
 * Chaque saisie appartient à l'utilisateur qui l'a faite (`owner`) : après une déconnexion, les saisies en
 * attente restent sur l'appareil mais ne sont synchronisées que par leur auteur (jamais sous l'identité du
 * suivant).
 */

export interface QueuedRequest {
  id: number;
  owner: string; // id de l'utilisateur qui a saisi : jamais envoyé sous l'identité d'un autre
  key: string; // Idempotency-Key
  path: string;
  body: unknown;
  label: string;
  createdAt: string;
  status: "pending" | "failed";
  attempts: number;
  error?: string;
}

export interface QueueStorage {
  getAll(): Promise<QueuedRequest[]>;
  add(item: Omit<QueuedRequest, "id">): Promise<QueuedRequest>;
  update(item: QueuedRequest): Promise<void>;
  remove(id: number): Promise<void>;
}

export interface FlushResult {
  sent: number;
  failed: number;
  remaining: number;
  stopped: boolean;
}

function newKey(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

/** Message lisible depuis la réponse d'erreur DRF (`{champ: [msg]}` ou `{detail}`). */
export function describeError(err: unknown): string {
  const detail = (err as { detail?: unknown } | null)?.detail;
  if (detail && typeof detail === "object") {
    const parts = Object.values(detail as Record<string, unknown>).flat().map(String);
    if (parts.length) return parts.join(" · ");
  }
  return err instanceof Error ? err.message : "Erreur";
}

export function memoryStorage(): QueueStorage {
  let seq = 0;
  const items = new Map<number, QueuedRequest>();
  return {
    async getAll() {
      return [...items.values()].sort((a, b) => a.id - b.id);
    },
    async add(item) {
      const full = { ...item, id: ++seq };
      items.set(full.id, full);
      return full;
    },
    async update(item) {
      items.set(item.id, item);
    },
    async remove(id) {
      items.delete(id);
    },
  };
}

/** Stockage persistant (survit au rechargement et à la fermeture de l'application). */
export function idbStorage(dbName = "etls-offline"): QueueStorage {
  const open = () =>
    new Promise<IDBDatabase>((resolve, reject) => {
      const req = indexedDB.open(dbName, 1);
      req.onupgradeneeded = () => req.result.createObjectStore("queue", { keyPath: "id", autoIncrement: true });
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  const tx = async <T>(mode: IDBTransactionMode, run: (s: IDBObjectStore) => IDBRequest<T>): Promise<T> => {
    const db = await open();
    return new Promise<T>((resolve, reject) => {
      const req = run(db.transaction("queue", mode).objectStore("queue"));
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  };
  return {
    getAll: async () => ((await tx("readonly", (s) => s.getAll())) as QueuedRequest[]).sort((a, b) => a.id - b.id),
    add: async (item) => {
      const id = (await tx("readwrite", (s) => s.add(item))) as number;
      return { ...item, id };
    },
    update: async (item) => void (await tx("readwrite", (s) => s.put(item))),
    remove: async (id) => void (await tx("readwrite", (s) => s.delete(id))),
  };
}

export function createQueue(storage: QueueStorage, send: (item: QueuedRequest) => Promise<void>) {
  const listeners = new Set<() => void>();
  let flushing: Promise<FlushResult> | null = null;
  const notify = () => listeners.forEach((l) => l());

  const list = async (owner?: string) =>
    (await storage.getAll()).filter((i) => owner === undefined || i.owner === owner);

  async function enqueue(input: {
    owner: string;
    path: string;
    body: unknown;
    label: string;
  }): Promise<QueuedRequest> {
    const item = await storage.add({
      owner: input.owner,
      key: newKey(),
      path: input.path,
      body: input.body,
      label: input.label,
      createdAt: new Date().toISOString(),
      status: "pending",
      attempts: 0,
    });
    notify();
    return item;
  }

  async function run(owner: string): Promise<FlushResult> {
    let sent = 0;
    let failed = 0;
    let stopped = false;
    for (const item of await list(owner)) {
      if (item.status !== "pending") continue;
      try {
        await send(item);
        await storage.remove(item.id);
        sent++;
      } catch (err) {
        const status = (err as { status?: number } | null)?.status;
        const retryable = typeof status !== "number" || status === 401 || status >= 500;
        await storage.update({
          ...item,
          attempts: item.attempts + 1,
          status: retryable ? "pending" : "failed",
          error: retryable ? undefined : describeError(err),
        });
        if (retryable) {
          stopped = true;
          break;
        }
        failed++;
      }
    }
    const remaining = (await list(owner)).length;
    notify();
    return { sent, failed, remaining, stopped };
  }

  const flush = (owner: string) => {
    flushing ??= run(owner).finally(() => {
      flushing = null;
    });
    return flushing;
  };

  return {
    enqueue,
    list,
    flush,
    async retry(id: number) {
      const item = (await storage.getAll()).find((i) => i.id === id);
      if (item) await storage.update({ ...item, status: "pending", error: undefined });
      notify();
    },
    async discard(id: number) {
      await storage.remove(id);
      notify();
    },
    subscribe(cb: () => void) {
      listeners.add(cb);
      return () => void listeners.delete(cb);
    },
  };
}
