import { useQuery } from "@tanstack/react-query";
import { Award, ClipboardCheck, FileCheck2, FileText, ShieldAlert } from "lucide-react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { formatDate } from "../lib/format";
import { Board, BoardCard, BoardColumn, BoardSkeleton, ErrorState, Kpi, PageHeader } from "../components/ui";
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

function QualifCard({ qual, index }: { qual: QualificationSoudeur; index: number }) {
  const { t } = useTranslation();
  const expired = qual.statut === "expiree";
  return (
    <Kpi
      label={`${qual.code} · ${qual.soudeur_code} · ${t(`qualite.norms.${qual.norme}`)}`}
      value={qual.soudeur_name}
      hint={
        <>
          {qual.procede_label} · {qual.position || "—"} · {formatDate(qual.date_validite, "fr")}
          {expired ? (
            <span className="badge err"> {t("qualite.expiree")}</span>
          ) : (
            <span className="badge ok"> {t("qualite.valide")}</span>
          )}
        </>
      }
      icon={Award}
      tone={expired ? "warn" : "ok"}
      delay={index * 0.05}
    />
  );
}

function WpsCard({ wps, index }: { wps: WpsWpqr; index: number }) {
  const { t } = useTranslation();
  return (
    <Kpi
      label={`${wps.code} · ${t(`qualite.wps_type.${wps.type}`)}`}
      value={wps.reference || "—"}
      hint={
        <>
          {wps.procede_label} · {wps.materiau || "—"} ·{" "}
          <span className={`badge ${wps.statut === "valide" ? "ok" : "brand"}`}>
            {t(`qualite.wps_status.${wps.statut}`)}
          </span>
        </>
      }
      icon={FileCheck2}
      tone={wps.statut === "valide" ? "ok" : "brand"}
      delay={index * 0.05}
    />
  );
}

function CtrlCard({ ctrl, index }: { ctrl: ControleQualite; index: number }) {
  const { t } = useTranslation();
  const badge: "ok" | "warn" | "err" = ctrl.resultat === "conforme" ? "ok" : ctrl.resultat === "reserve" ? "warn" : "err";
  return (
    <Kpi
      label={`${ctrl.code} · ${t(`qualite.ctrl_types.${ctrl.type_controle}`)}`}
      value={ctrl.point_controle || ctrl.type_label}
      hint={
        <>
          {ctrl.affaire_code ?? ctrl.ordre_code ?? ctrl.lot_code ?? "—"}
          {ctrl.organisme === "agrege" ? ` · ${ctrl.organisme_libelle || t("qualite.agrege")}` : ""}
          <span className={`badge ${badge}`}> {t(`qualite.ctrl_result.${ctrl.resultat}`)}</span>
        </>
      }
      icon={ClipboardCheck}
      tone={badge}
      delay={index * 0.05}
    />
  );
}

function NcCard({ nc, index }: { nc: NonConformite; index: number }) {
  const { t } = useTranslation();
  return (
    <BoardCard delay={Math.min(index * 0.03, 0.3)}>
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
    </BoardCard>
  );
}

function PvCard({ pv, index }: { pv: PvControle; index: number }) {
  const { t } = useTranslation();
  const badge: "ok" | "warn" | "err" | "brand" = pv.statut === "receptionne" ? "ok" : pv.statut === "reserve" ? "warn" : pv.statut === "rejete" ? "err" : "brand";
  return (
    <Kpi
      label={`${pv.code} · ${t("qualite.intitule")}`}
      value={pv.intitule}
      hint={
        <>
          {pv.affaire_code ?? "—"} · {formatDate(pv.date_pv, "fr")}
          <span className={`badge ${badge}`}> {t(`qualite.pv_statut.${pv.statut}`)}</span>
          <span className="badge brand"> {pv.retention_years}y</span>
        </>
      }
      icon={FileText}
      tone={badge}
      delay={index * 0.05}
    />
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

  if (qualifs.isLoading || ncs.isLoading) return <BoardSkeleton cols={4} rows={3} />;
  if (qualifs.isError || ncs.isError || !ncs.data)
    return (
      <ErrorState
        message={t("common.error")}
        onRetry={() => {
          void qualifs.refetch();
          void wps.refetch();
          void controles.refetch();
          void pvs.refetch();
          void ncs.refetch();
          void capa.refetch();
        }}
        retryLabel={t("common.retry")}
      />
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
      <PageHeader title={t("qualite.title")} />

      <div className="kpi-grid">
        <Kpi
          label={t("qualite.qualifsValides")}
          value={valids}
          hint={`${t("qualite.qualifs")} · ${qualifsAll.length}`}
          icon={Award}
          tone="ok"
          delay={0}
        />
        <Kpi
          label={t("qualite.ncOuvertes")}
          value={openNc}
          hint={`${t("qualite.capa")} · ${capaAll.length} (ouvertes ${capaAll.filter((a) => a.statut !== "cloturee").length})`}
          icon={ShieldAlert}
          tone="warn"
          delay={0.05}
        />
        <Kpi
          label={t("qualite.wpsValides")}
          value={wpsValid}
          hint={`${t("qualite.wps")} · ${wpsAll.length}`}
          icon={FileCheck2}
          tone="brand"
          delay={0.1}
        />
        <Kpi
          label={t("qualite.reservations")}
          value={reservations}
          hint={`${t("qualite.archive10")} · retention 10 ans`}
          icon={ClipboardCheck}
          tone="accent"
          delay={0.15}
        />
      </div>

      <div style={{ overflowX: "auto" }}>
        <Board>
          {NC_ORDER.map((st, ci) => (
            <BoardColumn
              key={st}
              title={t(`qualite.nc_statut.${st}`)}
              count={groups[st].length}
              tone={NC_BADGE[st]}
              delay={ci * 0.05}
              minWidth={260}
            >
              {groups[st].length === 0 ? (
                <p className="muted" style={{ padding: "0.5rem 0.25rem" }}>
                  {t("common.empty")}
                </p>
              ) : (
                groups[st].map((nc, i) => <NcCard key={nc.id} nc={nc} index={i} />)
              )}
            </BoardColumn>
          ))}
        </Board>
      </div>

      {qualifsAll.length > 0 ? (
        <>
          <h3 className="muted" style={{ marginTop: "2rem" }}>
            {t("qualite.qualifs")}
          </h3>
          <div className="kpi-grid">
            {qualifsAll.map((q, i) => <QualifCard key={q.id} qual={q} index={i} />)}
          </div>
        </>
      ) : null}

      {wpsAll.length > 0 || ctrlAll.length > 0 ? (
        <>
          <h3 className="muted" style={{ marginTop: "2rem" }}>
            {t("qualite.wps")} · {t("qualite.controles")}
          </h3>
          <div className="kpi-grid">
            {wpsAll.map((w, i) => <WpsCard key={w.id} wps={w} index={i} />)}
            {ctrlAll.map((c, i) => <CtrlCard key={c.id} ctrl={c} index={i} />)}
          </div>
        </>
      ) : null}

      {pvAll.length > 0 ? (
        <>
          <h3 className="muted" style={{ marginTop: "2rem" }}>
            {t("qualite.pvs")}
          </h3>
          <div className="kpi-grid">
            {pvAll.map((pv, i) => <PvCard key={pv.id} pv={pv} index={i} />)}
          </div>
        </>
      ) : null}
    </>
  );
}