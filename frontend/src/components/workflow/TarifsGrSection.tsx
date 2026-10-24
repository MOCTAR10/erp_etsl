import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate, formatMoney } from "../../lib/format";
import { describeError } from "../../lib/offlineQueue";
import type { EquipementParc, TarifGR } from "../../types";
import { QuickForm, SectionCard } from "../ui";

interface PartnerRef {
  id: string;
  code: string;
  name: string;
  is_global_rental: boolean;
}

const CATEGORIES = ["engin", "levage", "transport", "atelier", "materiel"] as const;
const PERIODICITES = ["heure", "jour", "mois", "forfait"] as const;
const montant = (v: string | null) => (v === null ? "••••••" : formatMoney(v));

/**
 * Grille tarifaire GLOBAL RENTAL (M4 §12.4 / §12.11) : versions datées, jamais réécrites. Un changement de tarif
 * = une nouvelle version (date d'effet) ; une version encore inutilisée peut être supprimée. La prestation retient
 * la version en vigueur à sa date de début, la plus spécifique d'abord (équipement, catégorie, générale).
 */
export function TarifsGrSection() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const tarifs = useQuery({ queryKey: ["logistique-tarifs-gr"], queryFn: () => api.listAll<TarifGR>("/api/logistique/tarifs-gr/"), retry: 0 });
  const partenaires = useQuery({
    queryKey: ["logistique-partenaires-gr"],
    queryFn: () => api.listAll<PartnerRef>("/api/referentiels/partners/"),
    select: (rows) => rows.filter((p) => p.is_global_rental),
    retry: 0,
  });
  const equipements = useQuery({
    queryKey: ["logistique-equipements-gr"],
    queryFn: () => api.listAll<EquipementParc>("/api/logistique/equipements/?global_rental=true"),
    retry: 0,
  });
  const supprimer = useMutation({
    mutationFn: (id: string) => api.remove(`/api/logistique/tarifs-gr/${id}/`),
    onSuccess: () => {
      setError(null);
      void qc.invalidateQueries({ queryKey: ["logistique-tarifs-gr"] });
    },
    onError: (e) => setError(describeError(e)),
  });

  if (tarifs.isError) return null; // pas de droit de lecture M4 : la section n'apparaît pas
  const rows = tarifs.data ?? [];

  const nouvelle = (
    <QuickForm
      title={t("tarifsGr.nouvelle")}
      endpoint="/api/logistique/tarifs-gr/"
      variant="secondary"
      fields={[
        {
          name: "partenaire", label: t("tarifsGr.partenaire"), type: "select", required: true,
          options: (partenaires.data ?? []).map((p) => ({ value: p.id, label: `${p.code} — ${p.name}` })),
        },
        {
          name: "equipement", label: t("tarifsGr.equipement"), type: "select",
          options: (equipements.data ?? []).map((e) => ({ value: e.id, label: `${e.code} — ${e.label}` })),
        },
        {
          name: "categorie", label: t("tarifsGr.categorie"), type: "select",
          options: CATEGORIES.map((c) => ({ value: c, label: t(`tarifsGr.cat.${c}`) })),
        },
        {
          name: "periodicite", label: t("tarifsGr.periodicite"), type: "select", required: true, defaultValue: "jour",
          options: PERIODICITES.map((p) => ({ value: p, label: t(`tarifsGr.per.${p}`) })),
        },
        { name: "tarif", label: t("tarifsGr.tarif"), type: "number", required: true, min: 0, step: "0.01" },
        { name: "penalite_jour", label: t("tarifsGr.penalite"), type: "number", min: 0, step: "0.01" },
        { name: "date_effet", label: t("tarifsGr.dateEffet"), type: "date", required: true },
      ]}
    />
  );

  return (
    // Le repère de test englobe la carte : le bouton de création est dans l'en-tête de la section.
    <div data-testid="tarifs-gr">
      <SectionCard title={`${t("tarifsGr.title")} · ${rows.length}`} actions={<div className="section-actions">{nouvelle}</div>}>
        <p className="muted">{t("tarifsGr.hint")}</p>
        {error && <p className="action-error" role="alert">{error}</p>}
        {rows.length === 0 ? (
          <p className="muted">{t("revueKit.ops.tarifs.aucun")}</p>
        ) : (
          <table className="table">
            <caption className="sr-only">{t("tarifsGr.title")}</caption>
            <thead>
              <tr>
                <th>{t("tarifsGr.code")}</th>
                <th>{t("revueKit.ops.tarifs.partenaire")}</th>
                <th>{t("tarifsGr.cible")}</th>
                <th>{t("tarifsGr.periodicite")}</th>
                <th className="num">{t("tarifsGr.tarif")}</th>
                <th className="num">{t("tarifsGr.penalite")}</th>
                <th>{t("tarifsGr.dateEffet")}</th>
                <th>{t("tarifsGr.version")}</th>
                <th><span className="sr-only">{t("revueKit.ops.param.actions")}</span></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td className="cell-nowrap"><strong>{r.code}</strong></td>
                  <td>{r.partenaire_code}</td>
                  <td>
                    {r.equipement_code ??
                      (r.categorie ? t(`tarifsGr.cat.${r.categorie}`, { defaultValue: r.categorie_label }) : t("tarifsGr.generale"))}
                  </td>
                  <td>{t(`tarifsGr.per.${r.periodicite}`, { defaultValue: r.periodicite_label })}</td>
                  <td className="num cell-nowrap">{montant(r.tarif)}</td>
                  <td className="num cell-nowrap">{montant(r.penalite_jour)}</td>
                  <td className="cell-nowrap"><time dateTime={r.date_effet}>{formatDate(r.date_effet)}</time></td>
                  <td>v{r.version}</td>
                  <td>
                    <div className="card-actions card-actions--end">
                      <button
                        type="button"
                        className="btn ghost sm"
                        disabled={supprimer.isPending}
                        onClick={() => window.confirm(t("tarifsGr.confirmSupprimer")) && supprimer.mutate(r.id)}
                      >
                        {t("tarifsGr.supprimer")}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </SectionCard>
    </div>
  );
}
