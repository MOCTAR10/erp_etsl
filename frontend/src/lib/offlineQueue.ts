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
 * - 409 (conflit : saisie trop ancienne, doublon, mesure plus récente au serveur) → marqué « conflit » ; l'utilisateur
 *   choisit « Forcer » (renvoi avec `forcer`) ou « Abandonner » ;
 * - autre 4xx (validation, droits) → marqué « échec » avec le message du serveur, la suite continue.
 *
 * Une saisie peut dépendre d'une autre (`dependsOn`, ex. photo d'un permis créé hors ligne) : elle attend l'envoi de
 * sa parente, puis `{ref}` (chemin et corps) est remplacé par l'identifiant renvoyé par le serveur.
 * Les pièces (photos) sont gardées sur l'appareil (Blob en IndexedDB) et envoyées en multipart.
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
  createdAt: string; // horodatage de la saisie sur l'appareil (transmis au serveur : `saisi_le`)
  status: "pending" | "failed" | "conflict";
  attempts: number;
  error?: string;
  files?: QueuedFile[];
  dependsOn?: string; // clé d'idempotence de la saisie parente
  force?: boolean; // conflit levé par l'utilisateur : renvoi avec `forcer`
}

export interface QueuedFile {
  field: string;
  name: string;
  type: string;
  blob: Blob;
}

export const REF = "{ref}";

/** Remplace `{ref}` (chemin et valeurs texte du corps) par l'identifiant de la saisie parente. */
export function resolveRef(item: QueuedRequest, ref: string): QueuedRequest {
  const body =
    item.body && typeof item.body === "object"
      ? Object.fromEntries(
          Object.entries(item.body as Record<string, unknown>).map(([k, v]) => [k, v === REF ? ref : v]),
        )
      : item.body;
  return { ...item, path: item.path.split(REF).join(ref), body, dependsOn: undefined };
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
  conflicts?: number;
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

export function createQueue(storage: QueueStorage, send: (item: QueuedRequest) => Promise<unknown>) {
  const listeners = new Set<() => void>();
  let flushing: Promise<FlushResult> | null = null;
  let lastSync: string | null = null;
  const notify = () => listeners.forEach((l) => l());

  const list = async (owner?: string) =>
    (await storage.getAll()).filter((i) => owner === undefined || i.owner === owner);

  async function enqueue(input: {
    owner: string;
    path: string;
    body: unknown;
    label: string;
    files?: QueuedFile[];
    dependsOn?: string;
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
      ...(input.files?.length ? { files: input.files } : {}),
      ...(input.dependsOn ? { dependsOn: input.dependsOn } : {}),
    });
    notify();
    return item;
  }

  async function run(owner: string): Promise<FlushResult> {
    let sent = 0;
    let failed = 0;
    let conflicts = 0;
    let stopped = false;
    const snapshot = await list(owner);
    const waiting = new Set(snapshot.map((i) => i.key));
    const resolved = new Map<string, string>();
    for (let item of snapshot) {
      if (item.status !== "pending") continue;
      if (item.dependsOn) {
        const ref = resolved.get(item.dependsOn);
        if (ref === undefined && waiting.has(item.dependsOn)) continue; // la parente n'est pas encore au serveur
        if (ref !== undefined) {
          item = resolveRef(item, ref);
          await storage.update(item);
        }
      }
      try {
        const res = await send(item);
        await storage.remove(item.id);
        waiting.delete(item.key);
        const id = (res as { id?: unknown } | null | undefined)?.id;
        if (id !== undefined && id !== null) resolved.set(item.key, String(id));
        sent++;
      } catch (err) {
        const status = (err as { status?: number } | null)?.status;
        const retryable = typeof status !== "number" || status === 401 || status >= 500;
        await storage.update({
          ...item,
          attempts: item.attempts + 1,
          status: retryable ? "pending" : status === 409 ? "conflict" : "failed",
          error: retryable ? undefined : describeError(err),
        });
        if (retryable) {
          stopped = true;
          break;
        }
        if (status === 409) conflicts++;
        else failed++;
      }
    }
    const remaining = (await list(owner)).length;
    if (!stopped) lastSync = new Date().toISOString();
    notify();
    return { sent, failed, conflicts, remaining, stopped };
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
    /** Conflit : l'utilisateur confirme sa saisie (renvoyée avec `forcer`, même clé d'idempotence). */
    async force(id: number) {
      const item = (await storage.getAll()).find((i) => i.id === id);
      if (item) await storage.update({ ...item, status: "pending", error: undefined, force: true });
      notify();
    },
    /** Abandon d'une saisie : ses saisies dépendantes (photos) sont abandonnées avec elle. */
    async discard(id: number) {
      const all = await storage.getAll();
      const item = all.find((i) => i.id === id);
      await storage.remove(id);
      if (item) for (const child of all.filter((i) => i.dependsOn === item.key)) await storage.remove(child.id);
      notify();
    },
    lastSyncAt: () => lastSync,
    subscribe(cb: () => void) {
      listeners.add(cb);
      return () => void listeners.delete(cb);
    },
  };
}
