import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAuth } from "../store/auth";
import { api, ApiError } from "./client";

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const refuse = () => json(403, { detail: "Given token not valid for any token type", code: "token_not_valid" });

beforeEach(() => {
  useAuth.setState({ access: "ancien", refresh: "r", user: null, expiree: false });
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("client API : session expirée", () => {
  it("jeton refusé (401 ou 403 token_not_valid) : rafraîchit puis rejoue la requête", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(refuse())
      .mockResolvedValueOnce(json(200, { access: "neuf" }))
      .mockResolvedValueOnce(json(200, { ok: true }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(api.get("/api/reports/dashboard/")).resolves.toEqual({ ok: true });
    expect(useAuth.getState().access).toBe("neuf");
    expect(useAuth.getState().expiree).toBe(false);
  });

  it("rafraîchissement impossible : déconnexion avec le motif « session expirée »", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(json(401, {})).mockResolvedValueOnce(json(401, {})));
    await expect(api.get("/api/reports/dashboard/")).rejects.toBeInstanceOf(ApiError);
    expect(useAuth.getState().access).toBeNull();
    expect(useAuth.getState().expiree).toBe(true);
  });

  it("un 403 de droits (pas de jeton en cause) reste une erreur de la page, sans déconnexion", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(json(403, { detail: "Vous n'avez pas la permission." })));
    await expect(api.get("/api/rh-paie/bulletins/")).rejects.toMatchObject({ status: 403 });
    expect(useAuth.getState().access).toBe("ancien");
    expect(useAuth.getState().expiree).toBe(false);
  });
});
