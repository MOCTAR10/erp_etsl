import { useQuery } from "@tanstack/react-query";
import { motion } from "motion/react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { formatDate } from "../lib/format";
import { motionTokens } from "../theme/tokens";
import type {
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
        {formatDate(permis.date_debut, "fr")} → {permis.date_fin ? formatDate(permis.date_fin, "fr") : "…"}
        {permis.affaire_code ? ` · ${permis.affaire_code}` : ""}
        <span className={`badge ${badge}`}> {t(`hse.permis_statut.${permis.statut}`)}</span>
      </span>
    </div>
  );
}

function RisqueCard({ risque }: { risque: EvaluationRisque }) {
  const { t } = useTranslation();
  const badge = risque.criticite === "critique" ? "err" : risque.criticite === "elevee" ? "warn" : "brand";
  return (
    <div className="card kpi" key={risque.id}>
      <span className="kpi-label">{risque.code} · {t(`hse.criticite.${risque.criticite}`)}</span>
      <span className="kpi-value">{risque.lieux}</span>
      <span className="meta muted">
        P{risque.probabilite} × G{risque.gravite} = {risque.score}
        <span className={`badge ${badge}`}> {t(`hse.statut_risque.${risque.statut}`)}</span>
      </span>
    </div>
  );
}

function AtexCard({ eq }: { eq: EquipementAtex }) {
  const { t } = useTranslation();
  const badge = eq.statut === "ecarte" ? "err" : eq.statut === "quarantaine" ? "warn" : "ok";
  return (
    <div className="card kpi" key={eq.id}>
      <span className="kpi-label">{eq.code} · {t(`hse.atx_statut.${eq.statut}`)}</span>
      <span className="kpi-value">{eq.designation}</span>
      <span className="meta muted">
        {eq.zone_atex || "—"} · {eq.certificat || "—"}
        {eq.certificat_expire ? (
          <span className="badge err"> {t("hse.atx_expire")}</span>
        ) : (
          <span className={`badge ${badge}`}> {t(`hse.atx_statut.${eq.statut}`)}</span>
        )}
      </span>
    </div>
  );
}

function FormCard({ form }: { form: FormationSecurite }) {
  const { t } = useTranslation();
  return (
    <div className="card kpi" key={form.id}>
      <span className="kpi-label">
        {form.code} · {t(`hse.formation_types.${form.type_session}`)}
      </span>
      <span className="kpi-value">{form.theme}</span>
      <span className="meta muted">
        {formatDate(form.date_session, "fr")}
        {form.nb_participants > 0 ? ` · ${form.nb_participants}${t("hse.participants")}` : ""}
        <span className={`badge ${form.statut === "realisee" ? "ok" : form.statut === "annulee" ? "err" : "brand"}`}>
          {" "}{t(`hse.formation_statut.${form.statut}`)}
        </span>
      </span>
    </div>
  );
}

function EpiCard({ epi }: { epi: Epi }) {
  const { t } = useTranslation();
  return (
    <div className="card kpi" key={epi.id}>
      <span className="kpi-label">{epi.code} · {t(`hse.epi_types.${epi.type_epi}`)}</span>
      <span className="kpi-value">{epi.designation}</span>
      <span className="meta muted">
        {epi.beneficiaire_name ?? "—"}
        {epi.a_renouveler ? (
          <span className="badge warn"> {t("hse.epi_renouveler")}</span>
        ) : (
          <span className={`badge ${epi.statut === "en_usage" ? "brand" : "ok"}`}>
            {" "}{t(`hse.epi_statut.${epi.statut}`)}
          </span>
        )}
      </span>
    </div>
  );
}

function BsdCard({ bsd }: { bsd: BordereauDechet }) {
  const { t } = useTranslation();
  const badge =
    bsd.statut === "traite" ? "ok" : bsd.statut === "emis" ? "brand" : "warn";
  return (
    <div className="card kpi" key={bsd.id}>
      <span className="kpi-label">{bsd.code} · {t(`hse.dechet_types.${bsd.type_dechet}`)}</span>
      <span className="kpi-value">
        {bsd.numero_bsd || "—"} · {bsd.quantite} {bsd.unite_label}
      </span>
      <span className="meta muted">
        {bsd.transporteur_name ?? "—"}
        <span className={`badge ${badge}`}> {t(`hse.bsd_statut.${bsd.statut}`)}</span>
      </span>
    </div>
  );
}

function IncidentCard({ inc }: { inc: Incident }) {
  const { t } = useTranslation();
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: motionTokens.distance.xs, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: motionTokens.duration.base, ease: motionTokens.ease.out }}
      className="task-card"
    >
      <div className="title">
        {inc.code} <span className="muted">· {t(`hse.incident_types.${inc.type_incident}`)}</span>
      </div>
      <div className="meta">{inc.lieu} · {formatDate(inc.date_evenement, "fr")}</div>
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
    </motion.div>
  );
}

