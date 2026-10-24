import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { TriangleAlert } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatMoney, formatParametre } from "../../lib/format";
import { describeError } from "../../lib/offlineQueue";
import type { GrAffairesResult, ParametreLogistique } from "../../types";
import { Badge, currentMonth, MonthPicker, SectionCard } from "../ui";
import { ParamsPanel } from "../parametres/ParamsPanel";
import { ParamValueTable } from "../parametres/ParamValueTable";

const montant = (v: string | null) => (v === null ? "••••••" : formatMoney(v));

/** Valeur lisible d'un paramètre (« 30 jours », « 50 000 000 FCFA ») ; espace simple avant l'unité finale. */
const valeurParametre = (valeur: string, unite: string) => formatParametre(valeur, unite).replace(/\u00a0(?=[^\d\u00a0]+$)/, " ");

/**
 * Flux compteurs → M11 : coût GLOBAL RENTAL du mois ventilé par affaire (compte 618 isolé), avec la marge
 * après coût GR quand l'exercice est connu. Valeurs de valorisation provisoires tant qu'ETSL ne les confirme pas.
 */
export function GrAffairesSection({ fiscalYear }: { fiscalYear?: number | string }) {
  const { t } = useTranslation();
  const [periode, setPeriode] = useState(currentMonth());
  const suffixe = fiscalYear !== undefined ? `&fiscal_year=${fiscalYear}` : "";
  const q = useQuery({
    queryKey: ["cg-gr-affaires", periode, fiscalYear],
    queryFn: () => api.get<GrAffairesResult>(`/api/controle-gestion/gr-affaires/?periode=${periode}${suffixe}`),
    enabled: /^\d{4}-\d{2}$/.test(periode),
    retry: 0,
  });
  if (q.isError && !q.data) return null; // pas de droit de lecture M11 : la section n'apparaît pas
  const champ = fiscalYear !== undefined ? "gr-affaires-mois-cg" : "gr-affaires-mois";

  return (
    <SectionCard title={t("grAffaires.title")}>
      <div data-testid="gr-affaires">
        <p className="muted">{t("grAffaires.hint")}</p>
        <div className="list-toolbar">
          <div className="field">
            <label htmlFor={champ}>{t("grAffaires.periode")}</label>
            <MonthPicker id={champ} value={periode} onChange={setPeriode} />
          </div>
        </div>
        {q.data?.provisoire && (
          <div className="banner warn" role="note" data-testid="alerte-provisoire-gr">
            <TriangleAlert size={18} aria-hidden />
            <div className="banner-body">
              <p className="banner-text">{t("grAffaires.warnProvisoire")}</p>
            </div>
          </div>
        )}
        {q.data && q.data.rows.length === 0 && <p className="muted">{t("revueKit.ops.gr.aucunePrestation")}</p>}
        {q.data && q.data.rows.length > 0 && (
          <table className="table">
            <thead>
              <tr>
                <th>{t("grAffaires.affaire")}</th>
                <th className="num">{t("grAffaires.consommation")}</th>
                <th className="num">{t("revueKit.ops.gr.cout")}</th>
                <th className="num">{t("grAffaires.penalites")}</th>
                {fiscalYear !== undefined && <th className="num">{t("revueKit.ops.gr.margeApres")}</th>}
              </tr>
            </thead>
            <tbody>
              {q.data.rows.map((r) => (
                <tr key={r.affaire ?? "non-affecte"}>
                  <td>{r.affaire ? `${r.affaire} — ${r.titre}` : <Badge tone="warn">{r.titre}</Badge>}</td>
                  <td className="num">{formatParametre(r.consommation, null)}</td>
                  <td className="num cell-nowrap">{montant(r.cout_gr)}</td>
                  <td className="num cell-nowrap">{montant(r.penalites)}</td>
                  {fiscalYear !== undefined && <td className="num cell-nowrap">{r.marge_apres_gr === null ? "—" : montant(r.marge_apres_gr)}</td>}
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {q.data && (
          <p>
            {t("revueKit.ops.gr.total")} (618) : <strong className="cell-nowrap">{montant(q.data.total_gr)}</strong>
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
  const params = useQuery({
    queryKey: ["log-parametres"],
    queryFn: () => api.listAll<ParametreLogistique>("/api/logistique/parametres/"),
    retry: 0,
  });
  const refresh = () => void qc.invalidateQueries({ queryKey: ["log-parametres"] });
  const modifier = useMutation({
    mutationFn: (v: { id: string; valeur: string }) => api.patch(`/api/logistique/parametres/${v.id}/`, { valeur: v.valeur }),
    onSuccess: () => {
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
    <ParamsPanel
      variant="card"
      module="logistique"
      title={t("paramLogistique.title")}
      count={params.data ? provisoires : undefined}
      total={params.data?.length}
      testId="parametres-logistique"
      alertTestId="alerte-provisoire-logistique"
    >
      <p className="muted">{t("paramLogistique.hint")}</p>
      {error && <p className="action-error" role="alert">{error}</p>}
      <ParamValueTable
        rows={params.data ?? []}
        caption={t("paramLogistique.title")}
        libelle={(p) => t(`revueKit.ops.param.libelles.${p.code}`, { defaultValue: p.label })}
        valeur={(p) => valeurParametre(p.valeur, p.unite)}
        min="1"
        pending={modifier.isPending || confirmer.isPending}
        confirmMessage={t("paramLogistique.confirmConfirmer")}
        onSave={(id, valeur) => modifier.mutateAsync({ id, valeur })}
        onConfirm={(id) => confirmer.mutate(id)}
      />
    </ParamsPanel>
  );
}
