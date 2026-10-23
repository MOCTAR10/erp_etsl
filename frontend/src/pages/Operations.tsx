import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { CoutMainOeuvreSection } from "../components/rhpaie/EcartsM9bSection";
import { EcartsM3Section } from "../components/operations/EcartsM3Section";
import { ConsommationOfSection } from "../components/operations/ConsommationOfSection";
import { NOWRAP, statutLabel } from "../components/operations/outils";
import { FluxM4Section } from "../components/suivi/SuiviSections";
import { useState } from "react";
import { Clock3, Construction, Factory, HardHat } from "lucide-react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { SiteFilter, siteQuery } from "../components/sites/SiteFilter";
import { formatDate, formatMoney, formatNumber, formatPercent } from "../lib/format";
import { pagedQuery, usePagedList } from "../lib/usePagedList";
import { Badge, Board, BoardCard, BoardColumn, BoardSkeleton, DataTable, ErrorState, Kpi, PageHeader, PagedDataTable, QuickForm, SearchField, SectionCard } from "../components/ui";
import { CardActions } from "../components/ui/Board";
import { actionsColumn } from "../components/ui/DataTable";
import type { ActionDef } from "../components/ui";
import type {
  ChargeStats,
  EquipeAffectation,
  OfStatus,
  OrdreFabrication,
  PresenceChantier,
  Paginated,
  SituationTravaux,
} from "../types";

type Groups = Record<OfStatus, OrdreFabrication[]>;

const STATUS_BADGE: Record<OfStatus, "ok" | "warn" | "err" | "brand"> = {
  prevu: "brand",
  lance: "brand",
  en_cours: "warn",
  termine: "ok",
  cloture: "ok",
  annule: "err",
};
const VALID_STATUSES = new Set<OfStatus>(["prevu", "lance", "en_cours", "termine", "cloture", "annule"]);
const METIERS = ["soudeur", "chaudronnier", "tuyauteur", "monteur", "peintre", "genie_civil", "electricien", "instrumentiste"];
const BOARD_ORDER: OfStatus[] = ["en_cours", "lance", "prevu", "termine", "cloture"];

function ofActions(of: OrdreFabrication, t: (k: string) => string): ActionDef[] {
  const base = `/api/operations/ordres/${of.id}`;
  switch (of.status) {
    case "prevu":
      return [{ label: t("operations.actions.lancer"), path: `${base}/lancer/` }];
    case "lance":
      return [{ label: t("operations.actions.demarrer"), path: `${base}/demarrer/` }];
    case "en_cours":
      return [{ label: t("operations.actions.terminer"), path: `${base}/terminer/` }];
    case "termine":
      return [{ label: t("operations.actions.liberer"), path: `${base}/liberer/`, confirm: t("operations.actions.confirmLiberer") }];
    default:
      return [];
  }
}

function OfCard({ of, index }: { of: OrdreFabrication; index: number }) {
  const { t } = useTranslation();
  const pointees = Number(of.pointage_hours);
  const prevues = Number(of.calculated_hours);
  return (
    <BoardCard delay={Math.min(index * 0.03, 0.3)}>
      <div className="card-top">
        <span className="card-code">{of.code}</span>
        <span className="card-tags">
          <Badge tone="neutral">{t(`operations.${of.scope}`)}</Badge>
        </span>
      </div>
      <div className="title">{of.label}</div>
      <div className="meta">
        {[of.affaire_code, of.gamme_code ? `${t("operations.gamme")} ${of.gamme_code}` : null].filter(Boolean).join(" · ") || "—"}
      </div>
      <div className="card-foot">
        <span>{of.planned_end ? t("listes.operations.echeance", { date: formatDate(of.planned_end) }) : null}</span>
        <span className={`amount${prevues > 0 && pointees > prevues ? " is-over" : ""}`}>
          {t("listes.operations.heures", { pointees: formatNumber(pointees), prevues: formatNumber(prevues) })}
        </span>
      </div>
      <CardActions actions={ofActions(of, t)} />
    </BoardCard>
  );
}

/** Alertes affichées avant « Afficher les N alertes » : la liste complète couvre souvent plus d'un an de semaines. */
const ALERTES_VISIBLES = 6;