export function HsePage() {
  const { t } = useTranslation();

  const stats = useQuery({
    queryKey: ["hse-stats"],
    queryFn: api.hseStats,
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
    return <p className="muted">{t("common.loading")}</p>;
  if (stats.isError || incidents.isError || !incidents.data)
    return (
      <p>
        {t("common.error")}{" "}
        <button
          className="btn ghost"
          onClick={() => {
            void stats.refetch();
            void permis.refetch();
            void incidents.refetch();
            void risques.refetch();
            void atex.refetch();
            void formations.refetch();
            void epis.refetch();
            void bsd.refetch();
          }}
        >
          {t("common.retry")}
        </button>
      </p>
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
      <h2>{t("hse.title")}</h2>

      <div className="kpis">
        <div className="card kpi">
          <span className="kpi-label">{t("hse.joursSansAccident")}</span>
          <span className="kpi-value">{s.jours_sans_accident ?? "∞"}</span>
          <span className="meta muted">{t("hse.incidentsOuverts")} · {s.incidents_ouverts}</span>
        </div>
        <div className="card kpi">
          <span className="kpi-label">{t("hse.permisActifs")}</span>
          <span className="kpi-value">{s.permis_actifs}</span>
          <span className="meta muted">{t("hse.risquesCritiques")} · {s.risques_critiques}</span>
        </div>
        <div className="card kpi">
          <span className="kpi-label">{t("hse.atexQuarantaine")}</span>
          <span className="kpi-value">{s.atex_quarantaine}</span>
          <span className="meta muted">{t("hse.actionsOuvertes")} · {s.actions_ouvertes}</span>
        </div>
        <div className="card kpi">
          <span className="kpi-label">{t("hse.epiRenouveler")}</span>
          <span className="kpi-value">{aRenouveler || s.epi_a_renouveler}</span>
          <span className="meta muted">
            {t("hse.formationsPrevues")} · {s.formations_prevues} · {t("hse.bsdAttente")} · {s.bsd_en_attente}
          </span>
        </div>
      </div>

      <div className="board" style={{ overflowX: "auto" }}>
        {INC_ORDER.map((st) => (
          <motion.div
            key={st}
            layout
            className="board-col"
            style={{ minWidth: 260 }}
            initial={{ opacity: 0, y: motionTokens.distance.sm }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: motionTokens.duration.base, ease: motionTokens.ease.out }}
          >
            <div className="board-col-head">
              <span>{t(`hse.incident_statut.${st}`)}</span>
              <span className={`badge ${INC_BADGE[st]}`}>{groups[st].length}</span>
            </div>
            {groups[st].length === 0 ? (
              <p className="muted" style={{ padding: "0.5rem 0.25rem" }}>
                {t("common.empty")}
              </p>
            ) : (
              groups[st].map((inc) => <IncidentCard key={inc.id} inc={inc} />)
            )}
          </motion.div>
        ))}
      </div>

      {ouvertNonClos > 0 ? (
        <p className="muted" style={{ marginTop: "0.5rem" }}>
          {t("hse.pendingNote")}
        </p>
      ) : null}

      {permisAll.length > 0 ? (
        <>
          <h3 className="muted" style={{ marginTop: "2rem" }}>
            {t("hse.permis")}
          </h3>
          <div className="kpis" style={{ flexWrap: "wrap" }}>
            {permisAll.map((p) => <PermisCard key={p.id} permis={p} />)}
          </div>
        </>
      ) : null}

      {risquesAll.length > 0 ? (
        <>
          <h3 className="muted" style={{ marginTop: "2rem" }}>
            {t("hse.risques")}
          </h3>
          <div className="kpis" style={{ flexWrap: "wrap" }}>
            {risquesAll.map((r) => <RisqueCard key={r.id} risque={r} />)}
          </div>
        </>
      ) : null}

      {(atexAll.length > 0 || formAll.length > 0) ? (
        <>
          <h3 className="muted" style={{ marginTop: "2rem" }}>
            {t("hse.atex")} · {t("hse.formations")}
          </h3>
          <div className="kpis" style={{ flexWrap: "wrap" }}>
            {atexAll.map((eq) => <AtexCard key={eq.id} eq={eq} />)}
            {formAll.map((f) => <FormCard key={f.id} form={f} />)}
          </div>
        </>
      ) : null}

      {(epiAll.length > 0 || bsdAll.length > 0) ? (
        <>
          <h3 className="muted" style={{ marginTop: "2rem" }}>
            {t("hse.epi")} · {t("hse.bsd")}
          </h3>
          <div className="kpis" style={{ flexWrap: "wrap" }}>
            {epiAll.map((e) => <EpiCard key={e.id} epi={e} />)}
            {bsdAll.map((b) => <BsdCard key={b.id} bsd={b} />)}
          </div>
        </>
      ) : null}
    </>
  );
}