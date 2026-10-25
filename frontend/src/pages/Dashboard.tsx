import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Archive, ArrowRight, FileText, ListChecks, SlidersHorizontal, Timer } from "lucide-react";
import { Link } from "react-router-dom";
import { Bar, BarChart, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { paletteFor } from "../theme/tokens";
import { useThemeMode } from "../lib/useThemeMode";
import { formatDate, formatMoney, formatNumber, formatPercent } from "../lib/format";
import { cleanLabel } from "../components/workflow/libelle";
import { HeroStat, toneFor } from "../components/direction/HeroStat";
import { DataGrid, EmptyState, ErrorState, Kpi, KpiGridSkeleton, PageHeader, SectionCard } from "../components/ui";
import type { GridColumn } from "../components/ui";
import { useAuth } from "../store/auth";
import type { DashboardDirection, ReportingPetrolier } from "../types";

/**
 * Rôles qui voient le bandeau « paramètres provisoires à confirmer par ETSL » (écarts transverses) : l'administration
 * technique seulement (A-02) — rien en tête d'écran pour la Direction, qui confirme depuis « Paramètres ETSL ».
 */
const ROLES_PARAMETRES = ["admin"];
/** Longueur maximale d'un libellé d'axe (le libellé complet reste dans l'infobulle). */
const MAX_LABEL = 32;
/** Rôles à qui l'accueil propose l'accès direct à la vue Direction / BI (A-01). */
const ROLES_VUE_DIRECTION = ["admin", "pdg", "dga", "direction"];
const BAR_ROW = 34;
/** Objectifs des chiffres héros (mêmes seuils que la page Direction). */
const OBJECTIF = { ok: 90, warn: 70 };

/** « 210 000 000 FCFA » → nombre + unité (affichée plus petite), montant exact, « •••••• » si masqué. */
function splitMoney(v: number | null | undefined): { value: string; unit?: string } {
  if (v === null || v === undefined) return { value: "••••••" };
  const m = /^(.*)\s(FCFA)$/u.exec(formatMoney(v));
  return m ? { value: m[1], unit: m[2] } : { value: formatMoney(v) };
}

/**
 * Chiffres clés de la Direction en tête de l'accueil (A04) : chiffre d'affaires signé, disponibilité du matériel,
 * sécurité, clôtures dans les délais. Mêmes requêtes (et cache) que la page Direction ; rien si indisponible.
 */
function HerosDirection() {
  const { t } = useTranslation();
  const direction = useQuery({ queryKey: ["direction"], queryFn: () => api.dashboardDirection(), retry: 0 });
  const petrolier = useQuery({ queryKey: ["petrolier"], queryFn: () => api.reportingPetrolier(), retry: 0 });
  if (!direction.data || !petrolier.data) return null;
  const d = direction.data as DashboardDirection;
  const p = petrolier.data as ReportingPetrolier;
  const ca = splitMoney(d.commercial.ca_gagne);
  const dispo = p.asmr.taux_disponibilite * 100;
  const dispoTone = toneFor(dispo, OBJECTIF.ok, OBJECTIF.warn);
  const jsa = p.hse.jours_sans_accident;
  const accidents = p.hse.accidents;
  const securiteTone = jsa === null ? "ok" : jsa < 30 ? "err" : jsa < 90 ? "warn" : "ok";
  const cloture = d.controle_gestion.conformite_j4.taux * 100;
  const clotureTone = toneFor(cloture, OBJECTIF.ok, OBJECTIF.warn);
  return (
    <section className="dir-heroes" aria-label={t("direction2.heros")} data-testid="accueil-heros">
      <HeroStat
        label={t("direction2.ca.label")}
        value={ca.value}
        unit={ca.unit}
        compact
        foot={t("direction2.ca.affaires", { count: d.commercial.affaires_actives })}
      />
      <HeroStat
        label={t("direction.heroDispo")}
        value={formatPercent(dispo, { decimals: dispo % 1 ? 1 : 0 })}
        tone={dispoTone}
        status={t(`direction2.statut.${dispoTone}`)}
        gauge={{ value: dispo, target: OBJECTIF.ok, ok: OBJECTIF.ok, warn: OBJECTIF.warn, label: t("direction.heroDispo") }}
        hint={t("direction2.dispo.hint", { ok: p.asmr.operationnels, total: p.asmr.equipements })}
        delay={0.04}
      />
      <HeroStat
        label={t("direction.heroSecurite")}
        value={formatNumber(jsa ?? accidents)}
        unit={jsa === null ? t("direction2.securite.accidents", { count: accidents }) : t("direction2.securite.jours", { count: jsa })}
        tone={securiteTone}
        hint={t("premiumPilotage.direction.securite.declaresTotal", { count: accidents })}
        delay={0.08}
      />
      <HeroStat
        label={t("direction2.cloture.label")}
        value={formatPercent(cloture)}
        tone={clotureTone}
        status={t(`direction2.statut.${clotureTone}`)}
        gauge={{ value: cloture, target: OBJECTIF.ok, ok: OBJECTIF.ok, warn: OBJECTIF.warn, label: t("direction2.cloture.label") }}
        delay={0.12}
      />
    </section>
  );
}

/** Libellé d'axe court : sans la précision entre parenthèses (« Pièces d'achat (BC, réception…) » → « Pièces d'achat »). */
const court = (s: string) => {
  const base = s.replace(/\s*\([^)]*\)?\s*$/, "").trim() || s;
  return base.length > MAX_LABEL ? `${base.slice(0, MAX_LABEL - 1).trimEnd()}…` : base;
};

