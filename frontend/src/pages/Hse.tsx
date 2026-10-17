import { useQuery } from "@tanstack/react-query";
import { Activity, Flame, Gauge, Inbox, ShieldAlert, ShieldCheck } from "lucide-react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { ActionBar, Badge, Board, BoardCard, BoardColumn, BoardSkeleton, DataTable, EmptyState, ErrorState, Kpi, PageHeader, QuickForm, SectionCard } from "../components/ui";
import type { Column } from "../components/ui";
import { formatDate } from "../lib/format";
import type {
  IndicateursHse,
  BordereauDechet,
  Epi,
  EquipementAtex,
  EvaluationRisque,
  FormationSecurite,
  Incident,
  Paginated,
  PermisTravail,
  StatutIncident,
} from "../types";
import { PermisActions } from "../components/workflow/PermisActions";

type IncidentGroups = Record<StatutIncident, Incident[]>;

const INC_BADGE: Record<StatutIncident, "ok" | "warn" | "err" | "brand"> = {
  declare: "warn",
  en_enquete: "brand",
  plan_action: "warn",
  cloture: "ok",
};
const INC_ORDER: StatutIncident[] = ["declare", "en_enquete", "plan_action", "cloture"];
const INC_VALID = new Set<StatutIncident>(INC_ORDER);

function PermisCard({ permis }: { permis: PermisTravail }) {
  const { t } = useTranslation();
  const badge =
    permis.statut === "actif" ? "ok" : permis.statut === "valide" ? "brand" : permis.statut === "refuse" || permis.statut === "annule" ? "err" : "warn";
  return (
    <div className="card kpi" key={permis.id}>
      <span className="kpi-label">
        {permis.code} · {t(`hse.permis_types.${permis.type_permis}`)}
      </span>
      <span className="kpi-value">{permis.emplacement}</span>
      <span className="meta muted">
        {formatDate(permis.date_debut)} → {permis.date_fin ? formatDate(permis.date_fin) : "…"}
        {permis.affaire_code ? ` · ${permis.affaire_code}` : ""}
        <span className={`badge ${badge}`}> {t(`hse.permis_statut.${permis.statut}`)}</span>
        {permis.gaz_obligatoire && (
          <span
            className={`badge ${
              permis.test_gaz_resultat === "non_conforme" ? "err" : permis.test_gaz_valide ? "ok" : "warn"
            }`}
            title={permis.test_gaz_valeur || undefined}
          >
            {" "}
            {t(
              permis.test_gaz_resultat === "non_conforme"
                ? "hse.gaz.nonConforme"
                : permis.test_gaz_valide
                  ? "hse.gaz.conforme"
                  : "hse.gaz.aFaire",
            )}
          </span>
        )}
      </span>
      <PermisActions permis={permis} />
    </div>
  );
}

type T = (key: string) => string;

function risqueColumns(t: T): Column<EvaluationRisque>[] {
  return [
    { key: "code", header: t("hse.col.code"), render: (r) => r.code },
    { key: "lieux", header: t("hse.col.lieux"), render: (r) => r.lieux },
    { key: "score", header: t("hse.col.score"), num: true, render: (r) => `P${r.probabilite} × G${r.gravite} = ${r.score}` },
    {
      key: "crit",
      header: t("hse.col.criticite"),
      render: (r) => (
        <Badge tone={r.criticite === "critique" ? "err" : r.criticite === "elevee" ? "warn" : "brand"}>
          {t(`hse.criticite.${r.criticite}`)}
        </Badge>
      ),
    },
    { key: "statut", header: t("hse.col.statut"), render: (r) => t(`hse.statut_risque.${r.statut}`) },
  ];
}

function atexColumns(t: T): Column<EquipementAtex>[] {
  return [
    { key: "code", header: t("hse.col.code"), render: (e) => e.code },
    { key: "designation", header: t("hse.col.designation"), render: (e) => e.designation },
    { key: "zone", header: t("hse.col.zone"), render: (e) => e.zone_atex || "—" },
    { key: "cert", header: t("hse.col.certificat"), render: (e) => e.certificat || "—" },
    {
      key: "statut",
      header: t("hse.col.statut"),
      render: (e) =>
        e.certificat_expire ? (
          <Badge tone="err">{t("hse.atx_expire")}</Badge>
        ) : (
          <Badge tone={e.statut === "ecarte" ? "err" : e.statut === "quarantaine" ? "warn" : "ok"}>
            {t(`hse.atx_statut.${e.statut}`)}
          </Badge>
        ),
    },
  ];
}

