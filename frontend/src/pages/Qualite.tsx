import { useQuery } from "@tanstack/react-query";
import { motion } from "motion/react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { formatDate } from "../lib/format";
import { motionTokens } from "../theme/tokens";
import type {
  ControleQualite,
  NonConformite,
  Paginated,
  PvControle,
  QualificationSoudeur,
  StatutNC,
  WpsWpqr,
} from "../types";

type NcGroups = Record<StatutNC, NonConformite[]>;

const NC_BADGE: Record<StatutNC, "ok" | "warn" | "err" | "brand"> = {
  signalee: "warn",
  analysee: "brand",
  en_traitement: "warn",
  cloturee: "ok",
};
const NC_ORDER: StatutNC[] = ["signalee", "analysee", "en_traitement", "cloturee"];
const NC_VALID = new Set<StatutNC>(NC_ORDER);

function QualifCard({ qual }: { qual: QualificationSoudeur }) {
  const { t } = useTranslation();
  const expired = qual.statut === "expiree";
  return (
    <div className="card kpi" key={qual.id}>
      <span className="kpi-label">
        {qual.code} · {qual.soudeur_code} · {t(`qualite.norms.${qual.norme}`)}
      </span>
      <span className="kpi-value">{qual.soudeur_name}</span>
      <span className="meta muted">
        {qual.procede_label} · {qual.position || "—"} · {formatDate(qual.date_validite, "fr")}
        {expired ? (
          <span className="badge err"> {t("qualite.expiree")}</span>
        ) : (
          <span className="badge ok"> {t("qualite.valide")}</span>
        )}
      </span>
    </div>
  );
}

function WpsCard({ wps }: { wps: WpsWpqr }) {
  const { t } = useTranslation();
  return (
    <div className="card kpi" key={wps.id}>
      <span className="kpi-label">
        {wps.code} · {t(`qualite.wps_type.${wps.type}`)}
      </span>
      <span className="kpi-value">{wps.reference || "—"}</span>
      <span className="meta muted">
        {wps.procede_label} · {wps.materiau || "—"} ·{" "}
        <span className={`badge ${wps.statut === "valide" ? "ok" : "brand"}`}>
          {t(`qualite.wps_status.${wps.statut}`)}
        </span>
      </span>
    </div>
  );
}

function CtrlCard({ ctrl }: { ctrl: ControleQualite }) {
  const { t } = useTranslation();
  const badge = ctrl.resultat === "conforme" ? "ok" : ctrl.resultat === "reserve" ? "warn" : "err";
  return (
    <div className="card kpi" key={ctrl.id}>
      <span className="kpi-label">
        {ctrl.code} · {t(`qualite.ctrl_types.${ctrl.type_controle}`)}
      </span>
      <span className="kpi-value">{ctrl.point_controle || ctrl.type_label}</span>
      <span className="meta muted">
        {ctrl.affaire_code ?? ctrl.ordre_code ?? ctrl.lot_code ?? "—"}
        {ctrl.organisme === "agrege" ? ` · ${ctrl.organisme_libelle || t("qualite.agrege")}` : ""}
        <span className={`badge ${badge}`}> {t(`qualite.ctrl_result.${ctrl.resultat}`)}</span>
      </span>
    </div>
  );
}

function NcCard({ nc }: { nc: NonConformite }) {
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
        {nc.code} <span className="muted">· {t(`qualite.nc_source.${nc.source}`)}</span>
      </div>
      <div className="meta">{nc.description}</div>
      <div className="meta" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span className={`badge ${nc.gravite === "critique" ? "err" : nc.gravite === "majeure" ? "warn" : "brand"}`}>
          {t(`qualite.nc_gravite.${nc.gravite}`)}
        </span>
        <span>{t(`qualite.nc_traitement.${nc.traitement}`)}</span>
      </div>
      <div className="meta muted">
        {nc.controle_code ? `· ${nc.controle_code}` : ""}
        {nc.actions_count > 0 ? ` · ${t("qualite.capa")} ×${nc.actions_count}` : ""}
      </div>
    </motion.div>
  );
}

function PvCard({ pv }: { pv: PvControle }) {
  const { t } = useTranslation();
  const badge = pv.statut === "receptionne" ? "ok" : pv.statut === "reserve" ? "warn" : pv.statut === "rejete" ? "err" : "brand";
  return (
    <div className="card kpi" key={pv.id}>
      <span className="kpi-label">{pv.code} · {t("qualite.intitule")}</span>
      <span className="kpi-value">{pv.intitule}</span>
      <span className="meta muted">
        {pv.affaire_code ?? "—"} · {formatDate(pv.date_pv, "fr")}
        <span className={`badge ${badge}`}> {t(`qualite.pv_statut.${pv.statut}`)}</span>
        <span className="badge brand"> {pv.retention_years}y</span>
      </span>
    </div>
  );
}