export function DashboardPage() {
  const { t, i18n } = useTranslation();
  const mode = useThemeMode();
  const c = paletteFor(mode);
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["dashboard"],
    queryFn: api.dashboard,
  });
  const role = useAuth((s) => s.user?.role) ?? "";
  const resume = useQuery({
    queryKey: ["parametres-etsl-resume"],
    queryFn: api.parametresEtslResume,
    enabled: ROLES_PARAMETRES.includes(role),
    retry: 0,
  }).data;

  const header = (
    <PageHeader
      title={t("dashboard.title")}
      subtitle={t("dashboard.subtitle")}
      actions={
        ROLES_VUE_DIRECTION.includes(role) ? (
          <Link className="btn" to="/direction">
            {t("premiumPilotage.dashboard.vueDirection")}
            <ArrowRight size={15} aria-hidden />
          </Link>
        ) : undefined
      }
    />
  );
  if (isLoading)
    return (
      <>
        {header}
        <KpiGridSkeleton count={4} />
      </>
    );
  if (isError || !data)
    return (
      <>
        {header}
        <ErrorState message={t("common.error")} onRetry={() => void refetch()} retryLabel={t("common.retry")} />
      </>
    );

  const avg = data.workflow.avg_processing_days;
  const archives = data.documents.by_status?.archived ?? 0;
  // Répartition : triée décroissante, type vide nommé « Non classé », libellés sans référence d'exigence.
  const chartData = data.documents.by_type
    .map((row) => ({ name: row.type__label ? cleanLabel(row.type__label) : t("dashboard2.nonClasse"), count: row.count }))
    .sort((x, y) => y.count - x.count)
    .slice(0, 8);
  const retentionRows = data.retention.due.map((d) => ({ ...d, id: d.id }));
  const retentionCols: GridColumn<(typeof retentionRows)[number]>[] = [
    {
      key: "doc",
      header: t("dashboard.documents"),
      render: (d) => (
        <>
          <strong>{d.titre}</strong> <span className="muted">· {cleanLabel(d.type)}</span>
        </>
      ),
      sortValue: (d) => d.titre,
    },
    { key: "fin", header: t("dashboard2.finConservation"), render: (d) => formatDate(d.retention_fin, i18n.language), sortValue: (d) => d.retention_fin },
  ];

  return (
    <>
      {header}

      {ROLES_VUE_DIRECTION.includes(role) ? <HerosDirection /> : null}

      {/* A05 : rappel discret (une ligne, ton neutre) — ce n'est pas une alerte pour la Direction. */}
      {resume && resume.provisoires > 0 ? (
        <div className="banner neutral" role="status" data-testid="kpi-parametres-provisoires">
          <SlidersHorizontal size={16} aria-hidden />
          <div className="banner-body">
            <span className="banner-text">{t("dashboard2.provisoires", { count: resume.provisoires })}</span>
          </div>
          <Link className="banner-action" to="/parametres">
            {t("direction2.ouvrirParametres")}
          </Link>
        </div>
      ) : null}

      <div className="kpi-grid">
        <Kpi
          label={t("dashboard.documents")}
          value={data.documents.total}
          hint={t("dashboard2.archives", { count: archives })}
          icon={FileText}
          tone="brand"
          delay={0}
        />
        <Kpi
          label={t("dashboard.workflowPending")}
          value={data.workflow.pending}
          hint={data.workflow.overdue ? t("dashboard2.enRetard", { count: data.workflow.overdue }) : t("dashboard2.aucunRetard")}
          icon={data.workflow.overdue ? AlertTriangle : ListChecks}
          tone={data.workflow.overdue ? "err" : "brand"}
          delay={0.04}
        />
        <Kpi
          label={t("dashboard.avgDays")}
          value={avg === null ? "—" : t("dashboard2.jours", { n: formatNumber(avg, { decimals: avg % 1 ? 1 : 0 }) })}
          hint={avg === null ? t("dashboard2.aucunCircuitTermine") : t("dashboard2.parValidation")}
          icon={Timer}
          tone="neutral"
          delay={0.08}
        />
        <Kpi
          label={t("dashboard.retention")}
          value={data.retention.due_count}
          hint={t("dashboard.retentionDue")}
          icon={Archive}
          tone={data.retention.due_count ? "warn" : "neutral"}
          delay={0.12}
        />
      </div>

      {/* A04 : sans fin de conservation proche, le KPI « 0 » suffit — la répartition passe en pleine largeur. */}
      <div className={retentionRows.length ? "dash-split" : undefined}>
        <SectionCard title={t("dashboard.byType")} subtitle={t("dashboard2.byTypeSub", { count: data.documents.total })}>
          {chartData.length === 0 ? (
            <EmptyState label={t("common.empty")} compact />
          ) : (
            <div style={{ height: chartData.length * BAR_ROW + 8 }} role="img" aria-label={chartData.map((r) => `${r.name} ${r.count}`).join(", ")}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} layout="vertical" margin={{ top: 0, right: 40, left: 0, bottom: 0 }} barCategoryGap={8}>
                  <XAxis type="number" hide allowDecimals={false} />
                  <YAxis
                    type="category"
                    dataKey="name"
                    width={220}
                    tickLine={false}
                    axisLine={false}
                    stroke={c.textMuted}
                    fontSize={12.5}
                    tickFormatter={court}
                  />
                  <Tooltip
                    cursor={{ fill: c.brandSoft }}
                    contentStyle={{ background: c.surface, border: `1px solid ${c.border}`, borderRadius: 8, color: c.text, fontSize: 12 }}
                    formatter={(v) => [formatNumber(Number(v)), t("dashboard.documents")]}
                  />
                  <Bar dataKey="count" fill={c.brand} radius={[0, 4, 4, 0]} maxBarSize={18} isAnimationActive={false}>
                    <LabelList dataKey="count" position="right" fill={c.text} fontSize={12} formatter={(v: unknown) => formatNumber(Number(v))} />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </SectionCard>

        {retentionRows.length ? (
          <SectionCard title={t("dashboard.retention")} subtitle={t("dashboard2.retentionSub", { count: data.retention.due.length })}>
            <DataGrid columns={retentionCols} rows={retentionRows} caption={t("dashboard.retention")} density="compact" maxHeight={360} />
          </SectionCard>
        ) : null}
      </div>
    </>
  );
}
