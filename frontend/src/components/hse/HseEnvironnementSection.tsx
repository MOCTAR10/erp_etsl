import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate, formatNumber } from "../../lib/format";
import { describeError } from "../../lib/offlineQueue";
import type { IndicateursHse, PlanReductionImpact, RapportEnvironnemental, RevueDirectionHse } from "../../types";
import { SectionActions } from "../sections/SectionActions";
import { nombre } from "../sections/affichage";
import { ActionBar, Badge, DataTable, Kpi, QuickForm, SectionCard } from "../ui";
import type { Column } from "../ui";

const RESSOURCES = ["electricite", "gazole", "essence", "gaz", "eau"];
const pct = (v: string | null) => (v === null ? "—" : `${formatNumber(Number(v))} %`);

/** Indicateurs HSE au-delà des taux de fréquence : formation, recyclage, conformité ISO, environnement. */
export function IndicateursHseSection() {
  const { t } = useTranslation();
  const q = useQuery({ queryKey: ["hse-indicateurs"], queryFn: () => api.get<IndicateursHse>("/api/hse/incidents/indicateurs/"), retry: 0 });
  if (q.isError || !q.data) return null;
  const d = q.data;
  return (
    <SectionCard title={t("m7e.ind.title")}>
      <div className="kpis" data-testid="indicateurs-hse">
        <Kpi label={t("m7e.ind.formation")} value={pct(d.taux_formation)} hint={t("m7e.ind.formationHint", { n: d.salaries_formes, total: d.salaries_actifs })} />
        <Kpi label={t("m7e.ind.recyclage")} value={pct(d.taux_recyclage)} hint={t("m7e.ind.recyclageHint", { n: d.habilitations_a_jour, total: d.habilitations_suivies })} />
        <Kpi label={t("m7e.ind.iso")} value={pct(d.conformite_iso)} hint={t("m7e.ind.isoHint", { n: d.audits_realises })} />
        <Kpi label={t("m7e.ind.env")} value={nombre(d.taux_incidents_environnement)} hint={t("m7e.ind.envHint", { n: d.incidents_environnement })} />
      </div>
    </SectionCard>
  );
}

type LigneEnv = RapportEnvironnemental["environnement"]["lignes"][number] & { id: string };

/** Quantité exacte (décimales significatives conservées, séparateurs français). */
const quantite = (v: string) => {
  const dec = (String(Number(v)).split(".")[1] ?? "").length;
  return formatNumber(v, { decimals: Math.min(dec, 3) });
};

