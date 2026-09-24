import { useQuery } from "@tanstack/react-query";
import { ClipboardCheck, Coins, Hammer, Inbox, Wrench } from "lucide-react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { Board, BoardCard, BoardColumn, BoardSkeleton, EmptyState, ErrorState, Kpi, PageHeader } from "../components/ui";
import { formatDate } from "../lib/format";
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

function OtCard({ ot, index }: { ot: OrdreTravail; index: number }) {
  const { t } = useTranslation();
  return (
    <BoardCard delay={Math.min(index * 0.03, 0.3)}>
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
    </BoardCard>
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
    return <BoardSkeleton cols={6} rows={3} />;
  if (stats.isError || ordres.isError || !ordres.data)
    return (
      <ErrorState
        message={t("common.error")}
        onRetry={() => {
          void stats.refetch();
          void actifs.refetch();
          void ordres.refetch();
          void inspections.refetch();
        }}
        retryLabel={t("common.retry")}
      />
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
      <PageHeader title={t("maintenance.title")} />

      <div className="kpi-grid">
        <Kpi label={t("maintenance.otOuverts")} value={s.ot_ouverts} hint={`${t("maintenance.enCours")} · ${s.ot_en_cours} · ${t("maintenance.critiques")} · ${s.ot_critiques}`} icon={Wrench} tone="brand" delay={0} />
        <Kpi label={t("maintenance.actifsArret")} value={arrete || s.actifs_arret} hint={`${t("maintenance.operationnels")} · ${s.actifs_operationnels}`} icon={Hammer} tone="warn" delay={0.05} />
        <Kpi label={t("maintenance.inspectionsPrevues")} value={s.inspections_prevues} hint={`${t("maintenance.heuresTotal")} · ${s.heures_total}`} icon={ClipboardCheck} tone="accent" delay={0.1} />
        <Kpi label={t("maintenance.coutTotal")} value={`${s.cout_total > 0 ? s.cout_total.toLocaleString("fr-FR") : "0"} F`} hint={`${t("maintenance.actifs")} · ${actifsAll.length}`} icon={Coins} tone="brand" delay={0.15} />
      </div>

      <div style={{ overflowX: "auto" }}>
        <Board>
          {OT_ORDER.map((st, ci) => (
            <BoardColumn
              key={st}
              title={t(`maintenance.ot_statut.${st}`)}
              count={groups[st].length}
              tone={OT_BADGE[st]}
              delay={ci * 0.05}
              minWidth={260}
            >
              {groups[st].length === 0 ? (
                <EmptyState icon={Inbox} label={t("common.empty")} />
              ) : (
                groups[st].map((ot, i) => <OtCard key={ot.id} ot={ot} index={i} />)
              )}
            </BoardColumn>
          ))}
        </Board>
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