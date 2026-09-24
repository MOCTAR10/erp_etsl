import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  Award,
  Boxes,
  CalendarDays,
  CheckCircle2,
  Flame,
  FolderOpen,
  Gauge,
  Scale,
  ShieldAlert,
  ShieldCheck,
  TrendingUp,
  UserCheck,
  Users,
} from "lucide-react";
import { Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { motionTokens } from "../theme/tokens";
import { paletteFor } from "../theme/tokens";
import { useThemeMode } from "../lib/useThemeMode";
import { formatNumber } from "../lib/format";
import { ChartCard, ErrorState, Kpi, KpiGridSkeleton, PageHeader, SectionTitle } from "../components/ui";
import type { AlertesAgregees, DashboardDirection, ReportingPetrolier } from "../types";
import { motion } from "motion/react";

const BANDE_ORDER = ["j90", "j60", "j30", "expiree"] as const;
const BANDE_TONE: Record<string, "ok" | "warn" | "err" | "brand"> = {
  j90: "ok",
  j60: "warn",
  j30: "warn",
  expiree: "err",
};

export function DirectionPage() {
  return <DirectionInner />;
}

function DirectionInner() {
  const { t } = useTranslation();
  const mode = useThemeMode();
  const c = paletteFor(mode);
  const chart = {
    axis: c.textMuted,
    grid: c.border,
    tooltipBg: c.surface,
    tooltipBorder: c.border,
    tooltipText: c.text,
  };

  const direction = useQuery({
    queryKey: ["direction"],
    queryFn: () => api.dashboardDirection(),
  });
  const petrolier = useQuery({
    queryKey: ["petrolier"],
    queryFn: () => api.reportingPetrolier(),
  });
  const alertes = useQuery({
    queryKey: ["alertes-agregees"],
    queryFn: () => api.alertesAgregees(),
  });

  if (direction.isPending || petrolier.isPending || alertes.isPending) {
    return <KpiGridSkeleton count={8} />;
  }
  if (direction.isError || petrolier.isError || alertes.isError) {
    return (
      <ErrorState
        message={t("common.error")}
        onRetry={() => {
          void direction.refetch();
          void petrolier.refetch();
          void alertes.refetch();
        }}
        retryLabel={t("common.retry")}
      />
    );
  }

  const d = direction.data as DashboardDirection;
  const p = petrolier.data as ReportingPetrolier;
  const a = alertes.data as AlertesAgregees;
  const taux = (p.asmr.taux_disponibilite * 100).toFixed(1);
  const j4 = d.controle_gestion.conformite_j4;
  const j4Taux = (j4.taux * 100).toFixed(0);

  const kpi = 0.04;
  const kpiDelay = (i: number) => Math.min(i * 0.05, kpi * 20);

  const flotte = [
    { name: t("direction.operationnels"), value: p.asmr.operationnels, color: c.ok },
    { name: t("direction.enPanne"), value: p.asmr.en_panne, color: c.err },
    { name: t("direction.enMaintenance"), value: p.asmr.en_maintenance, color: c.warn },
    { name: t("direction.horsService"), value: p.asmr.hors_service, color: c.textMuted },
  ].filter((f) => f.value > 0);

  const statutData = d.documents.par_statut.map((s) => ({ status: s.status, count: s.count }));

  const listes: { clé: string; items: { type: string; code: string | null; libelle: string; date_echeance: string | null; bande: string; jours: number | null }[] }[] = [
    { clé: "documents", items: a.documents },
    {
      clé: "juridique",
      items: [...(a.juridique.conventions ?? []), ...(a.juridique.cautions ?? []), ...(a.juridique.assurances ?? [])],
    },
    { clé: "rh", items: a.rh },
    { clé: "maintenance", items: a.maintenance },
  ];

  const tooltipStyle = {
    background: chart.tooltipBg,
    border: `1px solid ${chart.tooltipBorder}`,
    borderRadius: "10px",
    color: chart.tooltipText,
    fontSize: 13,
  };

  return (
    <>
      <PageHeader title={t("direction.title")} subtitle={t("direction.subtitle")} />

      <SectionTitle>{t("direction.directionKPIs")}</SectionTitle>
      <div className="kpi-grid">
        <Kpi label={t("direction.documentsRetention")} value={d.documents.total} hint={`${d.documents.dossiers} dossiers`} icon={FolderOpen} tone="brand" delay={kpiDelay(0)} />
        <Kpi label={t("nav.pipeline")} value={d.commercial.opportunites_ouvertes} hint={d.commercial.ca_gagne !== null ? `${formatNumber(d.commercial.ca_gagne)} F` : "••••••"} icon={TrendingUp} tone="accent" delay={kpiDelay(1)} />
        <Kpi label={t("nav.stocks")} value={d.stocks.lots} hint={d.stocks.valorisation !== null ? `${formatNumber(d.stocks.valorisation)} F` : "••••••"} icon={Boxes} tone="brand" delay={kpiDelay(2)} />
        <Kpi label={t("nav.hse")} value={d.hse.incidents_ouverts} hint={`${d.hse.jours_sans_accident ?? "—"} ${t("direction.joursSansAccident")}`} icon={ShieldAlert} tone="err" delay={kpiDelay(3)} />
        <Kpi label={t("nav.rhPaie")} value={d.rh_paie.effectif} hint={`${d.rh_paie.bulletins_mois} bulletins`} icon={Users} tone="brand" delay={kpiDelay(4)} />
        <Kpi label={t("direction.annuel")} value={`${j4.conformes}/${j4.periodes}`} hint={`${j4Taux}% J+4`} icon={CalendarDays} tone="ok" delay={kpiDelay(5)} />
        <Kpi label={t("nav.juridique")} value={d.juridique.contentieux_ouverts} hint={`${d.juridique.courriers} courriers`} icon={Scale} tone="err" delay={kpiDelay(6)} />
        <Kpi label={t("nav.controleGestion")} value={d.controle_gestion.clotures_realisees} hint={`${d.controle_gestion.budgets_approuves} budgets`} icon={CheckCircle2} tone="brand" delay={kpiDelay(7)} />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: "1rem" }}>
        <ChartCard title={t("direction.asmr")} subtitle={`${taux} % · ${p.asmr.operationnels}/${p.asmr.equipements}`} height={230}>
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={flotte} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius="55%" outerRadius="80%" paddingAngle={2} strokeWidth={0}>
                {flotte.map((f) => (
                  <Cell key={f.name} fill={f.color} />
                ))}
              </Pie>
              <Tooltip contentStyle={tooltipStyle} />
            </PieChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title={t("dashboard.byType") ?? "Documents par statut"} height={230}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={statutData} margin={{ top: 8, right: 8, left: -14, bottom: 0 }}>
              <CartesianGrid stroke={chart.grid} strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="status" stroke={chart.axis} fontSize={12} tickLine={false} axisLine={false} angle={-18} textAnchor="end" height={42} />
              <YAxis stroke={chart.axis} fontSize={12} tickLine={false} axisLine={false} allowDecimals={false} />
              <Tooltip contentStyle={tooltipStyle} />
              <Bar dataKey="count" fill={c.brand} radius={[6, 6, 0, 0]} maxBarSize={42} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      <SectionTitle>{t("direction.reportPetrolier")}</SectionTitle>
      <div className="kpi-grid">
        <Kpi label={t("direction.tauxDisponibilite")} value={`${taux} %`} hint={`${p.asmr.operationnels}/${p.asmr.equipements}`} icon={Gauge} tone="ok" delay={kpiDelay(0)} />
        <Kpi label={t("direction.joursSansAccident")} value={p.hse.jours_sans_accident ?? "—"} hint={`${p.hse.accidents} accidents`} icon={ShieldCheck} tone="ok" delay={kpiDelay(1)} />
        <Kpi label="NC ouvertes" value={p.qualite.nc_ouvertes} hint={`${p.qualite.nc_critiques} critiques`} icon={AlertTriangle} tone="warn" delay={kpiDelay(2)} />
        <Kpi label="Soudeurs qualifiés" value={p.qualite.soudeurs_qualifies} hint={`${p.qualite.soudeurs_expires} expirés`} icon={Award} tone="brand" delay={kpiDelay(3)} />
        <Kpi label="Permis ATEX" value={p.hse.permis_atex} hint={`${p.hse.equipements_atex_quarantaine} quarantaine`} icon={Flame} tone="warn" delay={kpiDelay(4)} />
        <Kpi label="EPI à renouveler" value={p.hse.epi_a_renouveler} hint={`${p.hse.permis_actifs} permis actifs`} icon={UserCheck} tone="accent" delay={kpiDelay(5)} />
      </div>

      <SectionTitle>{`${t("direction.alertes")} · ${a.total}`}</SectionTitle>
      <div className="kpi-grid">
        {BANDE_ORDER.map((bande, i) => (
          <Kpi
            key={bande}
            label={t(`juridique.bande.${bande}`)}
            value={a.compteurs[bande] ?? 0}
            tone={BANDE_TONE[bande]}
            delay={kpiDelay(i)}
          />
        ))}
      </div>

      {a.total > 0 && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: "0.75rem" }}>
          {listes.flatMap(({ items }, li) =>
            items.map((el, i) => (
              <motion.div
                key={`${el.type}-${el.code ?? i}`}
                layout
                initial={{ opacity: 0, y: motionTokens.distance.xs, scale: 0.98 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                transition={{ duration: motionTokens.duration.base, ease: motionTokens.ease.out, delay: Math.min(li * 0.05 + i * 0.02, 0.4) }}
                className="card kpi"
              >
                <span className="kpi-head">
                  <span className="kpi-label">
                    {el.type} · {el.code ?? "—"}
                  </span>
                  <span className={`badge ${BANDE_TONE[el.bande] ?? "ok"}`}>{t(`juridique.bande.${el.bande}`) ?? el.bande}</span>
                </span>
                <span className="kpi-value" style={{ fontSize: 18 }}>{el.libelle}</span>
                <span className="kpi-hint">
                  {el.date_echeance ?? "—"} · {el.jours !== null ? `${el.jours} j` : "—"}
                </span>
              </motion.div>
            )),
          )}
        </div>
      )}
    </>
  );
}