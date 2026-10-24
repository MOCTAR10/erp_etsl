import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  Award,
  Boxes,
  CalendarClock,
  CalendarX2,
  Factory,
  Flame,
  Scale,
  ShieldAlert,
  ShoppingCart,
  TrendingUp,
  UserCheck,
  Users,
  Wrench,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import { AttentionList } from "../components/direction/AttentionList";
import type { AttentionItem } from "../components/direction/AttentionList";
import { DirectionExports } from "../components/direction/DirectionExports";
import { EcheancesSection } from "../components/direction/Echeances";
import { HeroStat, toneFor } from "../components/direction/HeroStat";
import { PilotageSection } from "../components/direction/Pilotage";
import { ReportingSection } from "../components/direction/Reporting";
import { TrendPanel } from "../components/direction/TrendPanel";
import type { IndicateursCommerciaux, Pilotage } from "../components/direction/types";
import { ErrorState, Kpi, KpiGridSkeleton, PageHeader, SectionNav, Skeleton } from "../components/ui";
import { formatMoney, formatNumber, formatPercent } from "../lib/format";
import type { AlertesAgregees, DashboardDirection, ReportingPetrolier, Tendances } from "../types";

/** Objectifs de pilotage affichés sur les chiffres héros (seuils vert / orange, en %). */
const OBJECTIF_DISPO = { ok: 90, warn: 70 };
const OBJECTIF_CLOTURE = { ok: 90, warn: 70 };

type DashboardDirectionPlus = DashboardDirection & {
  commercial: DashboardDirection["commercial"] & { pipe_pondere?: number | null; indicateurs?: IndicateursCommerciaux };
};

/** Tuile KPI cliquable vers le module concerné (un seul lien, focus visible). */
function KpiLink({ to, children }: { to: string; children: React.ReactNode }) {
  return (
    <Link to={to} className="kpi-link">
      {children}
    </Link>
  );
}

/** Montant masqué (hors cercle des montants) : « •••••• », sinon montant exact. */
const montant = (v: number | null | undefined) => (v === null || v === undefined ? "••••••" : formatMoney(v));

/** Sépare « 210 000 000 FCFA » en nombre + unité (affichée plus petite) sans jamais abréger. */
function splitMoney(v: number | null | undefined): { value: string; unit?: string } {
  const text = montant(v);
  const m = /^(.*)\s(FCFA)$/u.exec(text);
  return m ? { value: m[1], unit: m[2] } : { value: text };
}

function DirectionSkeleton() {
  return (
    <>
      <div className="dir-heroes">
        {[0, 1, 2, 3].map((i) => (
          <div className="card dir-hero" key={i} aria-hidden>
            <Skeleton style={{ height: 14, width: "60%" }} />
            <Skeleton style={{ height: 40, width: "45%" }} />
            <Skeleton style={{ height: 8, width: "100%" }} />
            <Skeleton style={{ height: 12, width: "70%" }} />
          </div>
        ))}
      </div>
      <KpiGridSkeleton count={8} />
    </>
  );
}