/** Environnement ISO 14001 : consommations mensuelles, émissions, plans de réduction, rapport annuel. */
export function EnvironnementSection() {
  const { t } = useTranslation();
  const [annee, setAnnee] = useState(String(new Date().getFullYear()));
  const rapport = useQuery({
    queryKey: ["hse-rapport-env", annee],
    queryFn: () => api.get<RapportEnvironnemental>(`/api/hse/consommations/rapport/?annee=${annee}`),
    retry: 0,
  });
  const plans = useQuery({ queryKey: ["hse-plans-reduction"], queryFn: () => api.listAll<PlanReductionImpact>("/api/hse/plans-reduction/"), retry: 0 });
  if (rapport.isError) return null;
  const ressources = RESSOURCES.map((v) => ({ value: v, label: t(`m7e.env.ressources.${v}`) }));
  const r = rapport.data;
  const lignes: LigneEnv[] = (r?.environnement.lignes ?? []).map((l) => ({ ...l, id: l.ressource }));
  const colLignes: Column<LigneEnv>[] = [
    { key: "ressource", header: t("m7e.env.ressource"), render: (l) => l.libelle },
    { key: "quantite", header: t("m7e.env.quantite"), num: true, sortValue: (l) => Number(l.quantite), render: (l) => `${quantite(l.quantite)} ${l.unite}` },
    {
      key: "emissions",
      header: "kg CO2e",
      num: true,
      sortValue: (l) => (l.emissions_kg_co2e === null ? null : Number(l.emissions_kg_co2e)),
      render: (l) => formatNumber(l.emissions_kg_co2e),
    },
  ];
  const colPlans: Column<PlanReductionImpact>[] = [
    { key: "plan", header: t("tableaux.hse.plan"), sortValue: (p) => p.code, render: (p) => <><strong>{p.code}</strong> · {p.objectif}</> },
    { key: "periode", header: t("tableaux.hse.periode"), render: (p) => `${p.ressource_label || "—"} · ${p.annee_reference ?? "—"} → ${p.annee_cible}` },
    {
      key: "avancement",
      header: t("tableaux.hse.avancement"),
      render: (p) =>
        p.avancement?.realise_pct != null ? (
          <Badge tone={p.avancement.atteint ? "ok" : "warn"}>
            {t("m7e.env.realise", { r: formatNumber(p.avancement.realise_pct, { decimals: 1 }), c: formatNumber(p.reduction_cible_pct, { decimals: 1 }) })}
          </Badge>
        ) : (
          <span className="muted">{p.statut_label}</span>
        ),
    },
  ];
  return (
    <SectionCard title={t("m7e.env.title")}>
      <div data-testid="environnement-hse">
        <SectionActions>
          <QuickForm
            title={t("m7e.env.releve")}
            endpoint="/api/hse/consommations/"
            fields={[
              { name: "ressource", label: t("m7e.env.ressource"), type: "select", required: true, defaultValue: "gazole", options: ressources },
              { name: "periode", label: t("m7e.env.mois"), type: "date", required: true },
              { name: "quantite", label: t("m7e.env.quantite"), type: "number", min: 0, step: "0.01", required: true },
              { name: "site", label: t("m7e.env.site") },
              { name: "source", label: t("m7e.env.source") },
            ]}
          />
          <QuickForm
            title={t("m7e.env.plan")}
            endpoint="/api/hse/plans-reduction/"
            fields={[
              { name: "objectif", label: t("m7e.env.objectif"), required: true },
              { name: "ressource", label: t("m7e.env.ressourceSuivie"), type: "select", options: ressources },
              { name: "annee_reference", label: t("m7e.env.anneeReference"), type: "number", min: 2000, step: "1" },
              { name: "annee_cible", label: t("m7e.env.anneeCible"), type: "number", min: 2000, step: "1", required: true },
              { name: "reduction_cible_pct", label: t("m7e.env.cible"), type: "number", min: 0, step: "0.1" },
              { name: "actions", label: t("m7e.env.actions"), type: "textarea" },
            ]}
          />
          <button type="button" className="btn ghost" onClick={() => void api.download(`/api/hse/consommations/rapport/?annee=${annee}&export=pdf`, `rapport-environnemental-${annee}.pdf`)}>
            {t("m7e.env.rapportPdf")}
          </button>
        </SectionActions>
        <div className="field">
          <label htmlFor="env-annee">{t("m7e.env.annee")}</label>
          <input id="env-annee" className="control" type="number" value={annee} min={2000} max={2100} onChange={(e) => setAnnee(e.target.value)} style={{ maxWidth: 140 }} />
        </div>
        {r && (
          <>
            <p>{t("m7e.env.emissions", { t: formatNumber(r.environnement.emissions_t_co2e, { decimals: 1 }), n: r.incidents_environnement })}</p>
            <DataTable columns={colLignes} rows={lignes} caption={t("m7e.env.title")} />
          </>
        )}
        {(plans.data ?? []).length > 0 && (
          <div data-testid="plans-reduction">
            <DataTable columns={colPlans} rows={plans.data ?? []} caption={t("m7e.env.plans")} />
          </div>
        )}
      </div>
    </SectionCard>
  );
}

