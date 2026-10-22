import { describe, expect, it, vi } from "vitest";

import { createQueue, memoryStorage, type QueuedRequest } from "./offlineQueue";

class HttpError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown = null) {
    super(`HTTP ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

const make = (send: (i: QueuedRequest) => Promise<void>) => {
  const q = createQueue(memoryStorage(), send);
  const add = (label: string) => q.enqueue({ owner: "u1", path: "/api/x/", body: { label }, label });
  return { q, add };
};

describe("file d'attente hors-ligne", () => {
  it("envoie dans l'ordre de saisie puis se vide", async () => {
    const sent: string[] = [];
    const { q, add } = make(async (i) => void sent.push(i.label));
    await add("a");
    await add("b");
    await add("c");
    const r = await q.flush("u1");
    expect(sent).toEqual(["a", "b", "c"]);
    expect(r).toMatchObject({ sent: 3, failed: 0, remaining: 0, stopped: false });
    expect(await q.list("u1")).toHaveLength(0);
  });

  it("chaque saisie porte une clé d'idempotence unique, conservée au rejeu", async () => {
    const keys: string[] = [];
    let first = true;
    const { q, add } = make(async (i) => {
      keys.push(i.key);
      if (first) {
        first = false;
        throw new TypeError("Failed to fetch"); // coupure réseau pendant l'envoi
      }
    });
    await add("a");
    await add("b");
    await q.flush("u1"); // échoue sur « a » : réseau
    await q.flush("u1"); // rejeu complet
    expect(keys[0]).toBe(keys[1]); // « a » rejoué avec la MÊME clé
    expect(new Set(keys).size).toBe(2);
  });

  it("une erreur réseau stoppe la synchro et conserve tout (hors-ligne)", async () => {
    const send = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
    const { q, add } = make(send);
    await add("a");
    await add("b");
    const r = await q.flush("u1");
    expect(send).toHaveBeenCalledTimes(1);
    expect(r).toMatchObject({ sent: 0, remaining: 2, stopped: true });
    const items = await q.list("u1");
    expect(items.every((i) => i.status === "pending")).toBe(true);
    expect(items[0].attempts).toBe(1);
  });

  it("une erreur de validation (400) est marquée en échec sans bloquer la suite", async () => {
    const { q, add } = make(async (i) => {
      if (i.label === "mauvais") throw new HttpError(400, { hours: ["Le nombre d'heures doit être strictement positif."] });
    });
    await add("mauvais");
    await add("bon");
    const r = await q.flush("u1");
    expect(r).toMatchObject({ sent: 1, failed: 1, remaining: 1, stopped: false });
    const [rest] = await q.list("u1");
    expect(rest.status).toBe("failed");
    expect(rest.error).toContain("strictement positif");
  });

  it("401 (session expirée) et 5xx stoppent sans marquer en échec", async () => {
    for (const status of [401, 503]) {
      const { q, add } = make(async () => {
        throw new HttpError(status);
      });
      await add("a");
      const r = await q.flush("u1");
      expect(r.stopped).toBe(true);
      expect((await q.list("u1"))[0].status).toBe("pending");
    }
  });

  it("un échec peut être relancé ou abandonné", async () => {
    let ok = false;
    const { q, add } = make(async () => {
      if (!ok) throw new HttpError(400, { detail: "x" });
    });
    const item = await add("a");
    await q.flush("u1");
    expect((await q.list("u1"))[0].status).toBe("failed");
    ok = true;
    await q.retry(item.id);
    expect((await q.flush("u1")).sent).toBe(1);
    const second = await add("b");
    ok = false;
    await q.flush("u1");
    await q.discard(second.id);
    expect(await q.list("u1")).toHaveLength(0);
  });

  it("deux synchronisations simultanées n'envoient qu'une fois", async () => {
    const send = vi.fn(async () => {
      await new Promise((r) => setTimeout(r, 10));
    });
    const { q, add } = make(send);
    await add("a");
    await Promise.all([q.flush("u1"), q.flush("u1")]);
    expect(send).toHaveBeenCalledTimes(1);
  });

  it("une saisie n'est synchronisée que par son auteur (jamais sous l'identité d'un autre)", async () => {
    const sent: string[] = [];
    const { q } = make(async (i) => void sent.push(`${i.owner}:${i.label}`));
    await q.enqueue({ owner: "u1", path: "/api/x/", body: {}, label: "a" });
    await q.enqueue({ owner: "u2", path: "/api/x/", body: {}, label: "b" });
    await q.flush("u2");
    expect(sent).toEqual(["u2:b"]);
    expect(await q.list("u1")).toHaveLength(1); // la saisie de u1 attend toujours
    await q.flush("u1");
    expect(sent).toEqual(["u2:b", "u1:a"]);
  });

  it("notifie les abonnés (compteur d'éléments en attente)", async () => {
    const { q, add } = make(async () => undefined);
    const seen: number[] = [];
    q.subscribe(async () => void seen.push((await q.list("u1")).length));
    await add("a");
    await q.flush("u1");
    await new Promise((r) => setTimeout(r, 0));
    expect(seen.length).toBeGreaterThan(0);
  });

  it("un conflit (409) est signalé puis levé par « Forcer » (même clé, drapeau force)", async () => {
    const vus: QueuedRequest[] = [];
    const { q, add } = make(async (i) => {
      vus.push(i);
      if (!i.force) throw new HttpError(409, { detail: "Pointage identique déjà enregistré (doublon probable)" });
    });
    const item = await add("a");
    const r = await q.flush("u1");
    expect(r).toMatchObject({ sent: 0, failed: 0, conflicts: 1, stopped: false });
    const [c] = await q.list("u1");
    expect(c.status).toBe("conflict");
    expect(c.error).toContain("doublon");
    await q.force(item.id);
    expect((await q.flush("u1")).sent).toBe(1);
    expect(vus[0].key).toBe(vus[1].key);
    expect(q.lastSyncAt()).not.toBeNull();
  });

  it("une photo attend la saisie parente puis reçoit son identifiant ({ref})", async () => {
    const envoyes: { path: string; body: unknown }[] = [];
    const q = createQueue(memoryStorage(), async (i) => {
      envoyes.push({ path: i.path, body: i.body });
      return i.path === "/api/hse/permis/" ? { id: "P-42" } : {};
    });
    const parent = await q.enqueue({ owner: "u1", path: "/api/hse/permis/", body: { emplacement: "Rack" }, label: "permis" });
    await q.enqueue({
      owner: "u1", path: "/api/hse/permis/{ref}/joindre-photo/", body: { legende: "zone" }, label: "photo",
      dependsOn: parent.key, files: [{ field: "fichier", name: "zone.jpg", type: "image/jpeg", blob: new Blob(["x"]) }],
    });
    await q.enqueue({ owner: "u1", path: "/api/qualite/images-controle/", body: { controle: "{ref}" }, label: "img",
      dependsOn: parent.key });
    const r = await q.flush("u1");
    expect(r.sent).toBe(3);
    expect(envoyes[1].path).toBe("/api/hse/permis/P-42/joindre-photo/");
    expect(envoyes[2].body).toEqual({ controle: "P-42" });
  });

  it("la photo d'une saisie en échec attend ; abandonner la saisie abandonne sa photo", async () => {
    const q = createQueue(memoryStorage(), async (i) => {
      if (i.label === "permis") throw new HttpError(400, { detail: "refus" });
    });
    const parent = await q.enqueue({ owner: "u1", path: "/api/hse/permis/", body: {}, label: "permis" });
    await q.enqueue({ owner: "u1", path: "/api/hse/permis/{ref}/joindre-photo/", body: {}, label: "photo",
      dependsOn: parent.key });
    const r = await q.flush("u1");
    expect(r).toMatchObject({ sent: 0, failed: 1, remaining: 2 });
    expect((await q.list("u1"))[1].status).toBe("pending");
    await q.discard(parent.id);
    expect(await q.list("u1")).toHaveLength(0);
  });
});