function Charge({ stats }: { stats: ChargeStats }) {
  const { t } = useTranslation();
  const [toutes, setToutes] = useState(false);
  const alertes = stats.alertes ?? [];
  if (alertes.length === 0) return null;
  // Semaines à venir d'abord (la semaine en cours comprise), puis les semaines passées ; chronologique dans chaque groupe.
  const lundi = new Date();
  lundi.setDate(lundi.getDate() - 7);
  const seuil = lundi.toISOString().slice(0, 10);
  const triees = [...alertes].sort((a, b) => {
    const pa = a.week >= seuil ? 0 : 1;
    const pb = b.week >= seuil ? 0 : 1;
    return pa - pb || a.week.localeCompare(b.week) || a.scope.localeCompare(b.scope);
  });
  const visibles = toutes ? triees : triees.slice(0, ALERTES_VISIBLES);
  return (
    <SectionCard
      title={`${t("operations.surcharge")} · ${alertes.length}`}
      actions={
        alertes.length > ALERTES_VISIBLES ? (
          <button type="button" className="btn ghost sm" aria-expanded={toutes} onClick={() => setToutes((v) => !v)}>
            {toutes ? t("revueR2.operations.alertesReduire") : t("revueR2.operations.alertesVoir", { count: alertes.length })}
          </button>
        ) : undefined
      }
    >
      <ul className="overload-list" data-testid="alertes-surcharge">
        {visibles.map((a) => {
          // Barre : dépassement de capacité (pleine à +100 %).
          const ratio = Math.max(0.04, Math.min(1, a.overload_pct / 100));
          return (
            <li key={`${a.scope}-${a.week}`}>
              <span>
                <strong>{t(`operations.${a.scope}`)}</strong>
                <span className="cell-sub">{t("listes.operations.surchargeHint", { date: formatDate(a.week) })}</span>
              </span>
              <span className={`overload-bar${a.overload_pct >= 100 ? " err" : ""}`} aria-hidden>
                <span style={{ width: `${Math.round(ratio * 100)}%` }} />
              </span>
              <span className="overload-hours">
                {formatNumber(a.planned_hours)} h / {formatNumber(a.capacity)} h
              </span>
              <Badge tone={a.overload_pct >= 100 ? "err" : "warn"}>+{formatPercent(a.overload_pct)}</Badge>
            </li>
          );
        })}
      </ul>
    </SectionCard>
  );
}