function formationColumns(t: T): Column<FormationSecurite>[] {
  return [
    { key: "code", header: t("hse.col.code"), render: (f) => f.code },
    { key: "theme", header: t("hse.col.theme"), render: (f) => f.theme },
    { key: "type", header: t("hse.col.type"), render: (f) => t(`hse.formation_types.${f.type_session}`) },
    { key: "date", header: t("hse.col.date"), render: (f) => formatDate(f.date_session) },
    { key: "nb", header: t("hse.col.participants"), num: true, render: (f) => f.nb_participants },
    {
      key: "statut",
      header: t("hse.col.statut"),
      render: (f) => (
        <Badge tone={f.statut === "realisee" ? "ok" : f.statut === "annulee" ? "err" : "brand"}>
          {t(`hse.formation_statut.${f.statut}`)}
        </Badge>
      ),
    },
  ];
}

function epiColumns(t: T): Column<Epi>[] {
  return [
    { key: "code", header: t("hse.col.code"), render: (e) => e.code },
    { key: "designation", header: t("hse.col.designation"), render: (e) => e.designation },
    { key: "type", header: t("hse.col.type"), render: (e) => t(`hse.epi_types.${e.type_epi}`) },
    { key: "benef", header: t("hse.col.beneficiaire"), render: (e) => e.beneficiaire_name ?? "—" },
    {
      key: "statut",
      header: t("hse.col.statut"),
      render: (e) =>
        e.a_renouveler ? (
          <Badge tone="warn">{t("hse.epi_renouveler")}</Badge>
        ) : (
          <Badge tone={e.statut === "en_usage" ? "brand" : "ok"}>{t(`hse.epi_statut.${e.statut}`)}</Badge>
        ),
    },
  ];
}

function bsdColumns(t: T): Column<BordereauDechet>[] {
  return [
    { key: "code", header: t("hse.col.code"), render: (b) => b.code },
    { key: "numero", header: t("hse.col.numeroBsd"), render: (b) => b.numero_bsd || "—" },
    { key: "type", header: t("hse.col.type"), render: (b) => t(`hse.dechet_types.${b.type_dechet}`) },
    { key: "qty", header: t("hse.col.quantite"), num: true, render: (b) => `${b.quantite} ${b.unite_label}` },
    { key: "transp", header: t("hse.col.transporteur"), render: (b) => b.transporteur_name ?? "—" },
    {
      key: "statut",
      header: t("hse.col.statut"),
      render: (b) => (
        <Badge tone={b.statut === "traite" ? "ok" : b.statut === "emis" ? "brand" : "warn"}>
          {t(`hse.bsd_statut.${b.statut}`)}
        </Badge>
      ),
    },
  ];
}

function IncidentCard({ inc, index }: { inc: Incident; index: number }) {
  const { t } = useTranslation();
  return (
    <BoardCard delay={Math.min(index * 0.03, 0.3)}>
      <div className="title">
        {inc.code} <span className="muted">· {t(`hse.incident_types.${inc.type_incident}`)}</span>
      </div>
      <div className="meta">{inc.lieu} · {formatDate(inc.date_evenement)}</div>
      <div className="meta">{inc.description}</div>
      <div className="meta" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span className={`badge ${inc.gravite === "critique" ? "err" : inc.gravite === "majeure" ? "warn" : "brand"}`}>
          {t(`hse.incident_gravite.${inc.gravite}`)}
        </span>
        <span className="muted">
          {inc.enqueteur_name ? `${t("hse.enqueteur")} · ${inc.enqueteur_name}` : ""}
          {inc.actions_count > 0 ? ` · ${t("hse.actions")} ×${inc.actions_count}` : ""}
        </span>
      </div>
      <ActionBar
        actions={[
          ...(inc.statut === "declare"
            ? [{ label: t("hse.act.enquete"), path: `/api/hse/incidents/${inc.id}/ouvrir-enquete/`, tone: "ghost" as const }]
            : []),
          ...(inc.statut !== "cloture"
            ? [{ label: t("actions.cloturer"), path: `/api/hse/incidents/${inc.id}/cloturer/`, prompt: { name: "rapport", label: t("hse.act.rapport") } }]
            : []),
        ]}
      />
    </BoardCard>
  );
}

