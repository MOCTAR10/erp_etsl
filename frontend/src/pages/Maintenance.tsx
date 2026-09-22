import { useQuery } from "@tanstack/react-query";
import { motion } from "motion/react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { formatDate } from "../lib/format";
import { motionTokens } from "../theme/tokens";
import type {
  Actif,
  Inspection,
  OrdreTravail,
  Paginated,
  StatutOT,
} from "../types";

type OtGroups = Record<StatutOT, OrdreTravail[]>;

const OT_BADGE: Record<StatutOT, "ok" | "warn" | "err" | "brand"> = {
  demande: "warn",
  planifie: "brand",
  en_cours: "brand",
  termine: "warn",
  cloture: "ok",
  annule: "err",
};
const OT_ORDER: StatutOT[] = ["demande", "planifie", "en_cours", "termine", "cloture", "annule"];
const OT_VALID = new Set<StatutOT>(OT_ORDER);

function ActifCard({ actif }: { actif: Actif }) {
  const { t } = useTranslation();
  const badge =
    actif.statut === "operationnel"
      ? "ok"
      : actif.statut === "reforme" || actif.statut === "hors_service"
        ? "err"
        : actif.statut === "en_panne"
          ? "warn"
          : "brand";
  return (
    <div className="card kpi" key={actif.id}>
      <span className="kpi-label">
        {actif.code} · {t(`maintenance.categories.${actif.categorie}`)}
        {actif.is_global_rental ? <span className="badge brand"> {t("maintenance.GR")}</span> : null}
        {actif.signe_618 ? <span className="badge warn"> {t("maintenance.cpt618")}</span> : null}
      </span>
      <span className="kpi-value">{actif.designation}</span>
      <span className="meta muted">
        {actif.site || "—"} · {t("maintenance.compteur")} {String(actif.compteur_lecture ?? actif.compteur_value)}
        {actif.en_arret ? (
          <span className="badge warn"> {t(`maintenance.statut_actif.${actif.statut}`)}</span>
        ) : (
          <span className={`badge ${badge}`}> {t(`maintenance.statut_actif.${actif.statut}`)}</span>
        )}
      </span>
    </div>
  );
}

function InspectionCard({ insp }: { insp: Inspection }) {
  const { t } = useTranslation();
  const badge =
    insp.statut === "realisee" ? (insp.resultat === "non_conforme" ? "err" : insp.resultat === "sous_reserve" ? "warn" : "ok") : insp.statut === "annulee" ? "err" : "brand";
  return (
    <div className="card kpi" key={insp.id}>
      <span className="kpi-label">
        {insp.code} · {t(`maintenance.inspection_types.${insp.type_inspection}`)}
      </span>
      <span className="kpi-value">{insp.actif_designation}</span>
      <span className="meta muted">
        {formatDate(insp.date_inspection, "fr")}
        {insp.prochaine_inspection ? ` · ${t("maintenance.prochaine")} ${formatDate(insp.prochaine_inspection, "fr")}` : ""}
        {insp.ot_genere_code ? ` · ${insp.ot_genere_code}` : ""}
        {insp.statut === "realisee" && insp.resultat ? (
          <span className={`badge ${badge}`}> {t(`maintenance.inspection_resultats.${insp.resultat}`)}</span>
        ) : (
          <span className={`badge ${badge}`}> {t(`maintenance.inspection_statut.${insp.statut}`)}</span>
        )}
      </span>
    </div>
  );
}

function OtCard({ ot }: { ot: OrdreTravail }) {
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
        {ot.code} <span className="muted">· {t(`maintenance.ot_types.${ot.type_ot}`)}</span>
        {ot.actif_code ? <span className="muted"> · {ot.actif_code}</span> : null}
      </div>
      <div className="meta">{ot.actif_designation || "—"}</div>
      <div className="meta">{ot.description}</div>
      <div className="meta" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span className={`badge ${ot.priorite === "critique" ? "err" : ot.priorite === "haute" ? "warn" : "brand"}`}>
          {t(`maintenance.ot_priorites.${ot.priorite}`)}
        </span>
        <span className="muted">
          {formatDate(ot.date_demande, "fr")}
          {ot.technicien_name ? ` · ${ot.technicien_name}` : ""}
          {ot.has_amount_access && ot.cout_total !== null ? ` · ${ot.cout_total} F` : ""}
        </span>
      </div>
    </motion.div>
  );
}

