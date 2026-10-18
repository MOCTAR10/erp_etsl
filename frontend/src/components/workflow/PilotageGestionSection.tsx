import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatNumber } from "../../lib/format";
import { describeError } from "../../lib/offlineQueue";
import type { DoctrineResult, Paginated, ParametreGestion, SousActiviteResult } from "../../types";
import { Badge, SectionCard } from "../ui";

const montant = (v: string | null) => (v === null ? "••••••" : formatNumber(Number(v)));

/**
 * Pilotage M11 : sous-activité par centre (90 / 91 / 99), doctrine d'imputation Mix A/B/C et paramètres.
 * Les seuils et cibles sont des données ETSL, provisoires tant qu'elles ne sont pas confirmées.
 */
export function PilotageGestionSection({ fiscalYear }: { fiscalYear: number | string | undefined }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [edit, setEdit] = useState<{ id: string; valeur: string } | null>(null);
  const enabled = fiscalYear !== undefined;

  const params = useQuery({
    queryKey: ["cg-parametres"],
    queryFn: () => api.get<Paginated<ParametreGestion>>("/api/controle-gestion/parametres/").then((p) => p.results),
    retry: 0,
  });
  const sousActivite = useQuery({
    queryKey: ["cg-sous-activite", fiscalYear],
    queryFn: () => api.get<SousActiviteResult>(`/api/controle-gestion/sous-activite/?fiscal_year=${fiscalYear}`),
    enabled,
    retry: 0,
  });
  const doctrine = useQuery({
    queryKey: ["cg-doctrine", fiscalYear],
    queryFn: () => api.get<DoctrineResult>(`/api/controle-gestion/doctrine/?fiscal_year=${fiscalYear}`),
    enabled,
    retry: 0,
  });

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["cg-parametres"] });
    void qc.invalidateQueries({ queryKey: ["cg-sous-activite"] });
    void qc.invalidateQueries({ queryKey: ["cg-doctrine"] });
  };
  const modifier = useMutation({
    mutationFn: (v: { id: string; valeur: string }) => api.patch(`/api/controle-gestion/parametres/${v.id}/`, { valeur: v.valeur }),
    onSuccess: () => {
      setEdit(null);
      setError(null);
      refresh();
    },
    onError: (e) => setError(describeError(e)),
  });
  const confirmer = useMutation({
    mutationFn: (id: string) => api.post(`/api/controle-gestion/parametres/${id}/confirmer/`),
    onSuccess: refresh,
    onError: (e) => setError(describeError(e)),
  });

  if (params.isError) return null; // pas de droit : la section n'apparaît pas
  const provisoires = (params.data ?? []).filter((p) => p.est_provisoire).length;

  return (
    <SectionCard title={t("pilotageGestion.title")}>
      <div data-testid="pilotage-gestion">
        <p className="muted">{t("pilotageGestion.hint")}</p>
        {provisoires > 0 && (
          <p className="action-error" role="note" data-testid="alerte-provisoire-gestion">
            {t("pilotageGestion.warnProvisoire", { count: provisoires })}
          </p>
        )}
        {error && <p className="action-error" role="alert">{error}</p>}

        <h4 className="section-heading">{t("pilotageGestion.sousActivite")}</h4>
        {sousActivite.data && sousActivite.data.rows.length === 0 && <p className="muted">{t("pilotageGestion.aucun")}</p>}
        {sousActivite.data && sousActivite.data.rows.length > 0 && (
          <table className="table">
            <thead>
              <tr>
                <th>{t("pilotageGestion.budget")}</th>
                <th className="num">{t("pilotageGestion.prevu")}</th>
                <th className="num">{t("pilotageGestion.realise")}</th>
                <th className="num">{t("pilotageGestion.taux")}</th>
                <th>{t("pilotageGestion.centre")}</th>
              </tr>
            </thead>
            <tbody>
              {sousActivite.data.rows.map((r) => (
                <tr key={r.budget}>
                  <td>{r.code} — {r.label}</td>
                  <td className="num">{montant(r.budget_ecoule)}</td>
                  <td className="num">{montant(r.realise)}</td>
                  <td className="num">{r.taux_sous_activite} %</td>
                  <td><Badge tone={r.centre === "99" ? "err" : r.centre === "91" ? "warn" : "ok"}>{t("pilotageGestion.centreN", { n: r.centre })}</Badge></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <h4 className="section-heading">{t("pilotageGestion.doctrine")}</h4>
        {doctrine.data && !doctrine.data.cible_coherente && (
          <p className="action-error" role="note">{t("pilotageGestion.cibleIncoherente")}</p>
        )}
        {doctrine.data && (
          <table className="table">
            <thead>
              <tr>
                <th>{t("pilotageGestion.classe")}</th>
                <th className="num">{t("pilotageGestion.montant")}</th>
                <th className="num">{t("pilotageGestion.part")}</th>
                <th className="num">{t("pilotageGestion.cible")}</th>
                <th>{t("pilotageGestion.conformite")}</th>
              </tr>
            </thead>
            <tbody>
              {doctrine.data.lignes.map((l) => (
                <tr key={l.classe}>
                  <td>Mix {l.classe}</td>
                  <td className="num">{montant(l.montant)}</td>
                  <td className="num">{l.part} %</td>
                  <td className="num">{l.classe === "C" ? "≤ " : ""}{l.cible} %</td>
                  <td>{l.conforme === null ? "—" : <Badge tone={l.conforme ? "ok" : "err"}>{l.conforme ? t("pilotageGestion.conforme") : t("pilotageGestion.ecart")}</Badge>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {doctrine.data && doctrine.data.non_classes > 0 && (
          <p className="muted">{t("pilotageGestion.nonClasses", { count: doctrine.data.non_classes })}</p>
        )}

        <h4 className="section-heading">{t("pilotageGestion.params")}</h4>
        <table className="table">
          <tbody>
            {(params.data ?? []).map((p) => (
              <tr key={p.id}>
                <td>{p.label}</td>
                <td>
                  {edit?.id === p.id ? (
                    <input type="number" min="0" step="0.01" aria-label={p.label} value={edit.valeur} onChange={(e) => setEdit({ id: p.id, valeur: e.target.value })} />
                  ) : (
                    `${p.valeur} ${p.unite}`
                  )}
                </td>
                <td><Badge tone={p.est_provisoire ? "warn" : "ok"}>{t(`pilotageGestion.${p.statut_valeur}`)}</Badge></td>
                <td>
                  {edit?.id === p.id ? (
                    <>
                      <button type="button" className="btn" onClick={() => modifier.mutate(edit)}>{t("pilotageGestion.valider")}</button>{" "}
                      <button type="button" className="btn ghost" onClick={() => setEdit(null)}>{t("pilotageGestion.annuler")}</button>
                    </>
                  ) : (
                    <>
                      <button type="button" className="btn ghost" onClick={() => setEdit({ id: p.id, valeur: p.valeur })}>{t("pilotageGestion.modifier")}</button>{" "}
                      {p.est_provisoire && (
                        <button type="button" className="btn ghost" onClick={() => window.confirm(t("pilotageGestion.confirmConfirmer")) && confirmer.mutate(p.id)}>
                          {t("pilotageGestion.confirmer")}
                        </button>
                      )}
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </SectionCard>
  );
}