export function QualitePage() {
  const { t } = useTranslation();

  const qualifs = useQuery({
    queryKey: ["qualifs"],
    queryFn: () => api.qualifications(`?page_size=200`),
    select: (page: Paginated<QualificationSoudeur>) => page.results,
  });

  const wps = useQuery({
    queryKey: ["wps"],
    queryFn: () => api.wps(`?page_size=50`),
    select: (page: Paginated<WpsWpqr>) => page.results,
  });

  const controles = useQuery({
    queryKey: ["controles-qualite"],
    queryFn: () => api.controlesQualite(`?page_size=30`),
    select: (page: Paginated<ControleQualite>) => page.results,
  });

  const pvs = useQuery({
    queryKey: ["pvs-controle"],
    queryFn: () => api.pvsControle(`?page_size=30`),
    select: (page: Paginated<PvControle>) => page.results,
  });

  const ncs = useQuery({
    queryKey: ["non-conformites"],
    queryFn: () => api.nonConformites(`?page_size=100`),
    select: (page: Paginated<NonConformite>) => {
      const groups: NcGroups = { signalee: [], analysee: [], en_traitement: [], cloturee: [] };
      for (const nc of page.results) {
        if (NC_VALID.has(nc.statut)) groups[nc.statut].push(nc);
      }
      return groups;
    },
  });

  const capa = useQuery({
    queryKey: ["capa"],
    queryFn: () => api.actionsCorrectives(`?page_size=50`),
    select: (page: Paginated<import("../types").ActionCorrective>) => page.results,
  });

  if (qualifs.isLoading || ncs.isLoading)
    return <p className="muted">{t("common.loading")}</p>;
  if (qualifs.isError || ncs.isError || !ncs.data)
    return (
      <p>
        {t("common.error")}{" "}
        <button
          className="btn ghost"
          onClick={() => {
            void qualifs.refetch();
            void wps.refetch();
            void controles.refetch();
            void pvs.refetch();
            void ncs.refetch();
            void capa.refetch();
          }}
        >
          {t("common.retry")}
        </button>
      </p>
    );

  const qualifsAll = qualifs.data ?? [];
  const wpsAll = wps.data ?? [];
  const ctrlAll = controles.data ?? [];
  const pvAll = pvs.data ?? [];
  const capaAll = capa.data ?? [];
  const groups = ncs.data;
  const openNc = Object.entries(groups)
    .filter(([k]) => k !== "cloturee")
    .reduce((s, [, arr]) => s + arr.length, 0);
  const valids = qualifsAll.filter((q) => q.est_valide).length;
  const wpsValid = wpsAll.filter((w) => w.statut === "valide").length;
  const reservations = pvAll.filter((p) => p.statut === "reserve").length;

  return (
    <>
      <h2>{t("qualite.title")}</h2>

      <div className="kpis">
        <div className="card kpi">
          <span className="kpi-label">{t("qualite.qualifsValides")}</span>
          <span className="kpi-value">{valids}</span>
          <span className="meta muted">
            {t("qualite.qualifs")} · {qualifsAll.length}
          </span>
        </div>
        <div className="card kpi">
          <span className="kpi-label">{t("qualite.ncOuvertes")}</span>
          <span className="kpi-value">{openNc}</span>
          <span className="meta muted">
            {t("qualite.capa")} · {capaAll.length} (ouvertes {capaAll.filter((a) => a.statut !== "cloturee").length})
          </span>
        </div>
        <div className="card kpi">
          <span className="kpi-label">{t("qualite.wpsValides")}</span>
          <span className="kpi-value">{wpsValid}</span>
          <span className="meta muted">{t("qualite.wps")} · {wpsAll.length}</span>
        </div>
        <div className="card kpi">
          <span className="kpi-label">{t("qualite.reservations")}</span>
          <span className="kpi-value">{reservations}</span>
          <span className="meta muted">{t("qualite.archive10")} · retention 10 ans</span>
        </div>
      </div>

      <div className="board" style={{ overflowX: "auto" }}>
        {NC_ORDER.map((st) => (
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
              <span>{t(`qualite.nc_statut.${st}`)}</span>
              <span className={`badge ${NC_BADGE[st]}`}>{groups[st].length}</span>
            </div>
            {groups[st].length === 0 ? (
              <p className="muted" style={{ padding: "0.5rem 0.25rem" }}>
                {t("common.empty")}
              </p>
            ) : (
              groups[st].map((nc) => <NcCard key={nc.id} nc={nc} />)
            )}
          </motion.div>
        ))}
      </div>

      {qualifsAll.length > 0 ? (
        <>
          <h3 className="muted" style={{ marginTop: "2rem" }}>
            {t("qualite.qualifs")}
          </h3>
          <div className="kpis" style={{ flexWrap: "wrap" }}>
            {qualifsAll.map((q) => <QualifCard key={q.id} qual={q} />)}
          </div>
        </>
      ) : null}

      {(wpsAll.length > 0 || ctrlAll.length > 0) ? (
        <>
          <h3 className="muted" style={{ marginTop: "2rem" }}>
            {t("qualite.wps")} · {t("qualite.controles")}
          </h3>
          <div className="kpis" style={{ flexWrap: "wrap" }}>
            {wpsAll.map((w) => <WpsCard key={w.id} wps={w} />)}
            {ctrlAll.map((c) => <CtrlCard key={c.id} ctrl={c} />)}
          </div>
        </>
      ) : null}

      {pvAll.length > 0 ? (
        <>
          <h3 className="muted" style={{ marginTop: "2rem" }}>
            {t("qualite.pvs")}
          </h3>
          <div className="kpis" style={{ flexWrap: "wrap" }}>
            {pvAll.map((pv) => <PvCard key={pv.id} pv={pv} />)}
          </div>
        </>
      ) : null}
    </>
  );
}