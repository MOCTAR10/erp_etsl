import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

import { api } from "../../api/client";
import { formatNumber, formatPercent } from "../../lib/format";
import { useThemeMode } from "../../lib/useThemeMode";
import { paletteFor } from "../../theme/tokens";
import type { ReportingPetrolier } from "../../types";
import { Badge, DataGrid } from "../ui";
import type { GridColumn } from "../ui";
import { Stat } from "./Stat";
import type { CapaLigne, EtatBi, ItpCnd } from "./types";

/** Parc matériel (ASMR) : anneau de répartition + légende chiffrée. */
function Parc({ p }: { p: ReportingPetrolier }) {
  const { t } = useTranslation();
  const c = paletteFor(useThemeMode());
  const parts = [
    { key: "ok", name: t("direction.operationnels"), value: p.asmr.operationnels, color: c.ok },
    { key: "maint", name: t("direction.enMaintenance"), value: p.asmr.en_maintenance, color: c.warn },
    { key: "panne", name: t("direction.enPanne"), value: p.asmr.en_panne, color: c.err },
    { key: "hs", name: t("direction.horsService"), value: p.asmr.hors_service, color: c.textMuted },
  ];
  const visibles = parts.filter((f) => f.value > 0);
  const taux = p.asmr.taux_disponibilite * 100;
  return (
    <section className="card dir-card" aria-labelledby="dir-parc-title">
      <header className="card-header">
        <div>
          <h4 id="dir-parc-title" className="card-title">
            {t("direction2.reporting.parc")}
          </h4>
          <p className="card-sub">{t("direction2.reporting.parcSub", { n: p.asmr.equipements })}</p>
        </div>
      </header>
      <div className="dir-donut">
        <div className="dir-donut-chart">
          {visibles.length ? (
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={visibles} dataKey="value" nameKey="name" innerRadius="70%" outerRadius="100%" paddingAngle={2} strokeWidth={0} isAnimationActive={false}>
                  {visibles.map((f) => (
                    <Cell key={f.key} fill={f.color} />
                  ))}
                </Pie>
                <Tooltip contentStyle={{ background: c.surface, border: `1px solid ${c.border}`, borderRadius: 8, color: c.text, fontSize: 12 }} />
              </PieChart>
            </ResponsiveContainer>
          ) : null}
          <span className="dir-donut-center">
            <strong className="num">{formatPercent(taux, { decimals: taux % 1 ? 1 : 0 })}</strong>
            <span>{t("direction2.reporting.disponible")}</span>
          </span>
        </div>
        <ul className="dir-legend dir-legend-col">
          {parts.map((f) => (
            <li key={f.key}>
              <span className="dir-legend-dot" style={{ background: f.color }} aria-hidden />
              {f.name}
              <strong className="num">{formatNumber(f.value)}</strong>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

/** Qualité et HSE pour le client pétrolier : liste de chiffres. */
function Qhse({ p }: { p: ReportingPetrolier }) {
  const { t } = useTranslation();
  return (
    <section className="card dir-card" aria-labelledby="dir-qhse-title">
      <header className="card-header">
        <div>
          <h4 id="dir-qhse-title" className="card-title">
            {t("direction2.reporting.qhse")}
          </h4>
          <p className="card-sub">{t("direction2.reporting.qhseSub")}</p>
        </div>
      </header>
      <dl className="dir-stats">
        <Stat label={t("direction.ncOuvertes")} value={formatNumber(p.qualite.nc_ouvertes)} hint={t("direction.u.critiques", { count: p.qualite.nc_critiques })} tone={p.qualite.nc_critiques ? "err" : undefined} />
        <Stat label={t("direction.soudeursQualifies")} value={formatNumber(p.qualite.soudeurs_qualifies)} hint={t("direction.u.expires", { count: p.qualite.soudeurs_expires })} tone={p.qualite.soudeurs_expires ? "warn" : undefined} />
        <Stat label={t("direction2.reporting.incidents")} value={formatNumber(p.hse.incidents_ouverts)} hint={t("direction.u.accidents", { count: p.hse.accidents })} tone={p.hse.incidents_ouverts ? "warn" : undefined} />
        <Stat label={t("direction.permisAtex")} value={formatNumber(p.hse.permis_atex)} hint={t("direction.u.quarantaine", { count: p.hse.equipements_atex_quarantaine })} />
        <Stat label={t("direction.epiRenouveler")} value={formatNumber(p.hse.epi_a_renouveler)} hint={t("direction.u.permisActifs", { count: p.hse.permis_actifs })} tone={p.hse.epi_a_renouveler ? "warn" : undefined} />
      </dl>
    </section>
  );
}

/** Inspection (ITP) et contrôles non destructifs (CND). */
function ItpCndCard({ q }: { q: Required<ItpCnd> }) {
  const { t } = useTranslation();
  const methodes = Object.entries(q.cnd.par_methode)
    .map(([m, n]) => `${m} ${formatNumber(n)}`)
    .join(" · ");
  return (
    <section className="card dir-card" aria-labelledby="dir-itp-title" data-testid="petrolier-itp-cnd">
      <header className="card-header">
        <div>
          <h4 id="dir-itp-title" className="card-title">
            {t("direction2.reporting.itp")}
          </h4>
          <p className="card-sub">{t("ecarts_cd.itpCnd.approuves", { n: q.itp.plans_approuves })} · {t("direction2.reporting.plans", { count: q.itp.plans })}</p>
        </div>
      </header>
      <dl className="dir-stats">
        <Stat label={t("ecarts_cd.itpCnd.points")} value={`${formatNumber(q.itp.points_leves)} / ${formatNumber(q.itp.points)}`} hint={formatPercent(q.itp.taux_levee * 100, { decimals: 1 })} />
        <Stat label={t("ecarts_cd.itpCnd.arretsAttente")} value={formatNumber(q.itp.points_arret_en_attente)} tone={q.itp.points_arret_en_attente ? "warn" : undefined} />
        <Stat label={t("ecarts_cd.itpCnd.pointsNc")} value={formatNumber(q.itp.points_non_conformes)} tone={q.itp.points_non_conformes ? "err" : undefined} />
        <Stat label={t("ecarts_cd.itpCnd.cnd")} value={formatNumber(q.cnd.controles)} hint={methodes || t("ecarts_cd.itpCnd.enCours", { n: q.cnd.en_cours })} />
        <Stat label={t("ecarts_cd.itpCnd.rejet")} value={formatPercent(q.cnd.taux_rejet * 100, { decimals: 1 })} hint={`${formatNumber(q.cnd.conformes)} / ${formatNumber(q.cnd.sous_reserve)} / ${formatNumber(q.cnd.non_conformes)}`} />
      </dl>
    </section>
  );
}

/** Actions correctives et préventives (CAPA) qualité / HSE. */
function Capa({ lignes }: { lignes: CapaLigne[] }) {
  const { t } = useTranslation();
  const rows = lignes.map((c) => ({ ...c, id: c.origine }));
  const columns: GridColumn<(typeof rows)[number]>[] = [
    { key: "origine", header: t("ecarts_a4.capa.origine"), render: (c) => <strong>{t(`direction2.capa.${c.origine}`)}</strong> },
    { key: "ouvertes", header: t("ecarts_a4.capa.ouvertes"), num: true, render: (c) => `${formatNumber(c.ouvertes)} / ${formatNumber(c.total)}` },
    { key: "echues", header: t("ecarts_a4.capa.echues"), num: true, render: (c) => (c.echues > 0 ? <Badge tone="err">{formatNumber(c.echues)}</Badge> : "0") },
    { key: "cloturees", header: t("ecarts_a4.capa.cloturees"), num: true, render: (c) => formatNumber(c.cloturees) },
    {
      key: "delai",
      header: t("ecarts_a4.capa.delai"),
      num: true,
      render: (c) => (c.delai_moyen_cloture_jours === null ? "—" : t("direction2.capa.jours", { n: formatNumber(c.delai_moyen_cloture_jours, { decimals: 0 }) })),
    },
    {
      key: "efficacite",
      header: t("ecarts_a4.capa.efficacite"),
      num: true,
      render: (c) => (c.taux_efficacite_pct === null ? "—" : `${formatPercent(c.taux_efficacite_pct)} (${c.efficaces} / ${c.efficacite_verifiee})`),
    },
  ];
  return (
    <section className="card dir-card dir-card-wide" aria-labelledby="dir-capa-title" data-testid="capa-couche-d">
      <header className="card-header">
        <div>
          <h4 id="dir-capa-title" className="card-title">
            {t("direction2.capa.titre")}
          </h4>
          <p className="card-sub">{t("direction2.capa.sub")}</p>
        </div>
      </header>
      <DataGrid columns={columns} rows={rows} caption={t("direction2.capa.titre")} density="compact" maxHeight="none" />
    </section>
  );
}

/** Reporting client pétrolier : parc matériel, qualité / HSE, inspection et CND, CAPA. */
export function ReportingSection({ p }: { p: ReportingPetrolier }) {
  const { t } = useTranslation();
  const qualite = useQuery({ queryKey: ["cd", "itp-cnd"], queryFn: () => api.get<ItpCnd>("/api/analytics/petrolier/"), retry: 0 });
  const etat = useQuery({ queryKey: ["a4", "etat-bi"], queryFn: () => api.get<EtatBi>("/api/analytics/etat-bi/"), retry: 0 });
  const q = qualite.data;
  const capa = etat.data?.capa ?? [];
  return (
    <section className="dir-section" aria-labelledby="dir-reporting-title">
      <h3 id="dir-reporting-title" className="section-title">
        {t("direction.reportPetrolier")}
      </h3>
      <div className="dir-cards">
        <Parc p={p} />
        <Qhse p={p} />
        {q?.itp && q.cnd ? <ItpCndCard q={q as Required<ItpCnd>} /> : null}
        {capa.length ? <Capa lignes={capa} /> : null}
      </div>
    </section>
  );
}
