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
  Wrench,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { motion } from "motion/react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { api } from "../api/client";
import { ChartCard, EmptyState, ErrorState, Kpi, KpiGridSkeleton, PageHeader, ProgressBar, SectionTitle, Sparkline } from "../components/ui";
import { formatNumber } from "../lib/format";
import { useThemeMode } from "../lib/useThemeMode";
import { motionTokens, paletteFor } from "../theme/tokens";
import type { AlerteEcheanceItem, AlertesAgregees, DashboardDirection, ReportingPetrolier, Tendances } from "../types";

const BANDE_ORDER = ["j90", "j60", "j30", "j15", "j0", "expiree"] as const;
const BANDE_TONE: Record<string, "ok" | "warn" | "err" | "brand"> = {
  j90: "ok",
  j60: "warn",
  j30: "warn",
  j15: "err",
  j0: "err",
  expiree: "err",
};

type Tone = "err" | "warn";
interface Urgent {
  key: string;
  count: number;
  tone: Tone;
  to: string;
  Icon: LucideIcon;
}

export function DirectionPage() {
  return <DirectionInner />;
}

/** Tuile KPI cliquable vers le module concerné (accessible : un seul lien, focus visible). */
function KpiLink({ to, children }: { to: string; children: React.ReactNode }) {
  return (
    <Link to={to} className="kpi-link">
      {children}
    </Link>
  );
}