export function MaintenancePage() {
  const { t } = useTranslation();

  const stats = useQuery({ queryKey: ["maintenance-stats"], queryFn: api.maintenanceStats });

  const actifs = useQuery({
    queryKey: ["maintenance-actifs"],
    queryFn: () => api.actifs(`?page_size=50`),
    select: (page: Paginated<Actif>) => page.results,
  });

  const ordres = useQuery({
    queryKey: ["maintenance-ordres"],
    queryFn: () => api.ordresTravail(`?page_size=100`),
    select: (page: Paginated<OrdreTravail>) => {
      const groups: OtGroups = { demande: [], planifie: [], en_cours: [], termine: [], cloture: [], annule: [] };
      for (const ot of page.results) {
        if (OT_VALID.has(ot.statut)) groups[ot.statut].push(ot);
      }
      return groups;
    },
  });

  const inspections = useQuery({
    queryKey: ["maintenance-inspections"],
    queryFn: () => api.inspections(`?page_size=50`),
    select: (page: Paginated<Inspection>) => page.results,
  });

  if (stats.isLoading || ordres.isLoading || !stats.data)
    return <p className="muted">{t("common.loading")}</p>;
  if (stats.isError || ordres.isError || !ordres.data)
    return (
      <p>
        {t("common.error")}{" "}
        <button
          className="btn ghost"
          onClick={() => {
            void stats.refetch();
            void actifs.refetch();
            void ordres.refetch();
            void inspections.refetch();
          }}
        >
          {t("common.retry")}
        </button>
      </p>
    );

  const s = stats.data;
  const actifsAll = actifs.data ?? [];
  const groups = ordres.data;
  const inspectionsAll = inspections.data ?? [];
  const arrete = actifsAll.filter((a) => a.en_arret).length;
  const ouvertNonClos = Object.entries(groups)
    .filter(([k]) => k !== "cloture")
    .reduce((sum, [, arr]) => sum + arr.length, 0);

  return (
    <>
      <h2>{t("maintenance.title")}</h2>

      <div className="kpis">
        <div className="card kpi">
          <span className="kpi-label">{t("maintenance.otOuverts")}</span>
          <span className="kpi-value">{s.ot_ouverts}</span>
          <span className="meta muted">{t("maintenance.enCours")} · {s.ot_en_cours} · {t("maintenance.critiques")} · {s.ot_critiques}</span>
        </div>
        <div className="card kpi">
          <span className="kpi-label">{t("maintenance.actifsArret")}</span>
          <span className="kpi-value">{arrete || s.actifs_arret}</span>
          <span className="meta muted">{t("maintenance.operationnels")} · {s.actifs_operationnels}</span>
        </div>
        <div className="card kpi">
          <span className="kpi-label">{t("maintenance.inspectionsPrevues")}</span>
          <span className="kpi-value">{s.inspections_prevues}</span>
          <span className="meta muted">{t("maintenance.heuresTotal")} · {s.heures_total}</span>
        </div>
        <div className="card kpi">
          <span className="kpi-label">{t("maintenance.coutTotal")}</span>
          <span className="kpi-value">{s.cout_total > 0 ? s.cout_total.toLocaleString("fr-FR") : "0"} F</span>
          <span className="meta muted">{t("maintenance.actifs")} · {actifsAll.length}</span>
        </div>
      </div>

      <div className="board" style={{ overflowX: "auto" }}>
        {OT_ORDER.map((st) => (
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
              <span>{t(`maintenance.ot_statut.${st}`)}</span>
              <span className={`badge ${OT_BADGE[st]}`}>{groups[st].length}</span>
            </div>
            {groups[st].length === 0 ? (
              <p className="muted" style={{ padding: "0.5rem 0.25rem" }}>
                {t("common.empty")}
              </p>
            ) : (
              groups[st].map((ot) => <OtCard key={ot.id} ot={ot} />)
            )}
          </motion.div>
        ))}
      </div>

      {ouvertNonClos > 0 ? (
        <p className="muted" style={{ marginTop: "0.5rem" }}>
          {t("maintenance.pendingNote")}
        </p>
      ) : null}

      {actifsAll.length > 0 ? (
        <>
          <h3 className="muted" style={{ marginTop: "2rem" }}>
            {t("maintenance.actifs")}
          </h3>
          <div className="kpis" style={{ flexWrap: "wrap" }}>
            {actifsAll.map((a) => <ActifCard key={a.id} actif={a} />)}
          </div>
        </>
      ) : null}

      {inspectionsAll.length > 0 ? (
        <>
          <h3 className="muted" style={{ marginTop: "2rem" }}>
            {t("maintenance.inspections")}
          </h3>
          <div className="kpis" style={{ flexWrap: "wrap" }}>
            {inspectionsAll.map((i) => <InspectionCard key={i.id} insp={i} />)}
          </div>
        </>
      ) : null}
    </>
  );
}