export function DirectionPage() {
  const { t } = useTranslation();

  const direction = useQuery({ queryKey: ["direction"], queryFn: () => api.dashboardDirection() });
  const petrolier = useQuery({ queryKey: ["petrolier"], queryFn: () => api.reportingPetrolier() });
  const alertes = useQuery({ queryKey: ["alertes-agregees"], queryFn: () => api.alertesAgregees() });
  const tendances = useQuery({ queryKey: ["tendances"], queryFn: () => api.tendances(), retry: 0 });
  // Exports financiers proposés seulement si le pilotage financier est lisible (cercle des montants).
  const pilotage = useQuery({ queryKey: ["cd", "pilotage"], queryFn: () => api.get<Pilotage>("/api/analytics/pilotage/"), retry: 0 });

  const header = (
    <PageHeader title={t("direction.title")} subtitle={t("direction.subtitle")} actions={<DirectionExports financier={pilotage.isSuccess} />} />
  );

  if (direction.isPending || petrolier.isPending || alertes.isPending) {
    return (
      <>
        {header}
        <DirectionSkeleton />
      </>
    );
  }
  if (direction.isError || petrolier.isError || alertes.isError) {
    return (
      <>
        {header}
        <ErrorState
          message={t("common.error")}
          onRetry={() => {
            void direction.refetch();
            void petrolier.refetch();
            void alertes.refetch();
          }}
          retryLabel={t("common.retry")}
        />
      </>
    );
  }

  const d = direction.data as DashboardDirectionPlus;
  const p = petrolier.data as ReportingPetrolier;
  const a = alertes.data as AlertesAgregees;
  const tr = tendances.data as Tendances | undefined;

  // Héros 1 — chiffre d'affaires signé (montant exact, masqué hors cercle des montants).
  const ca = splitMoney(d.commercial.ca_gagne);
  // Héros 2 — disponibilité du matériel.
  const dispo = p.asmr.taux_disponibilite * 100;
  const dispoTone = toneFor(dispo, OBJECTIF_DISPO.ok, OBJECTIF_DISPO.warn);
  const dispoEcart = Math.round(dispo - OBJECTIF_DISPO.ok);
  // Héros 3 — sécurité.
  const jsa = p.hse.jours_sans_accident;
  const securiteTone = jsa === null ? "ok" : jsa < 30 ? "err" : jsa < 90 ? "warn" : "ok";
  // Pastille Sécurité explicite (A-09) : « Objectif non atteint (3 accidents) » plutôt qu'un
  // « Sous l'objectif » ambigu à côté de « 83 jours sans accident ».
  const accidents = p.hse.accidents;
  const securiteStatut = accidents
    ? t("premiumPilotage.direction.securite.nonAtteint", { count: accidents })
    : t("premiumPilotage.direction.securite.atteint");
  const securiteBadge = accidents ? (securiteTone === "err" ? "err" : "warn") : "ok";
  // Héros 4 — clôtures mensuelles dans les délais.
  const j4 = d.controle_gestion.conformite_j4;
  const clotureTaux = j4.taux * 100;
  const clotureTone = toneFor(clotureTaux, OBJECTIF_CLOTURE.ok, OBJECTIF_CLOTURE.warn);

  const statut = (tone: string) => t(`direction2.statut.${tone}`);
  const ecart = (n: number) =>
    n >= 0 ? t("direction2.ecart.dessus", { n: formatNumber(n) }) : t("direction2.ecart.dessous", { n: formatNumber(Math.abs(n)) });

  // « À traiter maintenant » : uniquement les points non nuls ; le tri par gravité est fait par la liste.
  const urgents: AttentionItem[] = (
    [
      { key: "expirees", count: a.compteurs.expiree ?? 0, tone: "err", to: "#echeances", Icon: CalendarX2 },
      { key: "j15", count: (a.compteurs.j0 ?? 0) + (a.compteurs.j15 ?? 0), tone: "err", to: "#echeances", Icon: CalendarClock },
      { key: "ncCritiques", count: p.qualite.nc_critiques, tone: "err", to: "/qualite", Icon: AlertTriangle },
      { key: "incidents", count: d.hse.incidents_ouverts, tone: "err", to: "/hse", Icon: ShieldAlert },
      { key: "atex", count: p.hse.equipements_atex_quarantaine, tone: "err", to: "/hse", Icon: Flame },
      { key: "panne", count: p.asmr.en_panne, tone: "err", to: "/maintenance", Icon: Wrench },
      { key: "j30", count: a.compteurs.j30 ?? 0, tone: "warn", to: "#echeances", Icon: CalendarClock },
      { key: "soudeurs", count: p.qualite.soudeurs_expires, tone: "warn", to: "/qualite", Icon: Award },
      { key: "epi", count: p.hse.epi_a_renouveler, tone: "warn", to: "/hse", Icon: UserCheck },
    ] as Omit<AttentionItem, "label">[]
  )
    .filter((u) => u.count > 0)
    .map((u) => ({ ...u, label: t(`direction2.attention.items.${u.key}`, { count: u.count }) }));

  const delay = (i: number) => Math.min(i * 0.04, 0.3);

  return (
    <>
      {header}
      <SectionNav
        items={[
          { id: "dir-synthese", label: t("premiumVague2.sections.direction.synthese") },
          { id: "dir-tendances", label: t("premiumVague2.sections.direction.tendances") },
          { id: "dir-modules", label: t("premiumVague2.sections.direction.modules") },
          { id: "dir-reporting", label: t("premiumVague2.sections.direction.reporting") },
          { id: "echeances", label: t("premiumVague2.sections.direction.echeances") },
          { id: "dir-pilotage", label: t("premiumVague2.sections.direction.pilotage") },
        ]}
      />

      {/* 1. Chiffres héros : cible, écart, état */}
      <section id="dir-synthese" className="dir-heroes" aria-label={t("direction2.heros")}>
        <HeroStat
          label={t("direction2.ca.label")}
          value={ca.value}
          unit={ca.unit}
          compact
          hint={
            <>
              {t("direction2.ca.pipe")} <strong className="num">{montant(d.commercial.pipe_pondere)}</strong>
            </>
          }
          foot={t("direction2.ca.affaires", { count: d.commercial.affaires_actives })}
          delay={0}
        />
        <HeroStat
          label={t("direction.heroDispo")}
          value={formatPercent(dispo, { decimals: dispo % 1 ? 1 : 0 })}
          tone={dispoTone}
          status={statut(dispoTone)}
          gauge={{ value: dispo, target: OBJECTIF_DISPO.ok, ok: OBJECTIF_DISPO.ok, warn: OBJECTIF_DISPO.warn, label: t("direction.heroDispo") }}
          foot={
            <>
              <span>{t("premiumPilotage.direction.objectif", { valeur: formatPercent(OBJECTIF_DISPO.ok) })}</span>
              <span className={`dir-delta tone-${dispoTone}`}>{ecart(dispoEcart)}</span>
            </>
          }
          hint={t("direction2.dispo.hint", { ok: p.asmr.operationnels, total: p.asmr.equipements })}
          delay={delay(1)}
        />
        <HeroStat
          label={t("direction.heroSecurite")}
          value={jsa === null ? formatNumber(p.hse.accidents) : formatNumber(jsa)}
          unit={jsa === null ? t("direction2.securite.accidents", { count: p.hse.accidents }) : t("direction2.securite.jours", { count: jsa })}
          tone={securiteBadge}
          status={securiteStatut}
          foot={
            <>
              <span>{t("direction2.securite.objectif")}</span>
              <span className={`dir-delta tone-${securiteBadge}`}>
                {t("premiumPilotage.direction.securite.declares", { count: accidents })}
              </span>
            </>
          }
          hint={
            jsa === null
              ? t("direction2.securite.aucunAccident", { count: d.hse.incidents_ouverts })
              : t("direction2.securite.incidents", { count: d.hse.incidents_ouverts })
          }
          delay={delay(2)}
        />
        <HeroStat
          label={t("direction2.cloture.label")}
          value={formatPercent(clotureTaux)}
          tone={clotureTone}
          status={statut(clotureTone)}
          gauge={{ value: clotureTaux, target: OBJECTIF_CLOTURE.ok, ok: OBJECTIF_CLOTURE.ok, warn: OBJECTIF_CLOTURE.warn, label: t("direction2.cloture.label") }}
          foot={
            <>
              <span>{t("premiumPilotage.direction.objectif", { valeur: formatPercent(OBJECTIF_CLOTURE.ok) })}</span>
              <span className={`dir-delta tone-${clotureTone}`}>{ecart(Math.round(clotureTaux - OBJECTIF_CLOTURE.ok))}</span>
            </>
          }
          hint={t("direction2.cloture.hint", { n: j4.conformes, total: j4.periodes })}
          delay={delay(3)}
        />
      </section>

      {/* 2. Tendances + « À traiter maintenant » (colonne latérale) */}
      <div id="dir-tendances" className="dir-split">
        <TrendPanel data={tr} loading={tendances.isPending} />
        <AttentionList items={urgents} />
      </div>

      {/* 3. Indicateurs par module : 2 rangées de 4 */}
      <section id="dir-modules" className="dir-section" aria-labelledby="dir-modules-title">
        <h3 id="dir-modules-title" className="section-title">
          {t("direction.directionKPIs")}
        </h3>
        <div className="kpi-grid dir-modules">
          <KpiLink to="/pipeline">
            <Kpi label={t("direction2.modules.commercial")} value={d.commercial.opportunites_ouvertes} hint={t("direction2.modules.commercialHint", { taux: d.commercial.taux_conversion === null ? "—" : formatPercent(d.commercial.taux_conversion * 100) })} icon={TrendingUp} tone="brand" delay={delay(0)} />
          </KpiLink>
          <KpiLink to="/purchases">
            <Kpi label={t("direction2.modules.achats")} value={d.achats.bc_en_cours} hint={<>{t("direction2.modules.achatsHint")} <span className="num">{montant(d.achats.montant_bc)}</span></>} icon={ShoppingCart} tone="brand" delay={delay(1)} />
          </KpiLink>
          <KpiLink to="/operations">
            <Kpi label={t("direction2.modules.operations")} value={d.operations.of_en_cours} hint={t("direction2.modules.operationsHint", { count: d.commercial.affaires_actives })} icon={Factory} tone="brand" delay={delay(2)} />
          </KpiLink>
          <KpiLink to="/maintenance">
            <Kpi label={t("direction2.modules.maintenance")} value={d.maintenance.ot_ouverts} hint={t("direction2.modules.maintenanceHint", { count: d.maintenance.en_arret })} icon={Wrench} tone={d.maintenance.en_arret ? "warn" : "brand"} delay={delay(3)} />
          </KpiLink>
          <KpiLink to="/stocks">
            <Kpi label={t("direction2.modules.stocks")} value={d.stocks.valorisation === null ? "••••••" : d.stocks.valorisation} kind="money" hint={t("direction2.modules.stocksHint", { count: d.stocks.lots_non_dispo })} icon={Boxes} tone="brand" delay={delay(4)} />
          </KpiLink>
          <KpiLink to="/hse">
            <Kpi label={t("direction2.modules.hse")} value={d.hse.incidents_ouverts} hint={t("direction2.modules.hseHint", { count: d.hse.actions_ouvertes })} icon={ShieldAlert} tone={d.hse.incidents_ouverts ? "warn" : "ok"} delay={delay(5)} />
          </KpiLink>
          <KpiLink to="/rh-paie">
            <Kpi label={t("direction2.modules.rh")} value={d.rh_paie.effectif} hint={t("direction2.modules.rhHint", { count: d.rh_paie.conges_en_attente })} icon={Users} tone="brand" delay={delay(6)} />
          </KpiLink>
          <KpiLink to="/juridique">
            <Kpi label={t("direction2.modules.juridique")} value={d.juridique.contentieux_ouverts} hint={t("direction2.modules.juridiqueHint", { count: d.juridique.cautions_en_cours })} icon={Scale} tone={d.juridique.contentieux_ouverts ? "warn" : "brand"} delay={delay(7)} />
          </KpiLink>
        </div>
      </section>

      {/* 4. Reporting client pétrolier */}
      <div id="dir-reporting" className="page-section">
        <ReportingSection p={p} />
      </div>

      {/* 5. Échéances */}
      <EcheancesSection a={a} />

      {/* 6. Pilotage financier et cubes (onglets) */}
      <div id="dir-pilotage" className="page-section">
        <PilotageSection commercial={d.commercial.indicateurs} />
      </div>
    </>
  );
}
