import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { EMPTY, formatMoney, formatParametre, formatPercent } from "../../lib/format";
import { describeError } from "../../lib/offlineQueue";
import type { AtterrissageResult, DoctrineResult, NiveauxMarge, ParametreGestion, SousActiviteResult } from "../../types";
import { Badge, DataTable, SectionCard } from "../ui";
import type { Column } from "../ui";

/** Montant exact en FCFA (« 1 089 983 419 FCFA ») ; masqué si l'API ne l'expose pas. */
const montant = (v: string | null) => (v === null ? "••••••" : formatMoney(v));
/** Taux en points servi par l'API (« 47.24 ») → « 47,24 % » ; entier sans décimales (« 5 % »). */
const pourcent = (v: string | number | null | undefined) => {
  if (v === null || v === undefined || v === "") return EMPTY;
  const n = Number(v);
  return formatPercent(v, { decimals: Number.isInteger(n) ? 0 : 2 });
};

/**
 * Pilotage M11 : sous-activité par centre (90 / 91 / 99), doctrine d'imputation Mix A/B/C et paramètres.
 * Les seuils et cibles sont des données ETSL, provisoires tant qu'elles ne sont pas confirmées.
 */
export function PilotageGestionSection({ fiscalYear }: { fiscalYear: number | string | undefined }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [edit, setEdit] = useState<{ id: string; valeur: string } | null>(null);
  // Paramètres repliés par défaut, ouverts tant que des valeurs provisoires attendent ETSL ; le choix de l'utilisateur prime ensuite.
  const [ouvert, setOuvert] = useState<boolean | null>(null);
  const enabled = fiscalYear !== undefined;

  const params = useQuery({
    queryKey: ["cg-parametres"],
    queryFn: () => api.listAll<ParametreGestion>("/api/controle-gestion/parametres/"),
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

  const niveaux = useQuery({
    queryKey: ["cg-niveaux-marge", fiscalYear],
    queryFn: () => api.get<NiveauxMarge>(`/api/controle-gestion/niveaux-marge/?fiscal_year=${fiscalYear}`),
    enabled,
    retry: 0,
  });
  const atterrissage = useQuery({
    queryKey: ["cg-atterrissage", fiscalYear],
    queryFn: () => api.get<AtterrissageResult>(`/api/controle-gestion/atterrissage/?fiscal_year=${fiscalYear}`),
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
  const colonnes: Column<ParametreGestion>[] = [
    { key: "libelle", header: t("revueKit.fin.parametre"), render: (p) => p.label, sortValue: (p) => p.label, width: 260 },
    {
      key: "valeur",
      header: t("revueKit.fin.valeur"),
      num: true,
      render: (p) =>
        edit?.id === p.id ? (
          <input
            type="number"
            min="0"
            step="0.01"
            className="control"
            aria-label={p.label}
            value={edit.valeur}
            onChange={(e) => setEdit({ id: p.id, valeur: e.target.value })}
          />
        ) : (
          <span className="cell-nowrap">{formatParametre(p.valeur, p.unite)}</span>
        ),
    },
    {
      key: "statut",
      header: t("revueKit.fin.statut"),
      render: (p) => <Badge tone={p.est_provisoire ? "warn" : "ok"}>{t(`pilotageGestion.${p.statut_valeur}`)}</Badge>,
      sortValue: (p) => p.statut_valeur,
    },
    {
      key: "actions",
      header: <span className="sr-only">{t("ui.actions")}</span>,
      render: (p) => (
        <div className="action-bar-buttons r3-nowrap">
          {edit?.id === p.id ? (
            <>
              <button type="button" className="btn primary sm" disabled={modifier.isPending} onClick={() => modifier.mutate(edit)}>
                {t("pilotageGestion.valider")}
              </button>
              <button type="button" className="btn ghost sm" onClick={() => setEdit(null)}>
                {t("pilotageGestion.annuler")}
              </button>
            </>
          ) : (
            <>
              <button type="button" className="btn ghost sm" onClick={() => setEdit({ id: p.id, valeur: p.valeur })}>
                {t("pilotageGestion.modifier")}
              </button>
              {p.est_provisoire && (
                <button
                  type="button"
                  className="btn ghost sm"
                  disabled={confirmer.isPending}
                  onClick={() => window.confirm(t("pilotageGestion.confirmConfirmer")) && confirmer.mutate(p.id)}
                >
                  {t("pilotageGestion.confirmer")}
                </button>
              )}
            </>
          )}
        </div>
      ),
    },
  ];

  return (
    <SectionCard title={t("pilotageGestion.title")}>
      <div data-testid="pilotage-gestion">
        <p className="muted">{t("pilotageGestion.hint")}</p>
        {error && <p className="action-error" role="alert">{error}</p>}

        <h4 className="section-heading">{t("pilotageGestion.niveaux")}</h4>
        {niveaux.data && (
          <table className="table" data-testid="niveaux-marge">
            <tbody>
              {(
                [
                  ["marge_brute", "taux_brute"],
                  ["marge_operationnelle", "taux_operationnelle"],
                  ["marge_nette", "taux_nette"],
                ] as const
              ).map(([m, tx]) => (
                <tr key={m}>
                  <td>{t(`pilotageGestion.${m}`)}</td>
                  <td className="num">{montant(niveaux.data[m])}</td>
                  <td className="num">{pourcent(niveaux.data[tx])}</td>
                </tr>
              ))}
              <tr>
                <td>{t("pilotageGestion.coutGr")}</td>
                <td className="num">{montant(niveaux.data.cout_gr)}</td>
                <td />
              </tr>
            </tbody>
          </table>
        )}
        <p className="muted">{t("pilotageGestion.niveauxHint")}</p>

        <h4 className="section-heading">{t("pilotageGestion.atterrissage")}</h4>
        {atterrissage.data && atterrissage.data.rows.length > 0 && (
          <table className="table">
            <thead>
              <tr>
                <th>{t("pilotageGestion.budget")}</th>
                <th className="num">{t("pilotageGestion.realise")}</th>
                <th className="num">{t("pilotageGestion.resteAVenir")}</th>
                <th className="num">{t("pilotageGestion.atterrissageCol")}</th>
                <th className="num">{t("pilotageGestion.ecartObjectif")}</th>
              </tr>
            </thead>
            <tbody>
              {atterrissage.data.rows.map((r) => (
                <tr key={r.budget}>
                  <td>{r.code} — {r.label}</td>
                  <td className="num">{montant(r.realise)}</td>
                  <td className="num">{montant(r.reste_a_venir)}</td>
                  <td className="num">{montant(r.atterrissage)}</td>
                  <td className="num">{montant(r.ecart_objectif)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {atterrissage.data && atterrissage.data.marge_a_terminaison !== null && (
          <p data-testid="marge-terminaison">{t("pilotageGestion.margeTerminaison")} : <strong>{montant(atterrissage.data.marge_a_terminaison)}</strong></p>
        )}

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
                  <td className="num">{pourcent(r.taux_sous_activite)}</td>
                  <td><Badge tone={r.centre === "99" ? "err" : r.centre === "91" ? "warn" : "ok"}>{t("pilotageGestion.centreN", { n: r.centre })}</Badge></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <h4 className="section-heading">{t("pilotageGestion.doctrine")}</h4>
        {doctrine.data && !doctrine.data.cible_coherente && (
          <div className="banner warn" role="note">
            <AlertTriangle size={18} aria-hidden />
            <div className="banner-body">
              <span className="banner-text">{t("pilotageGestion.cibleIncoherente")}</span>
            </div>
          </div>
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
                  <td className="num">{pourcent(l.part)}</td>
                  <td className="num cell-nowrap">{l.classe === "C" ? "≤ " : ""}{pourcent(l.cible)}</td>
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
        {provisoires > 0 && (
          <div className="banner warn" role="note" data-testid="alerte-provisoire-gestion">
            <AlertTriangle size={18} aria-hidden />
            <div className="banner-body">
              <span className="banner-text">{t("pilotageGestion.warnProvisoire", { count: provisoires })}</span>
            </div>
          </div>
        )}
        <details className="r3-repli" open={ouvert ?? provisoires > 0} onToggle={(e) => setOuvert(e.currentTarget.open)}>
          <summary>{t("revueKit.fin.voirParametres", { count: (params.data ?? []).length })}</summary>
          <DataTable columns={colonnes} rows={params.data ?? []} caption={t("pilotageGestion.params")} density="compact" />
        </details>
      </div>
    </SectionCard>
  );
}
