import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Activity, Flame, Gauge, Inbox, ShieldAlert, ShieldCheck } from "lucide-react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { ActionBar, Badge, Board, BoardCard, BoardColumn, BoardSkeleton, EmptyState, ErrorState, Kpi, PageHeader, PagedDataGrid, Pagination, QuickForm, SearchField, SectionCard } from "../components/ui";
import type { Column } from "../components/ui";
import { formatDate, formatNumber } from "../lib/format";
import { pagedQuery, usePagedList } from "../lib/usePagedList";
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
import { ConformiteHse } from "../components/hse/ConformiteHse";
import { PermisActions } from "../components/workflow/PermisActions";
import { DemandePermisForm, PermisPieces } from "../components/hse/HsePermisSection";
import { ActionsHseSection, RegistreOshaSection } from "../components/hse/HseEcartsSection";
import {
  AptitudesSection,
  ExigencesPermisSection,
  FormationsNominativesSection,
  ParametresHseSection,
  PersonnelHseSection,
} from "../components/hse/HsePersonnelSection";
import { EnvironnementSection, IndicateursHseSection, RevueDirectionSection } from "../components/hse/HseEnvironnementSection";
import { EcartsM7Sections } from "../components/hse/EcartsM7Section";
import { useListeHse } from "../components/hse/listesHse";

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
        {permis.code} · {t(`hse.permis_types.${permis.type_permis}`, { defaultValue: permis.type_label })}
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
      <PermisPieces permis={permis} />
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
    { key: "type", header: t("hse.col.type"), render: (b) => (t(`hse.dechet_types.${b.type_dechet}`) === `hse.dechet_types.${b.type_dechet}` ? b.type_label : t(`hse.dechet_types.${b.type_dechet}`)) },
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
        {inc.code} <span className="muted">· {t(`hse.incident_types.${inc.type_incident}`, { defaultValue: inc.type_label })}</span>
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
      {inc.zone && <div className="meta muted">{t(`m7e.zones.${inc.zone}`)}</div>}
      {inc.ncr_hse.length > 0 && <div className="meta">NCR-HSE : {inc.ncr_hse.join(", ")}</div>}
      {inc.document_titre && <div className="meta muted">{t("m7e.inc.archive")}</div>}
      <ActionBar
        actions={[
          ...(inc.statut === "declare"
            ? [{ label: t("hse.act.enquete"), path: `/api/hse/incidents/${inc.id}/ouvrir-enquete/`, tone: "ghost" as const }]
            : []),
          ...(inc.statut !== "cloture"
            ? [{
                label: t("m7e.inc.ajouterAction"), path: "/api/hse/actions/", tone: "ghost" as const,
                body: { incident: inc.id, type: "corrective" }, prompt: { name: "description", label: t("m7e.inc.actionPrompt") },
              }]
            : []),
          ...(inc.statut === "en_enquete"
            ? [{ label: t("m7e.inc.planAction"), path: `/api/hse/incidents/${inc.id}/plan-action/`, prompt: { name: "cause_profonde", label: t("m7e.inc.causeProfonde") } }]
            : []),
          ...(inc.statut !== "cloture"
            ? [{
                label: t("actions.cloturer"), path: `/api/hse/incidents/${inc.id}/cloturer/`,
                // Une seule action pleine par carte : pendant l'enquête, c'est l'arrêt du plan d'action.
                ...(inc.statut === "en_enquete" ? { tone: "ghost" as const } : {}),
                prompt: ["quasi_accident", "situation_dangereuse"].includes(inc.type_incident)
                  ? { name: "retour_experience", label: t("m7e.inc.rex") }
                  : { name: "rapport", label: t("hse.act.rapport") },
              }]
            : []),
          ...(inc.statut !== "declare"
            ? [{ label: t("m7e.inc.ncr"), path: `/api/hse/incidents/${inc.id}/ncr-hse/`, tone: "ghost" as const, prompt: { name: "description", label: t("m7e.inc.ncrPrompt") } }]
            : []),
        ]}
      />
      <button type="button" className="btn ghost sm" onClick={() => void api.download(`/api/hse/incidents/${inc.id}/rapport-pdf/`, `${inc.code}.pdf`)}>
        {t("m7e.inc.pdf")}
      </button>
    </BoardCard>
  );
}

