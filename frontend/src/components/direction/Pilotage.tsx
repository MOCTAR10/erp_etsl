import { useQuery } from "@tanstack/react-query";
import { Info, Lock, ShieldCheck, SlidersHorizontal, Trash2 } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Area, AreaChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { api } from "../../api/client";
import { formatDate, formatMoney, formatNumber, formatPercent } from "../../lib/format";
import { useThemeMode } from "../../lib/useThemeMode";
import { paletteFor } from "../../theme/tokens";
import type { CubeLecture } from "../../types";
import { Badge, DataGrid, Menu, Popover, ProgressBar } from "../ui";
import type { GridColumn } from "../ui";
import { CubesSection } from "../workflow/CubesSection";
import { ConfirmDialog, useServerAction } from "../workflow/actions";
import { Stat } from "./Stat";
import { Tabs } from "./Tabs";
import type { TabDef } from "./Tabs";
import type { EtatBi, IndicateursCommerciaux, Pilotage, Scelle, SeuilBudget } from "./types";

const NIVEAU_TONE: Record<string, "warn" | "err"> = { alerte: "warn", atteint: "warn", depasse: "err" };
const num = (v: string | number | null | undefined) => (v === null || v === undefined || v === "" ? null : Number(v));

/* ---------------------------------------------------------------- Trésorerie */

