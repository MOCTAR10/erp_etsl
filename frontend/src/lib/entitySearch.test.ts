import { describe, expect, it, vi } from "vitest";

import { ENTITY_SOURCES, searchEntities, type EntityFetcher } from "./entitySearch";

const page = (results: Record<string, unknown>[]) => ({ count: results.length, next: null, previous: null, results }) as never;

describe("searchEntities", () => {
  it("n'interroge que les sources lisibles par le rôle (GED toujours)", async () => {
    const fetcher = vi.fn<EntityFetcher>(async () => page([]));
    await searchEntities("bc", new AbortController().signal, ["rh_paie"], fetcher);
    const chemins = fetcher.mock.calls.map((c) => c[0]);
    expect(chemins).toEqual(["/api/rh-paie/employes/", "/api/documents/documents/"]);
  });

  it("fail-open sans `modules` : toutes les sources", async () => {
    const fetcher = vi.fn<EntityFetcher>(async () => page([]));
    await searchEntities("bc", new AbortController().signal, undefined, fetcher);
    expect(fetcher).toHaveBeenCalledTimes(ENTITY_SOURCES.length);
  });

  it("met en forme les résultats et ignore une source en erreur", async () => {
    const fetcher: EntityFetcher = async (path) => {
      if (path.includes("achats")) return page([{ id: 7, code: "BC-00007", supplier_name: "Total Gabon", status_label: "Émis" }]);
      if (path.includes("employes")) throw new Error("403");
      return page([]);
    };
    const groupes = await searchEntities("BC", new AbortController().signal, undefined, fetcher);
    expect(groupes).toHaveLength(1);
    expect(groupes[0].key).toBe("bc");
    expect(groupes[0].hits[0]).toMatchObject({ id: "ent-bc-7", label: "BC-00007", hint: "Total Gabon · Émis", route: "/purchases" });
  });

  it("transmet le signal d'annulation à chaque requête", async () => {
    const ctrl = new AbortController();
    const fetcher = vi.fn<EntityFetcher>(async () => page([]));
    await searchEntities("x", ctrl.signal, ["achats"], fetcher);
    for (const call of fetcher.mock.calls) expect(call[2]).toBe(ctrl.signal);
  });
});