export function OperationsPage() {
  const { t } = useTranslation();

  const [ofSearch, setOfSearch] = useState("");
  const [ofSite, setOfSite] = useState("");
  const byStatus = useQuery({
    queryKey: ["ordres", ofSearch, ofSite],
    queryFn: () => api.ordres(pagedQuery(1, 500, ofSearch, siteQuery(ofSite))),
    placeholderData: keepPreviousData,
    select: (page: Paginated<OrdreFabrication>) => {
      const groups: Groups = {
        prevu: [],
        lance: [],
        en_cours: [],
        termine: [],
        cloture: [],
        annule: [],
      };
      for (const of_ of page.results) {
        if (VALID_STATUSES.has(of_.status)) groups[of_.status].push(of_);
      }
      return groups;
    },
  });

  const charge = useQuery({
    queryKey: ["charge"],
    queryFn: () => api.charge(),
  });

  const situations = usePagedList<SituationTravaux>("situations", (q) => api.situations(q));
  // Heures déclarées : somme sur toutes les situations, pas seulement la page affichée.
  const situationsToutes = useQuery({
    queryKey: ["situations-toutes"],
    queryFn: () => api.listAll<SituationTravaux>("/api/operations/situations/"),
  });

  const affectations = useQuery({
    queryKey: ["affectations"],
    queryFn: () => api.affectations(`?page_size=100`),
    select: (page: Paginated<EquipeAffectation>) => page.results,
  });

  const presences = useQuery({
    queryKey: ["presences"],
    queryFn: () => api.presences(`?page_size=100`),
    select: (page: Paginated<PresenceChantier>) => page.results,
  });

  const equipes = useQuery({
    queryKey: ["equipes"],
    queryFn: () => api.equipes(`?page_size=100`),
    select: (page: Paginated<{ id: string; code: string; label: string }>) => page.results,
  });

  // Lecture RH réservée à certains rôles : sans droit, la liste des salariés reste vide (pas de blocage de l'écran).
  const employes = useQuery({
    queryKey: ["employes", "operations"],
    queryFn: () => api.employes(`?page_size=100`),
    select: (page: Paginated<{ id: string; code: string; nom_complet: string }>) => page.results,
    retry: false,
  });

  if (byStatus.isLoading || charge.isLoading || situations.query.isLoading)
    return <BoardSkeleton cols={5} rows={3} />;
  if (byStatus.isError || charge.isError || situations.query.isError || !byStatus.data)
    return (
      <ErrorState
        message={t("common.error")}
        onRetry={() => {
          void byStatus.refetch();
          void charge.refetch();
          void situations.query.refetch();
          void situationsToutes.refetch();
        }}
        retryLabel={t("common.retry")}
      />
    );

  const groups = byStatus.data;
  const ofOptions = Object.values(groups)
    .flat()
    .filter((o) => o.status !== "cloture" && o.status !== "annule")
    .map((o) => ({ value: o.id, label: `${o.code} — ${o.label}` }));
  const metierOptions = METIERS.map((m) => ({ value: m, label: t(`operations.forms.${m}`) }));
  const equipeOptions = (equipes.data ?? []).map((e) => ({ value: e.id, label: `${e.code} — ${e.label}` }));
  const employeOptions = (employes.data ?? []).map((e) => ({ value: e.id, label: `${e.code} — ${e.nom_complet}` }));
  const scopeOptions = [
    { value: "atelier", label: t("operations.atelier") },
    { value: "chantier", label: t("operations.chantier") },
  ];
  const active = groups.en_cours.length + groups.lance.length + groups.prevu.length;
  const reported = situationsToutes.data?.reduce((a, s) => a + Number(s.ordered_hours), 0) ?? 0;
  const chargeData = charge.data;

  return (
    <div className="listes-page">
      <PageHeader title={t("operations.title")} subtitle={t("listes.sub.operations")} />

      <div className="kpi-grid">
        <Kpi label={t("operations.of")} value={active} icon={HardHat} tone="brand" delay={0} />
        <Kpi label={t("operations.reported")} value={`${formatNumber(reported)} h`} icon={Clock3} tone="accent" delay={0.05} />
        {chargeData
          ? (["atelier", "chantier"] as const).map((key, i) => (
              <Kpi
                key={key}
                label={t(`operations.${key}`)}
                value={`${formatNumber(chargeData.totals[key].calculated)} h`}
                hint={t("revueR2.operations.kpiHint", { pointees: formatNumber(chargeData.totals[key].pointed), count: chargeData.totals[key].count })}
                icon={key === "atelier" ? Factory : Construction}
                tone="brand"
                delay={0.1 + i * 0.05}
              />
            ))
          : null}
      </div>
      {charge.data ? <Charge stats={charge.data} /> : null}

      <section className="listes-block">
        <div className="list-toolbar">
          <SearchField value={ofSearch} onChange={setOfSearch} placeholder={t("operations.searchOf")} />
          <SiteFilter value={ofSite} onChange={setOfSite} />
        </div>
        <Board label={t("listes.boardLabel.operations")}>
          {BOARD_ORDER.map((st, ci) => (
            <BoardColumn key={st} title={t(`operations.${st}`)} count={groups[st].length} tone={STATUS_BADGE[st]} delay={ci * 0.04} limit={20}>
              {groups[st].map((of_, i) => (
                <OfCard key={of_.id} of={of_} index={i} />
              ))}
            </BoardColumn>
          ))}
        </Board>
      </section>

      {(situations.count > 0 || situations.search) && (
        <SectionCard title={`${t("operations.situations")} · ${situations.count}`}>
          <PagedDataTable
            list={situations}
            searchPlaceholder={t("operations.searchSituations")}
            caption={t("operations.situations")}
            columns={[
              { key: "code", header: t("operations.sit.code"), render: (s) => <span style={NOWRAP}>{s.code}</span> },
              { key: "periode", header: t("operations.sit.periode"), render: (s) => <span style={NOWRAP}>{`${formatDate(s.period_start)} → ${formatDate(s.period_end)}`}</span> },
              { key: "heures", header: t("operations.sit.heures"), num: true, render: (s) => `${formatNumber(Number(s.ordered_hours))} h` },
              { key: "avancement", header: t("operations.sit.avancement"), num: true, render: (s) => formatPercent(s.progress) },
              { key: "montant", header: t("operations.sit.montant"), num: true, render: (s) => (s.amount === null ? t("operations.masked") : formatMoney(s.amount)) },
              {
                key: "statut",
                header: t("operations.sit.statut"),
                render: (s) => <Badge tone={s.status === "brouillon" || s.status === "soumise" ? "warn" : "ok"}>{statutLabel("situation", s.status, s.status_label)}</Badge>,
              },
              actionsColumn<SituationTravaux>(t("listes.col.actions"), (s) => [
                ...(s.status === "brouillon" ? [{ label: t("operations.actions.soumettre"), path: `/api/operations/situations/${s.id}/soumettre/` }] : []),
                ...(s.status === "soumise" ? [{ label: t("actions.valider"), path: `/api/operations/situations/${s.id}/validate/` }] : []),
              ]),
            ]}
          />
        </SectionCard>
      )}

      <SectionCard
        title={`${t("operations.equipes")} · ${(affectations.data ?? []).length}`}
        actions={
          <div className="section-actions">
            <QuickForm
              title={t("operations.forms.equipe")}
              endpoint="/api/operations/equipes/"
              fields={[
                { name: "label", label: t("operations.forms.nom"), required: true },
                { name: "metier", label: t("operations.forms.metier"), type: "select", options: metierOptions, required: true },
              ]}
            />
            <QuickForm
              title={t("operations.forms.affectation")}
              endpoint="/api/operations/affectations/"
              fields={[
                { name: "equipe", label: t("operations.forms.equipeChoix"), type: "select", options: equipeOptions, required: true },
                { name: "ordre", label: t("operations.forms.of"), type: "select", options: ofOptions, required: true },
                { name: "date_debut", label: t("operations.forms.debut"), type: "date", required: true },
                { name: "date_fin", label: t("operations.forms.fin"), type: "date", required: true },
                { name: "effectif", label: t("operations.forms.effectif"), type: "number", min: 1, defaultValue: "1" },
              ]}
              transform={(v) => ({ ...v, effectif: Number(v.effectif ?? 1) })}
            />
            <QuickForm
              title={t("operations.forms.capacite")}
              endpoint="/api/operations/capacites/"
              fields={[
                { name: "scope", label: t("operations.forms.perimetre"), type: "select", options: scopeOptions, required: true },
                { name: "resource", label: t("operations.forms.ressource"), type: "select", options: [{ value: "rh", label: t("operations.forms.rh") }], required: true, defaultValue: "rh" },
                { name: "hours_per_week", label: t("operations.forms.heures"), type: "number", min: 1, step: "0.5", required: true },
              ]}
            />
          </div>
          }
        >
          <DataTable
            rows={affectations.data ?? []}
            caption={t("operations.equipes")}
            columns={[
              { key: "equipe", header: t("operations.aff.equipe"), render: (a) => a.equipe_label },
              { key: "metier", header: t("operations.aff.metier"), render: (a) => (METIERS.includes(a.metier) ? t(`operations.forms.${a.metier}`) : a.metier) },
              { key: "of", header: t("operations.aff.of"), render: (a) => <span style={NOWRAP}>{a.ordre_code}</span> },
              { key: "periode", header: t("operations.aff.periode"), render: (a) => <span style={NOWRAP}>{`${formatDate(a.date_debut)} → ${formatDate(a.date_fin)}`}</span> },
              { key: "effectif", header: t("operations.aff.effectif"), num: true, render: (a) => a.effectif },
              {
                key: "statut",
                header: t("operations.aff.statut"),
                render: (a) => <Badge tone={a.statut === "planifiee" ? "warn" : "ok"}>{statutLabel("affectation", a.statut, a.statut_label)}</Badge>,
              },
              actionsColumn<EquipeAffectation>(t("listes.col.actions"), (a) => [
                ...(a.statut === "planifiee"
                  ? [{ label: t("operations.actions.mobiliser"), path: `/api/operations/affectations/${a.id}/mobiliser/`, confirm: t("operations.actions.confirmMobiliser") }]
                  : []),
                ...(a.statut === "mobilisee" ? [{ label: t("operations.actions.terminer"), path: `/api/operations/affectations/${a.id}/terminer/` }] : []),
              ]),
            ]}
          />
        </SectionCard>

        <SectionCard
          title={`${t("operations.presences")} · ${(presences.data ?? []).length}`}
          actions={
            <QuickForm
              title={t("operations.forms.presence")}
              endpoint="/api/operations/presences/"
              fields={[
                { name: "ordre", label: t("operations.forms.of"), type: "select", options: ofOptions, required: true },
                { name: "employe", label: t("operations.forms.employe"), type: "select", options: employeOptions, required: true },
                { name: "date", label: t("operations.forms.date"), type: "date", required: true },
                {
                  name: "statut", label: t("operations.forms.presence_"), type: "select", required: true, defaultValue: "present",
                  options: [
                    { value: "present", label: t("operations.forms.present") },
                    { value: "absent", label: t("operations.forms.absent") },
                    { value: "retard", label: t("operations.forms.retard") },
                  ],
                },
                { name: "motif", label: t("operations.forms.motif") },
              ]}
            />
          }
        >
          <DataTable
            rows={presences.data ?? []}
            caption={t("operations.presences")}
            columns={[
              { key: "date", header: t("operations.pres.date"), render: (p) => <span style={NOWRAP}>{formatDate(p.date)}</span> },
              { key: "employe", header: t("operations.pres.employe"), render: (p) => p.employe_nom },
              { key: "of", header: t("operations.pres.of"), render: (p) => <span style={NOWRAP}>{p.ordre_code}</span> },
              { key: "statut", header: t("operations.pres.statut"), render: (p) => <Badge tone={p.statut === "present" ? "ok" : "warn"}>{statutLabel("presence", p.statut, p.statut_label)}</Badge> },
              { key: "motif", header: t("operations.pres.motif"), render: (p) => p.motif || "—" },
            ]}
          />
        </SectionCard>
      <CoutMainOeuvreSection />
      <EcartsM3Section />
      <ConsommationOfSection />
      <FluxM4Section />
    </div>
  );
}