export function HsePage() {
  const { t } = useTranslation();

  const stats = useQuery({
    queryKey: ["hse-stats"],
    queryFn: api.hseStats,
  });

  const frequence = useQuery({
    queryKey: ["hse-indicateurs"],
    queryFn: () => api.get<IndicateursHse>("/api/hse/incidents/indicateurs/"),
  });

  const permis = useQuery({
    queryKey: ["hse-permis"],
    queryFn: () => api.permis(`?page_size=50`),
    select: (page: Paginated<PermisTravail>) => page.results,
  });

  const incidents = useQuery({
    queryKey: ["hse-incidents"],
    queryFn: () => api.incidents(`?page_size=100`),
    select: (page: Paginated<Incident>) => {
      const groups: IncidentGroups = { declare: [], en_enquete: [], plan_action: [], cloture: [] };
      for (const inc of page.results) {
        if (INC_VALID.has(inc.statut)) groups[inc.statut].push(inc);
      }
      return groups;
    },
  });

  const risques = useQuery({
    queryKey: ["hse-risques"],
    queryFn: () => api.risquesHse(`?page_size=50`),
    select: (page: Paginated<EvaluationRisque>) => page.results,
  });

  const atex = useQuery({
    queryKey: ["hse-atex"],
    queryFn: () => api.equipementsAtex(`?page_size=50`),
    select: (page: Paginated<EquipementAtex>) => page.results,
  });

  const formations = useQuery({
    queryKey: ["hse-formations"],
    queryFn: () => api.formationsHse(`?page_size=50`),
    select: (page: Paginated<FormationSecurite>) => page.results,
  });

  const epis = useQuery({
    queryKey: ["hse-epis"],
    queryFn: () => api.episHse(`?page_size=50`),
    select: (page: Paginated<Epi>) => page.results,
  });

  const bsd = useQuery({
    queryKey: ["hse-bsd"],
    queryFn: () => api.bordereauxDechets(`?page_size=30`),
    select: (page: Paginated<BordereauDechet>) => page.results,
  });

  if (stats.isLoading || incidents.isLoading || !stats.data)
    return <BoardSkeleton cols={4} rows={3} />;
  if (stats.isError || incidents.isError || !incidents.data)
    return (
      <ErrorState
        message={t("common.error")}
        onRetry={() => {
          void stats.refetch();
          void permis.refetch();
          void incidents.refetch();
          void risques.refetch();
          void atex.refetch();
          void formations.refetch();
          void epis.refetch();
          void bsd.refetch();
        }}
        retryLabel={t("common.retry")}
      />
    );

  const s = stats.data;
  const permisAll = permis.data ?? [];
  const groups = incidents.data;
  const risquesAll = risques.data ?? [];
  const atexAll = atex.data ?? [];
  const formAll = formations.data ?? [];
  const epiAll = epis.data ?? [];
  const bsdAll = bsd.data ?? [];
  const ouvertNonClos = Object.entries(groups)
    .filter(([k]) => k !== "cloture")
    .reduce((sum, [, arr]) => sum + arr.length, 0);
  const aRenouveler = epiAll.filter((e) => e.a_renouveler).length;

  return (
    <>
      <PageHeader title={t("hse.title")} />
      <QuickForm
        title={t("hse.form.title")}
        endpoint="/api/hse/incidents/"
        fields={[
          {
            name: "type_incident",
            label: t("hse.col.type"),
            type: "select",
            required: true,
            defaultValue: "quasi_accident",
            options: ["quasi_accident", "incident", "accident", "blessure", "depart_feu", "pollution", "deversement", "dommage_materiel", "situation_dangereuse"].map(
              (v) => ({ value: v, label: t(`hse.incident_types.${v}`) }),
            ),
          },
          {
            name: "gravite",
            label: t("hse.gravite"),
            type: "select",
            required: true,
            defaultValue: "mineure",
            options: ["mineure", "majeure", "critique"].map((v) => ({ value: v, label: t(`hse.incident_gravite.${v}`) })),
          },
          { name: "date_evenement", label: t("hse.form.date"), type: "datetime-local", required: true },
          { name: "lieu", label: t("hse.col.lieux"), required: true },
          { name: "description", label: t("hse.form.description"), type: "textarea", required: true },
        ]}
      />

      <div className="kpi-grid">
        <Kpi label={t("hse.joursSansAccident")} value={s.jours_sans_accident ?? "∞"} hint={`${t("hse.incidentsOuverts")} · ${s.incidents_ouverts}`} icon={ShieldAlert} tone="ok" delay={0} />
        <Kpi label={t("hse.permisActifs")} value={s.permis_actifs} hint={`${t("hse.risquesCritiques")} · ${s.risques_critiques}`} icon={ShieldCheck} tone="brand" delay={0.05} />
        <Kpi label={t("hse.atexQuarantaine")} value={s.atex_quarantaine} hint={`${t("hse.actionsOuvertes")} · ${s.actions_ouvertes}`} icon={Flame} tone="warn" delay={0.1} />
        <Kpi label={t("hse.epiRenouveler")} value={aRenouveler || s.epi_a_renouveler} hint={`${t("hse.formationsPrevues")} · ${s.formations_prevues} · ${t("hse.bsdAttente")} · ${s.bsd_en_attente}`} icon={Activity} tone="warn" delay={0.15} />
        <Kpi
          label={t("hse.trir")}
          value={frequence.data?.trir ?? "—"}
          hint={`LTIR ${frequence.data?.ltir ?? "—"} · LTIFR ${frequence.data?.ltifr ?? "—"} · ${t("hse.joursPerdus")} ${frequence.data?.jours_perdus ?? 0}`}
          icon={Gauge}
          tone="brand"
          delay={0.2}
        />
      </div>

      <div style={{ overflowX: "auto" }}>
        <Board>
          {INC_ORDER.map((st, ci) => (
            <BoardColumn
              key={st}
              title={t(`hse.incident_statut.${st}`)}
              count={groups[st].length}
              tone={INC_BADGE[st]}
              delay={ci * 0.05}
              minWidth={260}
            >
              {groups[st].length === 0 ? (
                <EmptyState icon={Inbox} label={t("common.empty")} />
              ) : (
                groups[st].map((inc, i) => <IncidentCard key={inc.id} inc={inc} index={i} />)
              )}
            </BoardColumn>
          ))}
        </Board>
      </div>

      {ouvertNonClos > 0 ? (
        <p className="muted" style={{ marginTop: "0.5rem" }}>
          {t("hse.pendingNote")}
        </p>
      ) : null}

      {permisAll.length > 0 ? (
        <>
          <h3 className="section-heading">
            {t("hse.permis")}
          </h3>
          <div className="card-list">
            {permisAll.map((p) => <PermisCard key={p.id} permis={p} />)}
          </div>
        </>
      ) : null}

      {risquesAll.length > 0 && (
        <SectionCard title={`${t("hse.risques")} · ${risquesAll.length}`}>
          <DataTable rows={risquesAll} columns={risqueColumns(t)} caption={t("hse.risques")} />
        </SectionCard>
      )}
      {atexAll.length > 0 && (
        <SectionCard title={`${t("hse.atex")} · ${atexAll.length}`}>
          <DataTable rows={atexAll} columns={atexColumns(t)} caption={t("hse.atex")} />
        </SectionCard>
      )}
      {formAll.length > 0 && (
        <SectionCard title={`${t("hse.formations")} · ${formAll.length}`}>
          <DataTable rows={formAll} columns={formationColumns(t)} caption={t("hse.formations")} />
        </SectionCard>
      )}
      {epiAll.length > 0 && (
        <SectionCard title={`${t("hse.epi")} · ${epiAll.length}`}>
          <DataTable rows={epiAll} columns={epiColumns(t)} caption={t("hse.epi")} />
        </SectionCard>
      )}
      {bsdAll.length > 0 && (
        <SectionCard title={`${t("hse.bsd")} · ${bsdAll.length}`}>
          <DataTable rows={bsdAll} columns={bsdColumns(t)} caption={t("hse.bsd")} />
        </SectionCard>
      )}
    </>
  );
}