export function HsePage() {
  const { t } = useTranslation();

  const stats = useQuery({
    queryKey: ["hse-stats"],
    queryFn: api.hseStats,
  });

  const typesIncident = useListeHse("type_incident");

  const frequence = useQuery({
    queryKey: ["hse-indicateurs"],
    queryFn: () => api.get<IndicateursHse>("/api/hse/incidents/indicateurs/"),
  });

  const permis = usePagedList<PermisTravail>("hse-permis", (q) => api.permis(q));

  const [incSearch, setIncSearch] = useState("");
  const incidents = useQuery({
    queryKey: ["hse-incidents", incSearch],
    queryFn: () => api.incidents(pagedQuery(1, 500, incSearch)),
    placeholderData: keepPreviousData,
    select: (page: Paginated<Incident>) => {
      const groups: IncidentGroups = { declare: [], en_enquete: [], plan_action: [], cloture: [] };
      for (const inc of page.results) {
        if (INC_VALID.has(inc.statut)) groups[inc.statut].push(inc);
      }
      return groups;
    },
  });

  const risques = usePagedList<EvaluationRisque>("hse-risques", (q) => api.risquesHse(q));

  const atex = usePagedList<EquipementAtex>("hse-atex", (q) => api.equipementsAtex(q));

  const formations = usePagedList<FormationSecurite>("hse-formations", (q) => api.formationsHse(q));

  const epis = usePagedList<Epi>("hse-epis", (q) => api.episHse(q));

  const bsd = usePagedList<BordereauDechet>("hse-bsd", (q) => api.bordereauxDechets(q));

  if (stats.isLoading || incidents.isLoading || !stats.data)
    return <BoardSkeleton cols={4} rows={3} />;
  if (stats.isError || incidents.isError || !incidents.data)
    return (
      <ErrorState
        message={t("common.error")}
        onRetry={() => {
          void stats.refetch();
          void permis.query.refetch();
          void incidents.refetch();
          void risques.query.refetch();
          void atex.query.refetch();
          void formations.query.refetch();
          void epis.query.refetch();
          void bsd.query.refetch();
        }}
        retryLabel={t("common.retry")}
      />
    );

  const s = stats.data;
  const permisAll = permis.rows;
  const groups = incidents.data;
  const ouvertNonClos = Object.entries(groups)
    .filter(([k]) => k !== "cloture")
    .reduce((sum, [, arr]) => sum + arr.length, 0);

  return (
    <>
      <PageHeader
        title={t("hse.title")}
        subtitle={t("tableaux.entetes.hse")}
        actions={
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
                options: typesIncident,
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
              {
                name: "zone", label: t("m7e.inc.zone"), type: "select",
                options: ["atelier", "chantier", "bureau", "site_client", "site_gr"].map((v) => ({ value: v, label: t(`m7e.zones.${v}`) })),
              },
              { name: "personnes_impliquees", label: t("m7e.inc.personnes") },
              { name: "description", label: t("hse.form.description"), type: "textarea", required: true },
            ]}
          />
        }
      />

      <div className="kpi-grid">
        <Kpi label={t("hse.joursSansAccident")} value={s.jours_sans_accident ?? t("tableaux.entetes.aucunAccident")} hint={`${s.incidents_ouverts} ${t("hse.incidentsOuverts")}`} icon={ShieldAlert} tone="ok" delay={0} />
        <Kpi label={t("hse.permisActifs")} value={s.permis_actifs} hint={`${s.risques_critiques} ${t("hse.risquesCritiques")}`} icon={ShieldCheck} tone="brand" delay={0.05} />
        <Kpi label={t("hse.atexQuarantaine")} value={s.atex_quarantaine} hint={`${s.actions_ouvertes} ${t("hse.actionsOuvertes")}`} icon={Flame} tone="warn" delay={0.1} />
        <Kpi label={t("hse.epiRenouveler")} value={s.epi_a_renouveler} hint={`${s.formations_prevues} ${t("hse.formationsPrevues")} · ${s.bsd_en_attente} ${t("hse.bsdAttente")}`} icon={Activity} tone="warn" delay={0.15} />
        <Kpi
          label={t("hse.trir")}
          value={frequence.data ? formatNumber(frequence.data.trir, { decimals: 2 }) : "—"}
          hint={`LTIR ${formatNumber(frequence.data?.ltir, { decimals: 2 })} · LTIFR ${formatNumber(frequence.data?.ltifr, { decimals: 2 })} · ${frequence.data?.jours_perdus ?? 0} ${t("hse.joursPerdus")}`}
          icon={Gauge}
          tone="brand"
          delay={0.2}
        />
      </div>

      <SearchField value={incSearch} onChange={setIncSearch} placeholder={t("hse.searchIncidents")} />

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
              limit={20}
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

      <DemandePermisForm />
      {permis.count > 0 || permis.search ? (
        <>
          <h3 className="section-heading">
            {t("hse.permis")}
          </h3>
          <SearchField value={permis.search} onChange={permis.setSearch} placeholder={t("hse.searchPermis")} />
          {permisAll.length === 0 ? (
            <EmptyState icon={Inbox} label={t("common.empty")} />
          ) : (
            <div className="card-list">
              {permisAll.map((p) => <PermisCard key={p.id} permis={p} />)}
            </div>
          )}
          <Pagination page={permis.page} pageSize={permis.pageSize} count={permis.count} onPageChange={permis.setPage} onPageSizeChange={permis.setPageSize} />
        </>
      ) : null}

      {(risques.count > 0 || risques.search) && (
        <SectionCard title={`${t("hse.risques")} · ${risques.count}`}>
          <PagedDataGrid list={risques} columns={risqueColumns(t)} caption={t("hse.risques")} searchPlaceholder={t("hse.searchRisques")} />
        </SectionCard>
      )}
      {(atex.count > 0 || atex.search) && (
        <SectionCard title={`${t("hse.atex")} · ${atex.count}`}>
          <PagedDataGrid list={atex} columns={atexColumns(t)} caption={t("hse.atex")} searchPlaceholder={t("hse.searchAtex")} />
        </SectionCard>
      )}
      {(formations.count > 0 || formations.search) && (
        <SectionCard title={`${t("hse.formations")} · ${formations.count}`}>
          <PagedDataGrid list={formations} columns={formationColumns(t)} caption={t("hse.formations")} searchPlaceholder={t("hse.searchFormations")} />
        </SectionCard>
      )}
      {(epis.count > 0 || epis.search) && (
        <SectionCard title={`${t("hse.epi")} · ${epis.count}`}>
          <PagedDataGrid list={epis} columns={epiColumns(t)} caption={t("hse.epi")} searchPlaceholder={t("hse.searchEpis")} />
        </SectionCard>
      )}
      <ConformiteHse />
      <ActionsHseSection />
      <RegistreOshaSection />
      <PersonnelHseSection />
      <FormationsNominativesSection />
      <AptitudesSection />
      <ExigencesPermisSection />
      <IndicateursHseSection />
      <EnvironnementSection />
      <RevueDirectionSection />
      <ParametresHseSection />
      <EcartsM7Sections />
      {(bsd.count > 0 || bsd.search) && (
        <SectionCard title={`${t("hse.bsd")} · ${bsd.count}`}>
          <PagedDataGrid list={bsd} columns={bsdColumns(t)} caption={t("hse.bsd")} searchPlaceholder={t("hse.searchBsd")} />
        </SectionCard>
      )}
    </>
  );
}