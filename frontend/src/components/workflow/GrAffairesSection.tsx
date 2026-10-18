import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatNumber } from "../../lib/format";
import { describeError } from "../../lib/offlineQueue";
import type { GrAffairesResult, Paginated, ParametreLogistique } from "../../types";
import { Badge, SectionCard } from "../ui";

const montant = (v: string | null) => (v === null ? "••••••" : formatNumber(Number(v)));
const moisCourant = () => new Date().toISOString().slice(0, 7);

/**
 * Flux compteurs → M11 : coût GLOBAL RENTAL du mois ventilé par affaire (compte 618 isolé), avec la marge
 * après coût GR quand l'exercice est connu. Valeurs de valorisation provisoires tant qu'ETSL ne les confirme pas.
 */
export function GrAffairesSection({ fiscalYear }: { fiscalYear?: number | string }) {
  const { t } = useTranslation();
  const [periode, setPeriode] = useState(moisCourant());
  const suffixe = fiscalYear !== undefined ? `&fiscal_year=${fiscalYear}` : "";
  const q = useQuery({
    queryKey: ["cg-gr-affaires", periode, fiscalYear],
    queryFn: () => api.get<GrAffairesResult>(`/api/controle-gestion/gr-affaires/?periode=${periode}${suffixe}`),
    enabled: /^\d{4}-\d{2}$/.test(periode),
    retry: 0,
  });
  if (q.isError && !q.data) return null; // pas de droit de lecture M11 : la section n'apparaît pas

  return (
    <SectionCard title={t("grAffaires.title")}>
      <div data-testid="gr-affaires">
        <p className="muted">{t("grAffaires.hint")}</p>
        <label>
          {t("grAffaires.periode")}{" "}
          <input type="month" value={periode} onChange={(e) => setPeriode(e.target.value)} aria-label={t("grAffaires.periode")} />
        </label>
        {q.data?.provisoire && (
          <p className="action-error" role="note" data-testid="alerte-provisoire-gr">{t("grAffaires.warnProvisoire")}</p>
        )}
        {q.data && q.data.rows.length === 0 && <p className="muted">{t("grAffaires.aucun")}</p>}
        {q.data && q.data.rows.length > 0 && (
          <table className="table">
            <thead>
              <tr>
                <th>{t("grAffaires.affaire")}</th>
                <th className="num">{t("grAffaires.consommation")}</th>
                <th className="num">{t("grAffaires.coutGr")}</th>
                <th className="num">{t("grAffaires.penalites")}</th>
                {fiscalYear !== undefined && <th className="num">{t("grAffaires.margeApresGr")}</th>}
              </tr>
            </thead>
            <tbody>
              {q.data.rows.map((r) => (
                <tr key={r.affaire ?? "non-affecte"}>
                  <td>{r.affaire ? `${r.affaire} — ${r.titre}` : <Badge tone="warn">{r.titre}</Badge>}</td>
                  <td className="num">{formatNumber(Number(r.consommation))}</td>
                  <td className="num">{montant(r.cout_gr)}</td>
                  <td className="num">{montant(r.penalites)}</td>
                  {fiscalYear !== undefined && <td className="num">{r.marge_apres_gr === null ? "—" : montant(r.marge_apres_gr)}</td>}
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {q.data && (
          <p>
            {t("grAffaires.total")} (618) : <strong>{montant(q.data.total_gr)}</strong>
          </p>
        )}
      </div>
    </SectionCard>
  );
}

/** Paramètres M4 (fenêtre glissante, horizon, jours par mois) : modifiables par ETSL, provisoires puis confirmés. */
export function ParametresLogistiqueSection() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [edit, setEdit] = useState<{ id: string; valeur: string } | null>(null);
  const params = useQuery({
    queryKey: ["log-parametres"],
    queryFn: () => api.get<Paginated<ParametreLogistique>>("/api/logistique/parametres/").then((p) => p.results),
    retry: 0,
  });
  const refresh = () => void qc.invalidateQueries({ queryKey: ["log-parametres"] });
  const modifier = useMutation({
    mutationFn: (v: { id: string; valeur: string }) => api.patch(`/api/logistique/parametres/${v.id}/`, { valeur: v.valeur }),
    onSuccess: () => {
      setEdit(null);
      setError(null);
      refresh();
      void qc.invalidateQueries({ queryKey: ["cg-gr-affaires"] });
    },
    onError: (e) => setError(describeError(e)),
  });
  const confirmer = useMutation({
    mutationFn: (id: string) => api.post(`/api/logistique/parametres/${id}/confirmer/`),
    onSuccess: () => {
      setError(null);
      refresh();
    },
    onError: (e) => setError(describeError(e)),
  });

  if (params.isError) return null;
  const provisoires = (params.data ?? []).filter((p) => p.est_provisoire).length;
  return (
    <SectionCard title={t("paramLogistique.title")}>
      <div data-testid="parametres-logistique">
        <p className="muted">{t("paramLogistique.hint")}</p>
        {provisoires > 0 && (
          <p className="action-error" role="note" data-testid="alerte-provisoire-logistique">
            {t("paramLogistique.warnProvisoire", { count: provisoires })}
          </p>
        )}
        {error && <p className="action-error" role="alert">{error}</p>}
        <table className="table">
          <tbody>
            {(params.data ?? []).map((p) => (
              <tr key={p.id}>
                <td>{p.label}</td>
                <td>
                  {edit?.id === p.id ? (
                    <input type="number" min="1" step="1" aria-label={p.label} value={edit.valeur} onChange={(e) => setEdit({ id: p.id, valeur: e.target.value })} />
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
                        <button type="button" className="btn ghost" onClick={() => window.confirm(t("paramLogistique.confirmConfirmer")) && confirmer.mutate(p.id)}>
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
