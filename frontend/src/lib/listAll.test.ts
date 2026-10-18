import { describe, expect, it } from "vitest";
import { listAll } from "./listAll";
import type { Paginated } from "../types";

/** Faux serveur DRF : `total` éléments, pages de `page_size` (défaut 20). */
function fakeServer(total: number) {
  const calls: string[] = [];
  const fetchPage = async (path: string): Promise<Paginated<number>> => {
    calls.push(path);
    const qs = new URLSearchParams(path.split("?")[1]);
    const size = Number(qs.get("page_size") ?? 20);
    const page = Number(qs.get("page") ?? 1);
    const start = (page - 1) * size;
    const results = Array.from({ length: Math.max(0, Math.min(size, total - start)) }, (_, i) => start + i);
    return { count: total, next: start + size < total ? "next" : null, previous: null, results };
  };
  return { calls, fetchPage };
}

describe("listAll", () => {
  it("suit next jusqu'à épuiser la liste", async () => {
    const { calls, fetchPage } = fakeServer(1200);
    const all = await listAll(fetchPage, "/api/x/", { pageSize: 500 });
    expect(all).toHaveLength(1200);
    expect(calls).toHaveLength(3);
  });

  it("une seule requête si tout tient dans une page", async () => {
    const { calls, fetchPage } = fakeServer(7);
    expect(await listAll(fetchPage, "/api/x/")).toHaveLength(7);
    expect(calls).toHaveLength(1);
  });

  it("respecte le plafond de pages", async () => {
    const { calls, fetchPage } = fakeServer(1000);
    const all = await listAll(fetchPage, "/api/x/", { pageSize: 100, maxPages: 3 });
    expect(all).toHaveLength(300);
    expect(calls).toHaveLength(3);
  });

  it("conserve les filtres existants et remplace page_size", async () => {
    const { calls, fetchPage } = fakeServer(5);
    await listAll(fetchPage, "/api/x/?statut=ouvert&page_size=20");
    const qs = new URLSearchParams(calls[0].split("?")[1]);
    expect(qs.get("statut")).toBe("ouvert");
    expect(qs.get("page_size")).toBe("500");
  });
});