function Tresorerie({ p }: { p: Pilotage }) {
  const { t } = useTranslation();
  const c = paletteFor(useThemeMode());
  const cf = p.cashflow;
  const data = cf.semaines.map((s) => ({
    ...s,
    id: s.semaine,
    label: `S${s.semaine}`,
    solde: num(s.solde_fin) ?? 0,
    // Semaine sans aucun mouvement : « — » en gris plutôt que trois « 0 FCFA » (A-08).
    vide: !num(s.encaissements) && !num(s.decaissements),
  }));
  const tension = data.filter((s) => s.solde < 0).length;
  const flux = (s: (typeof data)[number], v: string | number) => (s.vide ? <span className="muted">—</span> : formatMoney(v));
  // Largeur de l'axe Y : graduations exactes groupées (« 900 000 000 »), unité en titre d'axe.
  const maxAbs = Math.max(1, ...data.map((s) => Math.abs(s.solde)));
  const axisWidth = Math.min(110, 14 + formatNumber(maxAbs).length * 6.4);
  const columns: GridColumn<(typeof data)[number]>[] = [
    {
      key: "semaine",
      header: t("ecarts_cd.cashflow.semaine"),
      render: (s) => (
        <>
          <strong>S{s.semaine}</strong> <span className="muted">· {formatDate(s.debut)}</span>
        </>
      ),
    },
    { key: "enc", header: t("ecarts_cd.cashflow.encaissements"), num: true, render: (s) => flux(s, s.encaissements) },
    { key: "dec", header: t("ecarts_cd.cashflow.decaissements"), num: true, render: (s) => flux(s, s.decaissements) },
    { key: "flux", header: t("ecarts_cd.cashflow.flux"), num: true, render: (s) => flux(s, s.flux_net) },
    {
      key: "solde",
      header: t("ecarts_cd.cashflow.solde"),
      num: true,
      render: (s) => (
        <span className="dir-solde">
          {s.solde < 0 ? <Badge tone="err">{t("ecarts_cd.cashflow.tension")}</Badge> : null}
          <span className={s.vide ? "muted" : undefined}>{formatMoney(s.solde_fin)}</span>
        </span>
      ),
    },
  ];
  return (
    <div className="dir-panel" data-testid="cashflow-13s">
      <dl className="dir-stats dir-stats-row">
        <Stat label={t("direction2.tresorerie.ouverture")} value={formatMoney(cf.ouverture)} />
        <Stat label={t("direction2.tresorerie.finale")} value={formatMoney(cf.solde_final)} tone={(num(cf.solde_final) ?? 0) < 0 ? "err" : undefined} />
        <Stat label={t("direction2.tresorerie.tension")} value={formatNumber(tension)} tone={tension ? "err" : "ok"} />
      </dl>
      <p className="dir-note">{t("direction2.tresorerie.note")}</p>
      {data.length ? (
        <div className="dir-chart dir-chart-axis" role="img" aria-label={t("direction2.tresorerie.graphe")}>
          <span className="dir-chart-unit" aria-hidden>
            {t("premiumPilotage.direction.axeFcfa")}
          </span>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 28, right: 12, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="dir-cf" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={c.brand} stopOpacity={0.16} />
                  <stop offset="100%" stopColor={c.brand} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke={c.border} strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="label" stroke={c.textMuted} fontSize={11} tickLine={false} axisLine={false} interval={0} />
              <YAxis
                stroke={c.textMuted}
                fontSize={11}
                tickLine={false}
                axisLine={false}
                width={axisWidth}
                tickCount={5}
                domain={["auto", "auto"]}
                tickFormatter={(v: number) => formatNumber(v)}
              />
              {tension ? <ReferenceLine y={0} stroke={c.err} strokeDasharray="4 4" /> : null}
              <Tooltip
                contentStyle={{ background: c.surface, border: `1px solid ${c.border}`, borderRadius: 8, color: c.text, fontSize: 12 }}
                formatter={(v) => [formatMoney(Number(v)), t("ecarts_cd.cashflow.solde")]}
              />
              <Area type="monotone" dataKey="solde" stroke={c.brand} strokeWidth={2} fill="url(#dir-cf)" isAnimationActive={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      ) : null}
      <DataGrid columns={columns} rows={data} caption={t("ecarts_cd.cashflow.title")} density="compact" maxHeight="none" />
    </div>
  );
}

/* ---------------------------------------------------------------- Pipe → budget */

function PipeBudget({ p }: { p: Pilotage }) {
  const { t } = useTranslation();
  const pb = p.pipe_budget;
  const budget = num(pb.budget_produits) ?? 0;
  const part = (v: string) => (budget > 0 ? Math.max(0, Math.min(100, ((num(v) ?? 0) / budget) * 100)) : 0);
  const segments = [
    { key: "realise", label: t("ecarts_cd.pipe.realise"), value: pb.realise, cls: "s1" },
    { key: "signe", label: t("direction2.pipe.signe"), value: pb.pipe_pondere.signe, cls: "s2" },
    { key: "en_cours", label: t("direction2.pipe.enCours"), value: pb.pipe_pondere.en_cours, cls: "s3" },
    { key: "prospect", label: t("direction2.pipe.prospect"), value: pb.pipe_pondere.prospect, cls: "s4" },
  ];
  const couverture = num(pb.couverture_pct);
  return (
    <div className="dir-panel" data-testid="pipe-budget">
      <div className="dir-cover">
        <div>
          <span className="dir-cover-label">{t("ecarts_cd.pipe.couverture")}</span>
          <span className="dir-cover-value num">{couverture === null ? "—" : formatPercent(couverture)}</span>
        </div>
        <span className="muted">{t("direction2.pipe.annee", { annee: pb.annee })}</span>
      </div>
      <div className="dir-stack" role="img" aria-label={segments.map((s) => `${s.label} ${formatMoney(s.value)}`).join(", ")}>
        {segments.map((s) => (
          <span key={s.key} className={`dir-stack-seg ${s.cls}`} style={{ width: `${part(s.value)}%` }} />
        ))}
      </div>
      <ul className="dir-legend">
        {segments.map((s) => (
          <li key={s.key}>
            <span className={`dir-legend-dot ${s.cls}`} aria-hidden />
            {s.label} <strong className="num">{formatMoney(s.value)}</strong>
          </li>
        ))}
      </ul>
      <dl className="dir-stats">
        <Stat label={t("ecarts_cd.pipe.budget")} value={formatMoney(pb.budget_produits)} />
        <Stat label={t("ecarts_cd.pipe.realise")} value={formatMoney(pb.realise)} />
        <Stat label={t("direction2.pipe.pipeTotal")} value={formatMoney(pb.pipe_pondere.total)} />
        <Stat label={t("ecarts_cd.pipe.atterrissage")} value={formatMoney(pb.atterrissage)} />
        <Stat label={t("ecarts_cd.pipe.reste")} value={formatMoney(pb.reste_a_couvrir)} tone={(num(pb.reste_a_couvrir) ?? 0) > 0 ? "warn" : "ok"} />
      </dl>
    </div>
  );
}

/* ---------------------------------------------------------------- Seuils budgétaires */

function Seuils({ p }: { p: Pilotage }) {
  const { t } = useTranslation();
  const action = useServerAction([["cd", "pilotage"]]);
  const rows = p.seuils_budget.map((s) => ({ ...s, id: s.budget }));
  const columns: GridColumn<SeuilBudget & { id: string }>[] = [
    {
      key: "budget",
      header: t("direction2.seuils.budget"),
      sortValue: (s) => s.libelle,
      render: (s) => (
        <>
          <strong>{s.libelle}</strong> <span className="muted">· {s.budget}</span>
        </>
      ),
    },
    { key: "realise", header: t("direction2.seuils.realise"), num: true, render: (s) => formatMoney(s.realise), sortValue: (s) => num(s.realise) },
    { key: "montant", header: t("direction2.seuils.montant"), num: true, render: (s) => formatMoney(s.montant), sortValue: (s) => num(s.montant) },
    {
      key: "taux",
      header: t("direction2.seuils.taux"),
      width: 180,
      sortValue: (s) => num(s.taux_pct),
      render: (s) => {
        const v = num(s.taux_pct) ?? 0;
        return (
          <span className="dir-taux">
            <ProgressBar value={v} label={`${s.libelle} ${formatPercent(v)}`} tone={s.niveau ? NIVEAU_TONE[s.niveau] : "brand"} />
            <span className="num">{formatPercent(v)}</span>
          </span>
        );
      },
    },
    {
      key: "niveau",
      header: t("direction2.seuils.niveau"),
      render: (s) =>
        s.niveau ? <Badge tone={NIVEAU_TONE[s.niveau]}>{t(`ecarts_cd.seuils.${s.niveau}`)}</Badge> : <Badge tone="ok">{t("direction2.seuils.normal")}</Badge>,
    },
  ];
  return (
    <div className="dir-panel" data-testid="seuils-budget">
      <div className="dir-panel-bar">
        <p className="dir-note">{t("direction2.seuils.note")}</p>
        <button
          type="button"
          className="btn ghost sm"
          disabled={action.isPending}
          onClick={() => action.mutate({ path: "/api/analytics/pilotage/controler-seuils/", success: t("direction2.seuils.controle") })}
        >
          <ShieldCheck size={15} aria-hidden />
          {t("ecarts_cd.seuils.controler")}
        </button>
      </div>
      <DataGrid columns={columns} rows={rows} caption={t("ecarts_cd.seuils.title")} emptyLabel={t("ecarts_cd.seuils.aucun")} maxHeight="none" />
    </div>
  );
}

/* ---------------------------------------------------------------- Commercial */

function Commercial({ ic }: { ic: IndicateursCommerciaux }) {
  const { t } = useTranslation();
  return (
    <div className="dir-panel" data-testid="indicateurs-commerciaux">
      <dl className="dir-stats">
        <Stat label={t("ecarts_cd.commercial.prixMoyen")} value={formatMoney(ic.prix_moyen)} hint={t("ecarts_cd.commercial.gagnees", { count: ic.offres_gagnees })} />
        <Stat
          label={t("ecarts_cd.commercial.transformation")}
          value={ic.taux_transformation_pct === null ? "—" : formatPercent(ic.taux_transformation_pct, { decimals: 1 })}
        />
        <Stat
          label={t("ecarts_cd.commercial.score")}
          value={ic.score_moyen === null ? "—" : formatNumber(ic.score_moyen, { decimals: 1 })}
          hint={t("direction2.commercial.sur100")}
        />
        <Stat label={t("direction2.commercial.plus70")} value={formatNumber(ic.clients_70_plus)} />
        <Stat label={t("direction2.commercial.sousSeuil")} value={formatNumber(ic.clients_sous_seuil)} tone={ic.clients_sous_seuil ? "warn" : undefined} />
      </dl>
      <p className="dir-note">{t("direction2.commercial.note")}</p>
    </div>
  );
}

/* ---------------------------------------------------------------- Données et archives */

const FRAICHEUR_TONE = { a_jour: "ok", en_retard: "err", jamais: "warn" } as const;

function Donnees({ p, etat }: { p: Pilotage | undefined; etat: EtatBi | undefined }) {
  const { t } = useTranslation();
  const [purge, setPurge] = useState(false);
  const action = useServerAction([["cd", "scelles"]]);
  const scelles = useQuery({
    queryKey: ["cd", "scelles"],
    queryFn: () => api.listAll<Scelle>("/api/analytics/marts/scelles/"),
    retry: 0,
    enabled: Boolean(p),
  });
  const f = etat?.fraicheur;
  const columns: GridColumn<Scelle>[] = [
    { key: "mart", header: t("direction2.scelles.jeu"), render: (s) => s.mart, sortValue: (s) => s.mart },
    { key: "type", header: t("direction2.scelles.type"), render: (s) => t(`ecarts_cd.scelles.${s.type_donnees}`) },
    { key: "lignes", header: t("direction2.scelles.lignes"), num: true, render: (s) => formatNumber(s.nb_lignes) },
    {
      key: "sha",
      header: t("direction2.scelles.empreinte"),
      render: (s) => (
        <code className="dir-hash" title={s.sha256}>
          {s.sha256.slice(0, 12)}…
        </code>
      ),
    },
    { key: "conserve", header: t("direction2.scelles.conserve"), render: (s) => formatDate(s.conserve_jusqu_au), sortValue: (s) => s.conserve_jusqu_au },
    {
      key: "integre",
      header: t("direction2.scelles.integrite"),
      render: (s) => <Badge tone={s.integre ? "ok" : "err"}>{s.integre ? t("ecarts_cd.scelles.integre") : t("ecarts_cd.scelles.altere")}</Badge>,
    },
  ];
  return (
    <div className="dir-panel">
      {f ? (
        <p className="dir-note" data-testid="fraicheur-bi">
          <Badge tone={FRAICHEUR_TONE[f.statut]}>{t(`ecarts_a4.fraicheur.${f.statut}`)}</Badge>{" "}
          {f.rafraichi_le ? t("direction2.donnees.derniere", { date: formatDate(f.rafraichi_le), age: f.age_minutes }) : t("direction2.donnees.aucune")}
          {" · "}
          {t("direction2.donnees.seuil", { n: f.seuil_minutes })}
          {etat?.fraicheur_provisoire ? (
            <>
              {" "}
              <Badge tone="warn">{t("direction2.provisoire")}</Badge>
            </>
          ) : null}
        </p>
      ) : null}
      {p ? (
        <>
          <p className="dir-note" data-testid="publication-cloture">
            <Lock size={14} aria-hidden className="dir-inline-icon" />
            {p.blocage_avant_cloture ? t("ecarts_cd.publication.bloque") : t("ecarts_cd.publication.libre")}{" "}
            {t("direction2.donnees.clotures", { liste: p.periodes_cloturees.join(", ") || "—" })}
            {p.voit_non_cloture && p.blocage_avant_cloture ? (
              <>
                {" "}
                <Badge tone="warn">{t("ecarts_cd.publication.producteur")}</Badge>
              </>
            ) : null}
          </p>
          <div className="dir-panel-bar">
            <h4 className="dir-panel-title">{t("direction2.scelles.titre")}</h4>
            <span className="dir-panel-actions">
              <button
                type="button"
                className="btn ghost sm"
                disabled={action.isPending}
                onClick={() => action.mutate({ path: "/api/analytics/marts/scelles/sceller/", success: t("direction2.scelles.ok") })}
              >
                <ShieldCheck size={15} aria-hidden />
                {t("ecarts_cd.scelles.sceller")}
              </button>
              <Menu
                size="sm"
                label={t("direction2.scelles.plus")}
                items={[{ label: t("ecarts_cd.scelles.purger"), icon: Trash2, danger: true, onSelect: () => setPurge(true) }]}
              />
            </span>
          </div>
          <p className="dir-note">
            {t("ecarts_cd.scelles.hint", { fin: p.retention.retention_financier_ans, op: p.retention.retention_operationnel_ans })}
          </p>
          <div data-testid="scelles-marts">
            <DataGrid
              columns={columns}
              rows={scelles.data ?? []}
              loading={scelles.isPending}
              caption={t("direction2.scelles.titre")}
              emptyLabel={t("ecarts_cd.scelles.aucun")}
              density="compact"
              maxHeight={420}
            />
          </div>
          <ConfirmDialog
            open={purge}
            onOpenChange={setPurge}
            title={t("ecarts_cd.scelles.purger")}
            description={t("ecarts_cd.scelles.confirmPurge")}
            confirmLabel={t("direction2.scelles.purgerOk")}
            danger
            onConfirm={() => action.mutate({ path: "/api/analytics/marts/scelles/purger/", success: t("direction2.scelles.purge") })}
          />
        </>
      ) : null}
    </div>
  );
}

/* ---------------------------------------------------------------- Section à onglets */

/**
 * Pilotage financier en onglets : trésorerie 13 semaines, pipe → budget, seuils, commercial, cubes 6 axes,
 * données et archives. Les onglets financiers n'apparaissent que pour le cercle des montants (refus du serveur sinon).
 */
export function PilotageSection({ commercial }: { commercial?: IndicateursCommerciaux }) {
  const { t } = useTranslation();
  const pilotage = useQuery({ queryKey: ["cd", "pilotage"], queryFn: () => api.get<Pilotage>("/api/analytics/pilotage/"), retry: 0 });
  const etat = useQuery({ queryKey: ["a4", "etat-bi"], queryFn: () => api.get<EtatBi>("/api/analytics/etat-bi/"), retry: 0 });
  // Même requête que la lecture initiale du cube (axe période) : l'onglet n'existe que si le cube est lisible.
  const cube = useQuery({ queryKey: ["cube", ["periode"]], queryFn: () => api.get<CubeLecture>("/api/analytics/cubes/?axes=periode"), retry: 0 });
  const p = pilotage.data;

  const tabs = [
    p && { id: "tresorerie", label: t("direction2.onglets.tresorerie"), content: <Tresorerie p={p} /> },
    p && { id: "pipe", label: t("direction2.onglets.pipe"), content: <PipeBudget p={p} /> },
    p && { id: "seuils", label: t("direction2.onglets.seuils"), content: <Seuils p={p} /> },
    commercial && { id: "commercial", label: t("direction2.onglets.commercial"), content: <Commercial ic={commercial} /> },
    cube.isSuccess && { id: "cubes", label: t("direction2.onglets.cubes"), content: <CubesSection /> },
    (p || etat.data) && { id: "donnees", label: t("direction2.onglets.donnees"), content: <Donnees p={p} etat={etat.data} /> },
  ].filter(Boolean) as TabDef[];

  if (tabs.length === 0) return null;
  return (
    <section className="dir-section" aria-labelledby="dir-pilotage-title" data-testid="pilotage-direction">
      <div className="dir-section-head">
        <h3 id="dir-pilotage-title" className="section-title">
          {t("direction2.pilotage.titre")}
        </h3>
        {p?.parametres_provisoires ? (
          // Hypothèses par défaut (délais, seuils) : une icône d'information discrète, rien d'alarmant en tête d'écran.
          <Popover
            label={t("premiumVague2.direction.hypothesesTitre")}
            align="end"
            trigger={
              <button type="button" className="icon-btn dir-hypotheses" aria-label={t("premiumVague2.direction.hypothesesTitre")} data-testid="alerte-provisoire-cd">
                <Info size={16} aria-hidden />
              </button>
            }
          >
            <div className="dir-hypotheses-pop">
              <strong>{t("premiumVague2.direction.hypothesesTitre")}</strong>
              <p>{t("premiumVague2.direction.hypothesesTexte")}</p>
              <Link className="btn ghost sm" to="/parametres">
                <SlidersHorizontal size={14} aria-hidden />
                {t("direction2.ouvrirParametres")}
              </Link>
            </div>
          </Popover>
        ) : null}
      </div>
      <div className="card dir-tabs-card">
        <Tabs tabs={tabs} label={t("direction2.pilotage.titre")} />
      </div>
    </section>
  );
}
