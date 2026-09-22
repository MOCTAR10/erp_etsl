import { useAuth } from "../store/auth";
import type { Me, Tokens } from "../types";

async function raw<T>(path: string, init?: RequestInit): Promise<T> {
  const auth = useAuth.getState();
  const headers = new Headers(init?.headers);
  if (auth.access) headers.set("Authorization", `Bearer ${auth.access}`);
  if (init?.body && typeof init.body === "string") {
    headers.set("Content-Type", "application/json");
  }

  const res = await fetch(path, { ...init, headers });

  if (res.status === 401 && auth.refresh) {
    try {
      const refreshed = await refreshToken(auth.refresh);
      useAuth.getState().setAccess(refreshed.access);
      const retry = await fetch(path, {
        ...init,
        headers: new Headers({
          ...Object.fromEntries(headers.entries()),
          Authorization: `Bearer ${refreshed.access}`,
        }),
      });
      if (retry.ok) return (await retry.json()) as T;
    } catch {
      useAuth.getState().clear();
    }
  }

  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}

async function postForm<T>(path: string, body: Record<string, string>): Promise<T> {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

/** Dépagination : les listes DRF sont paginées par défaut (count/results). */
async function rawList<T>(path: string): Promise<T[]> {
  const page = await raw<import("../types").Paginated<T>>(path);
  return page.results;
}

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(`HTTP ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

export async function login(email: string, password: string): Promise<{ user: Me; tokens: Tokens }> {
  const tokens = await postForm<Tokens>("/api/users/token/", { email, password });
  const user = await authenticatedMe(tokens.access);
  return { user, tokens };
}

async function refreshToken(refresh: string): Promise<{ access: string }> {
  return postForm<{ access: string }>("/api/users/token/refresh/", { refresh });
}

async function authenticatedMe(access: string): Promise<Me> {
  const res = await fetch("/api/users/me/", {
    headers: { Authorization: `Bearer ${access}` },
  });
  if (!res.ok) throw new ApiError(res.status, null);
  return (await res.json()) as Me;
}

export const api = {
  get: <T,>(path: string) => raw<T>(path),
  me: () => raw<Me>("/api/users/me/"),
  dashboard: () => raw<import("../types").DashboardData>("/api/reports/dashboard/"),
  tasks: () => rawList<import("../types").WorkflowTask>("/api/workflow/tasks/"),
  circuits: () => rawList<import("../types").Circuit>("/api/workflow/circuits/"),
  notifications: () => rawList<import("../types").NotificationItem>("/api/workflow/notifications/"),
  opportunities: () =>
    raw<import("../types").Paginated<import("../types").Opportunity>>("/api/commercial/opportunities/"),
  pipeline: () =>
    raw<import("../types").PipelineStats>("/api/commercial/opportunities/pipeline/"),
  purchaseOrders: (params = "") =>
    raw<import("../types").Paginated<import("../types").PurchaseOrder>>(`/api/achats/orders/${params}`),
  ordres: (params = "") =>
    raw<import("../types").Paginated<import("../types").OrdreFabrication>>(`/api/operations/ordres/${params}`),
  charge: () => raw<import("../types").ChargeStats>("/api/operations/ordres/charge/"),
  situations: (params = "") =>
    raw<import("../types").Paginated<import("../types").SituationTravaux>>(`/api/operations/situations/${params}`),
  equipements: (params = "") =>
    raw<import("../types").Paginated<import("../types").EquipementParc>>(`/api/logistique/equipements/${params}`),
  locationsGR: (params = "") =>
    raw<import("../types").Paginated<import("../types").LocationGR>>(`/api/logistique/locations/${params}`),
  demandesLog: (params = "") =>
    raw<import("../types").Paginated<import("../types").DemandeMobilisation>>(`/api/logistique/demandes/${params}`),
  parcStats: () => raw<import("../types").ParcStats>("/api/logistique/locations/stats/"),
};