/** Bilan HSE annuel et revue de direction : bilan figé, validation hiérarchique, compte rendu scellé en GED. */
export function RevueDirectionSection() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const q = useQuery({ queryKey: ["hse-revues"], queryFn: () => api.listAll<RevueDirectionHse>("/api/hse/revues-direction/"), retry: 0 });
  const completer = useMutation({
    mutationFn: (v: { id: string; body: Record<string, string> }) => api.patch(`/api/hse/revues-direction/${v.id}/`, v.body),
    onSuccess: () => {
      setError(null);
      void qc.invalidateQueries({ queryKey: ["hse-revues"] });
    },
    onError: (e) => setError(describeError(e)),
  });
  if (q.isError) return null;
  const annee = new Date().getFullYear();
  const columns: Column<RevueDirectionHse>[] = [
    {
      key: "revue",
      header: t("tableaux.hse.revue"),
      sortValue: (r) => r.date_revue,
      render: (r) => <><strong>{r.code}</strong> · {r.annee} · {formatDate(r.date_revue)}</>,
    },
    {
      key: "statut",
      header: t("tableaux.hse.statut"),
      render: (r) => <><Badge tone={r.statut === "validee" ? "ok" : "warn"}>{r.statut_label}</Badge>{r.document ? ` ${t("m7e.revue.archivee")}` : ""}</>,
    },
    {
      key: "actions",
      header: <span className="sr-only">{t("ui.actions")}</span>,
      render: (r) => (
        <div className="permis-actions">
          <button type="button" className="btn ghost" onClick={() => void api.download(`/api/hse/revues-direction/${r.id}/pdf/`, `${r.code}.pdf`)}>
            PDF
          </button>
          {r.statut !== "validee" && (
            <>
              <button
                type="button"
                className="btn ghost"
                onClick={() => {
                  const body: Record<string, string> = {};
                  for (const champ of ["participants", "conclusions", "decisions"] as const) {
                    const v = window.prompt(t(`m7e.revue.${champ}`), r[champ]);
                    if (v === null) return;
                    body[champ] = v;
                  }
                  completer.mutate({ id: r.id, body });
                }}
              >
                {t("m7e.revue.completer")}
              </button>
              <ActionBar
                actions={[
                  { label: t("m7e.revue.valider"), path: `/api/hse/revues-direction/${r.id}/valider/`, confirm: t("m7e.revue.confirmValider") },
                  { label: t("m7e.revue.actualiser"), path: `/api/hse/revues-direction/${r.id}/actualiser/`, tone: "ghost" },
                ]}
              />
            </>
          )}
        </div>
      ),
    },
  ];
  return (
    <SectionCard
      title={t("m7e.revue.title")}
      actions={
        <SectionActions>
          <QuickForm
            title={t("m7e.revue.nouvelle")}
            endpoint="/api/hse/revues-direction/"
            fields={[
              { name: "annee", label: t("m7e.revue.annee"), type: "number", min: 2000, step: "1", required: true, defaultValue: String(annee - 1) },
              { name: "date_revue", label: t("m7e.revue.date"), type: "date" },
              { name: "participants", label: t("m7e.revue.participants"), type: "textarea" },
              { name: "conclusions", label: t("m7e.revue.conclusions"), type: "textarea" },
              { name: "decisions", label: t("m7e.revue.decisions"), type: "textarea" },
            ]}
          />
          <button type="button" className="btn ghost" onClick={() => void api.download(`/api/hse/revues-direction/bilan/?annee=${annee}&export=pdf`, `bilan-hse-${annee}.pdf`)}>
            {t("m7e.revue.bilanPdf", { annee })}
          </button>
        </SectionActions>
      }
    >
      <div data-testid="revues-direction">
        {error && <p className="action-error" role="alert">{error}</p>}
        <DataTable columns={columns} rows={q.data ?? []} caption={t("m7e.revue.title")} emptyLabel={t("m7e.revue.aucune")} />
      </div>
    </SectionCard>
  );
}