function DirectionInner() {
  const { t } = useTranslation();
  const mode = useThemeMode();
  const c = paletteFor(mode);
  const chart = { axis: c.textMuted, grid: c.border, tooltipBg: c.surface, tooltipBorder: c.border, tooltipText: c.text };

  const direction = useQuery({ queryKey: ["direction"], queryFn: () => api.dashboardDirection() });
  const petrolier = useQuery({ queryKey: ["petrolier"], queryFn: () => api.reportingPetrolier() });
  const alertes = useQuery({ queryKey: ["alertes-agregees"], queryFn: () => api.alertesAgregees() });
  const tendances = useQuery({ queryKey: ["tendances"], queryFn: () => api.tendances(), retry: 0 });

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
  const tr = tendances.data as Tendances | undefined;
  const taux = (p.asmr.taux_disponibilite * 100).toFixed(1);
  const j4 = d.controle_gestion.conformite_j4;
  const j4Taux = Math.round(j4.taux * 100);

  const delay = (i: number) => Math.min(i * 0.05, 0.8);

  // « À traiter maintenant » : uniquement ce qui est non nul, le plus grave d'abord.
  const urgents: Urgent[] = (
    [
      { key: "expirees", count: a.compteurs.expiree ?? 0, tone: "err", to: "#echeances", Icon: CalendarDays },
      { key: "j15", count: (a.compteurs.j0 ?? 0) + (a.compteurs.j15 ?? 0), tone: "err", to: "#echeances", Icon: CalendarDays },
      { key: "ncCritiques", count: p.qualite.nc_critiques, tone: "err", to: "/qualite", Icon: AlertTriangle },
      { key: "incidents", count: d.hse.incidents_ouverts, tone: "err", to: "/hse", Icon: ShieldAlert },
      { key: "atex", count: p.hse.equipements_atex_quarantaine, tone: "err", to: "/hse", Icon: Flame },
      { key: "panne", count: p.asmr.en_panne, tone: "err", to: "/maintenance", Icon: Wrench },
      { key: "j30", count: a.compteurs.j30 ?? 0, tone: "warn", to: "#echeances", Icon: CalendarDays },
      { key: "soudeurs", count: p.qualite.soudeurs_expires, tone: "warn", to: "/qualite", Icon: Award },
      { key: "epi", count: p.hse.epi_a_renouveler, tone: "warn", to: "/hse", Icon: UserCheck },
    ] as Urgent[]
  ).filter((u) => u.count > 0);

  const flotte = [
    { name: t("direction.operationnels"), value: p.asmr.operationnels, color: c.ok },
    { name: t("direction.enPanne"), value: p.asmr.en_panne, color: c.err },
    { name: t("direction.enMaintenance"), value: p.asmr.en_maintenance, color: c.warn },
    { name: t("direction.horsService"), value: p.asmr.hors_service, color: c.textMuted },
  ].filter((f) => f.value > 0);

  const statutData = d.documents.par_statut.map((s) => ({ status: s.status, count: s.count }));

  const echeances: AlerteEcheanceItem[] = [
    ...a.documents,
    ...(a.juridique.conventions ?? []),
    ...(a.juridique.cautions ?? []),
    ...(a.juridique.assurances ?? []),
    ...a.rh,
  ]
    .filter((e) => e.jours !== null)
    .sort((x, y) => (x.jours ?? 0) - (y.jours ?? 0))
    .slice(0, 8);

  const tooltipStyle = {
    background: chart.tooltipBg,
    border: `1px solid ${chart.tooltipBorder}`,
    borderRadius: "10px",
    color: chart.tooltipText,
    fontSize: 13,
  };

  const trends: { key: keyof Tendances["series"]; label: string; color: string }[] = [
    { key: "documents", label: t("direction.trend.documents"), color: c.brand },
    { key: "incidents", label: t("direction.trend.incidents"), color: c.accent },
    { key: "ordres_travail", label: t("direction.trend.ordres"), color: c.warn },
  ];

  return (
    <>
      <PageHeader title={t("direction.title")} subtitle={t("direction.subtitle")} />

      {/* À traiter maintenant */}
      <section className="urgent" aria-label={t("direction.urgent")}>
        <h3 className="urgent-title">{t("direction.urgent")}</h3>
        {urgents.length === 0 ? (
          <p className="urgent-none">
            <CheckCircle2 size={18} /> {t("direction.urgentNone")}
          </p>
        ) : (
          <div className="urgent-chips">
            {urgents.map(({ key, count, tone, to, Icon }, i) => {
              const inner = (
                <motion.span
                  className={`urgent-chip ${tone}`}
                  initial={{ opacity: 0, y: motionTokens.distance.xs }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: motionTokens.duration.base, delay: delay(i) }}
                >
                  <Icon size={16} aria-hidden="true" />
                  <strong>{count}</strong> {t(`direction.urgentItems.${key}`)}
                </motion.span>
              );
              return to.startsWith("#") ? (
                <a key={key} href={to} className="kpi-link">
                  {inner}
                </a>
              ) : (
                <Link key={key} to={to} className="kpi-link">
                  {inner}
                </Link>
              );
            })}
          </div>
        )}
      </section>

      {/* Indicateurs de pilotage */}
      <div className="hero-grid">
        <div className="card hero">
          <span className="hero-label">{t("direction.heroDispo")}</span>
          <span className="hero-value">{taux} %</span>
          <ProgressBar label={t("direction.heroDispo")} value={Number(taux)} tone={Number(taux) >= 85 ? "ok" : Number(taux) >= 60 ? "warn" : "err"} />
          <span className="hero-hint">
            {p.asmr.operationnels}/{p.asmr.equipements} {t("direction.operationnels").toLowerCase()}
          </span>
        </div>
        <div className="card hero">
          <span className="hero-label">{t("direction.heroSecurite")}</span>
          <span className="hero-value">{p.hse.jours_sans_accident ?? "—"}</span>
          <span className="hero-hint">
            {p.hse.jours_sans_accident === null
              ? t("direction.noAccident")
              : `${t("direction.joursSansAccident")} · ${t("direction.u.accidents", { count: p.hse.accidents })}`}
          </span>
        </div>
        <div className="card hero">
          <span className="hero-label">{t("direction.heroCloture")}</span>
          <span className="hero-value">
            {j4.conformes}/{j4.periodes}
          </span>
          <ProgressBar label={t("direction.heroCloture")} value={j4Taux} tone={j4Taux >= 80 ? "ok" : j4Taux >= 50 ? "warn" : "err"} />
          <span className="hero-hint">{j4Taux} % J+4</span>
        </div>
      </div>

      {/* Tendances */}
      <SectionTitle>{t("direction.tendances")}</SectionTitle>
      <div className="trend-grid">
        {trends.map(({ key, label, color }) => {
          const values = tr?.series[key];
          return (
            <div className="card trend" key={key}>
              <span className="kpi-label">{label}</span>
              {values ? (
                <>
                  <span className="trend-value">{values[values.length - 1]}</span>
                  <Sparkline values={values} color={color} label={label} />
                  <span className="trend-axis">
                    {tr!.mois[0]} → {tr!.mois[tr!.mois.length - 1]}
                  </span>
                </>
              ) : (
                <span className="muted">{t("direction.noData")}</span>
              )}
            </div>
          );
        })}
      </div>

      <SectionTitle>{t("direction.directionKPIs")}</SectionTitle>
      <div className="kpi-grid">
        <KpiLink to="/">
          <Kpi label={t("direction.documentsRetention")} value={d.documents.total} hint={t("direction.u.dossiers", { count: d.documents.dossiers })} icon={FolderOpen} tone="brand" delay={delay(0)} />
        </KpiLink>
        <KpiLink to="/pipeline">
          <Kpi label={t("nav.pipeline")} value={d.commercial.opportunites_ouvertes} hint={d.commercial.ca_gagne !== null ? `${formatNumber(d.commercial.ca_gagne)} F` : "••••••"} icon={TrendingUp} tone="accent" delay={delay(1)} />
        </KpiLink>
        <KpiLink to="/stocks">
          <Kpi label={t("nav.stocks")} value={d.stocks.lots} hint={d.stocks.valorisation !== null ? `${formatNumber(d.stocks.valorisation)} F` : "••••••"} icon={Boxes} tone="brand" delay={delay(2)} />
        </KpiLink>
        <KpiLink to="/hse">
          <Kpi label={t("nav.hse")} value={d.hse.incidents_ouverts} hint={`${d.hse.jours_sans_accident ?? "—"} ${t("direction.joursSansAccident")}`} icon={ShieldAlert} tone="err" delay={delay(3)} />
        </KpiLink>
        <KpiLink to="/rh-paie">
          <Kpi label={t("nav.rhPaie")} value={d.rh_paie.effectif} hint={t("direction.u.bulletins", { count: d.rh_paie.bulletins_mois })} icon={Users} tone="brand" delay={delay(4)} />
        </KpiLink>
        <KpiLink to="/controle-gestion">
          <Kpi label={t("direction.annuel")} value={`${j4.conformes}/${j4.periodes}`} hint={`${j4Taux}% J+4`} icon={CalendarDays} tone="ok" delay={delay(5)} />
        </KpiLink>
        <KpiLink to="/juridique">
          <Kpi label={t("nav.juridique")} value={d.juridique.contentieux_ouverts} hint={t("direction.u.courriers", { count: d.juridique.courriers })} icon={Scale} tone="err" delay={delay(6)} />
        </KpiLink>
        <KpiLink to="/controle-gestion">
          <Kpi label={t("nav.controleGestion")} value={d.controle_gestion.clotures_realisees} hint={t("direction.u.budgets", { count: d.controle_gestion.budgets_approuves })} icon={CheckCircle2} tone="brand" delay={delay(7)} />
        </KpiLink>
      </div>

      <div className="chart-grid">
        <ChartCard title={t("direction.asmr")} subtitle={`${taux} % · ${p.asmr.operationnels}/${p.asmr.equipements}`} height={230}>
          {flotte.length === 0 ? (
            <EmptyState label={t("direction.noData")} />
          ) : (
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
          )}
        </ChartCard>

        <ChartCard title={t("dashboard.byType") ?? "Documents par statut"} height={230}>
          {statutData.length === 0 ? (
            <EmptyState label={t("direction.noData")} />
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={statutData} margin={{ top: 8, right: 8, left: -14, bottom: 0 }}>
                <CartesianGrid stroke={chart.grid} strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="status" stroke={chart.axis} fontSize={12} tickLine={false} axisLine={false} angle={-18} textAnchor="end" height={42} />
                <YAxis stroke={chart.axis} fontSize={12} tickLine={false} axisLine={false} allowDecimals={false} />
                <Tooltip contentStyle={tooltipStyle} />
                <Bar dataKey="count" fill={c.brand} radius={[6, 6, 0, 0]} maxBarSize={42} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </ChartCard>
      </div>

      <SectionTitle>{t("direction.reportPetrolier")}</SectionTitle>
      <div className="kpi-grid">
        <Kpi label={t("direction.tauxDisponibilite")} value={`${taux} %`} hint={`${p.asmr.operationnels}/${p.asmr.equipements}`} icon={Gauge} tone="ok" delay={delay(0)} />
        <Kpi label={t("direction.joursSansAccident")} value={p.hse.jours_sans_accident ?? "—"} hint={t("direction.u.accidents", { count: p.hse.accidents })} icon={ShieldCheck} tone="ok" delay={delay(1)} />
        <Kpi label={t("direction.ncOuvertes")} value={p.qualite.nc_ouvertes} hint={t("direction.u.critiques", { count: p.qualite.nc_critiques })} icon={AlertTriangle} tone="warn" delay={delay(2)} />
        <Kpi label={t("direction.soudeursQualifies")} value={p.qualite.soudeurs_qualifies} hint={t("direction.u.expires", { count: p.qualite.soudeurs_expires })} icon={Award} tone="brand" delay={delay(3)} />
        <Kpi label={t("direction.permisAtex")} value={p.hse.permis_atex} hint={t("direction.u.quarantaine", { count: p.hse.equipements_atex_quarantaine })} icon={Flame} tone="warn" delay={delay(4)} />
        <Kpi label={t("direction.epiRenouveler")} value={p.hse.epi_a_renouveler} hint={t("direction.u.permisActifs", { count: p.hse.permis_actifs })} icon={UserCheck} tone="accent" delay={delay(5)} />
      </div>

      <section id="echeances">
        <SectionTitle>{`${t("direction.alertes")} · ${a.total}`}</SectionTitle>
        <div className="kpi-grid">
          {BANDE_ORDER.map((bande, i) => (
            <Kpi key={bande} label={t(`juridique.bande.${bande}`)} value={a.compteurs[bande] ?? 0} tone={BANDE_TONE[bande]} delay={delay(i)} />
          ))}
        </div>

        <h4 className="subtitle">{t("direction.echeances")}</h4>
        {echeances.length === 0 ? (
          <p className="muted">{t("direction.aucuneEcheance")}</p>
        ) : (
          <ol className="timeline">
            {echeances.map((el, i) => (
              <motion.li
                key={`${el.type}-${el.code ?? i}-${i}`}
                className={`timeline-item ${BANDE_TONE[el.bande] ?? "ok"}`}
                initial={{ opacity: 0, x: -motionTokens.distance.sm }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: motionTokens.duration.base, delay: Math.min(i * 0.03, 0.3) }}
              >
                <span className="timeline-days">{(el.jours ?? 0) < 0 ? `${Math.abs(el.jours ?? 0)} j de retard` : `J-${el.jours}`}</span>
                <span className="timeline-body">
                  <strong>{el.libelle}</strong>
                  <span className="muted">
                    {el.type} · {el.code ?? "—"} · {el.date_echeance ?? "—"}
                  </span>
                </span>
                <span className={`badge ${BANDE_TONE[el.bande] ?? "ok"}`}>{t(`juridique.bande.${el.bande}`) ?? el.bande}</span>
              </motion.li>
            ))}
          </ol>
        )}
      </section>
    </>
  );
}
