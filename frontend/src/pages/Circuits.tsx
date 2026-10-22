import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { ActionBar, BoardSkeleton, ErrorState, PageHeader, QuickForm } from "../components/ui";
import { useAuth } from "../store/auth";
import type { Circuit, Paginated } from "../types";

/** Rôles autorisés à modifier les circuits à chaud (EX-G-02) — le serveur reste la garde. */
const GESTION_CIRCUITS = ["admin", "pdg", "dga"];
const ROLES_ACTEURS = [
  "pdg", "dga", "secretaire_general", "directeur_projets", "directeur_operations", "rh", "finance", "qaqc", "hse",
  "logistique", "maintenance", "chef_atelier", "admin", "direction", "chef_service", "comptable",
];

export function CircuitsPage() {
  const { t } = useTranslation();
  const role = useAuth((s) => s.user?.role) ?? "";
  const gestion = GESTION_CIRCUITS.includes(role);
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["circuits", gestion],
    queryFn: () =>
      gestion
        ? api.get<Paginated<Circuit>>("/api/workflow/circuits/?tous=1&page_size=100").then((p) => p.results)
        : api.circuits(),
  });

  if (isLoading) return <BoardSkeleton cols={1} rows={3} />;
  if (isError || !data)
    return (
      <ErrorState message={t("common.error")} onRetry={() => void refetch()} retryLabel={t("common.retry")} />
    );

  const roleOpts = ROLES_ACTEURS.map((r) => ({ value: r, label: r }));

  return (
    <>
      <PageHeader title={t("circuits.title")} subtitle={gestion ? t("ecarts_tr.circuits.aide") : undefined} />
      {gestion ? (
        <div className="action-bar-buttons" style={{ marginBottom: "1rem" }}>
          <QuickForm
            title={t("ecarts_tr.circuits.nouveau")}
            endpoint="/api/workflow/circuits/"
            fields={[
              { name: "code", label: t("ecarts_tr.circuits.code"), required: true },
              { name: "label", label: t("ecarts_tr.circuits.libelle"), required: true },
              { name: "max_days", label: t("circuits.days"), type: "number", min: 1, required: true, defaultValue: "5" },
            ]}
          />
        </div>
      ) : null}
      {data.map((circuit) => (
        <div className="card" key={circuit.id} style={{ marginBottom: "1rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
            <h3 style={{ fontSize: 16, margin: 0 }}>
              {circuit.label} <span className="muted" style={{ fontWeight: 500 }}>({circuit.code})</span>
              <span className="muted" style={{ fontWeight: 500, fontSize: 13 }}> · {circuit.max_days} j</span>
            </h3>
            <span className={`badge ${circuit.is_active ? "ok" : "muted"}`}>
              {circuit.is_active ? t("circuits.active") : t("circuits.inactive")}
            </span>
          </div>
          {gestion ? (
            <ActionBar
              actions={[
                {
                  label: t("ecarts_tr.circuits.renommer"),
                  path: `/api/workflow/circuits/${circuit.id}/`,
                  tone: "ghost" as const,
                  method: "PATCH" as const,
                  prompt: { name: "label", label: t("ecarts_tr.circuits.libelle") },
                },
                {
                  label: circuit.is_active ? t("ecarts_tr.circuits.desactiver") : t("ecarts_tr.circuits.activer"),
                  path: `/api/workflow/circuits/${circuit.id}/`,
                  body: { is_active: !circuit.is_active },
                  tone: "ghost" as const,
                  method: "PATCH" as const,
                  confirm: t("ecarts_tr.circuits.confirmActivation"),
                },
              ]}
            />
          ) : null}
          <table className="table mt-1">
            <thead>
              <tr>
                <th>#</th>
                <th>{t("circuits.steps")}</th>
                <th>{t("circuits.actor")}</th>
                <th>{t("circuits.days")}</th>
                {gestion ? <th /> : null}
              </tr>
            </thead>
            <tbody>
              {circuit.steps.map((step) => (
                <tr key={step.id}>
                  <td className="muted">{step.order}</td>
                  <td>{step.name}</td>
                  <td>
                    <span className="badge brand">{step.actor_role_label}</span>
                  </td>
                  <td className="muted">{step.max_days} j</td>
                  {gestion ? (
                    <td>
                      <ActionBar
                        actions={[
                          { label: "↑", path: `/api/workflow/circuits/${circuit.id}/deplacer-etape/`, body: { etape: step.id, sens: "haut" }, tone: "ghost" },
                          { label: "↓", path: `/api/workflow/circuits/${circuit.id}/deplacer-etape/`, body: { etape: step.id, sens: "bas" }, tone: "ghost" },
                          {
                            label: t("ecarts_tr.circuits.delai"),
                            path: `/api/workflow/circuits/${circuit.id}/modifier-etape/`,
                            body: { etape: step.id },
                            tone: "ghost",
                            prompt: { name: "max_days", label: t("circuits.days") },
                          },
                          {
                            label: t("ecarts_tr.circuits.acteur"),
                            path: `/api/workflow/circuits/${circuit.id}/modifier-etape/`,
                            body: { etape: step.id },
                            tone: "ghost",
                            prompt: { name: "actor_role", label: t("circuits.actor"), options: roleOpts },
                          },
                          {
                            label: t("ecarts_tr.circuits.retirer"),
                            path: `/api/workflow/circuits/${circuit.id}/retirer-etape/`,
                            body: { etape: step.id },
                            tone: "danger",
                            confirm: t("ecarts_tr.circuits.confirmRetirer"),
                          },
                        ]}
                      />
                    </td>
                  ) : null}
                </tr>
              ))}
            </tbody>
          </table>
          {gestion ? (
            <QuickForm
              title={t("ecarts_tr.circuits.ajouterEtape")}
              endpoint={`/api/workflow/circuits/${circuit.id}/ajouter-etape/`}
              fields={[
                { name: "name", label: t("circuits.steps"), required: true },
                { name: "actor_role", label: t("circuits.actor"), type: "select", options: roleOpts, required: true },
                { name: "max_days", label: t("circuits.days"), type: "number", min: 1, defaultValue: "2" },
              ]}
            />
          ) : null}
        </div>
      ))}
    </>
  );
}
