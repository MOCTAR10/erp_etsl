import { useQuery } from "@tanstack/react-query";
import { ClipboardCheck, Coins, Hammer, Inbox, Wrench } from "lucide-react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { Badge, Board, BoardCard, BoardColumn, BoardSkeleton, EmptyState, ErrorState, Kpi, PageHeader, SectionCard } from "../components/ui";
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

function actifTone(a: Actif): "ok" | "warn" | "err" | "brand" {
  if (a.en_arret) return "warn";
  if (a.statut === "operationnel") return "ok";
  if (a.statut === "reforme" || a.statut === "hors_service") return "err";
  return a.statut === "en_panne" ? "warn" : "brand";
}

function inspectionTone(i: Inspection): "ok" | "warn" | "err" | "brand" {
  if (i.statut === "annulee") return "err";
  if (i.statut !== "realisee") return "brand";
  return i.resultat === "non_conforme" ? "err" : i.resultat === "sous_reserve" ? "warn" : "ok";
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
  const { t, i18n } = useTranslation();
  const lang = i18n.language;

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

      {actifsAll.length > 0 && (
        <SectionCard title={`${t("maintenance.actifs")} · ${actifsAll.length}`}>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>{t("maintenance.col.code")}</th>
                  <th>{t("maintenance.col.designation")}</th>
                  <th>{t("maintenance.col.category")}</th>
                  <th>{t("maintenance.col.site")}</th>
                  <th className="num">{t("maintenance.compteur")}</th>
                  <th>{t("maintenance.col.status")}</th>
                </tr>
              </thead>
              <tbody>
                {actifsAll.map((a) => (
                  <tr key={a.id}>
                    <td>{a.code}</td>
                    <td>
                      {a.designation}{" "}
                      {a.is_global_rental && <Badge tone="brand">{t("maintenance.GR")}</Badge>}{" "}
                      {a.signe_618 && <Badge tone="warn">{t("maintenance.cpt618")}</Badge>}
                    </td>
                    <td>{t(`maintenance.categories.${a.categorie}`)}</td>
                    <td>{a.site || "—"}</td>
                    <td className="num">{String(a.compteur_lecture ?? a.compteur_value)}</td>
                    <td>
                      <Badge tone={actifTone(a)}>{t(`maintenance.statut_actif.${a.statut}`)}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SectionCard>
      )}

      {inspectionsAll.length > 0 && (
        <SectionCard title={`${t("maintenance.inspections")} · ${inspectionsAll.length}`}>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>{t("maintenance.col.code")}</th>
                  <th>{t("maintenance.col.designation")}</th>
                  <th>{t("maintenance.col.type")}</th>
                  <th>{t("maintenance.col.date")}</th>
                  <th>{t("maintenance.prochaine")}</th>
                  <th>{t("maintenance.col.ot")}</th>
                  <th>{t("maintenance.col.status")}</th>
                </tr>
              </thead>
              <tbody>
                {inspectionsAll.map((i) => (
                  <tr key={i.id}>
                    <td>{i.code}</td>
                    <td>{i.actif_designation}</td>
                    <td>{t(`maintenance.inspection_types.${i.type_inspection}`)}</td>
                    <td>{formatDate(i.date_inspection, lang)}</td>
                    <td>{i.prochaine_inspection ? formatDate(i.prochaine_inspection, lang) : "—"}</td>
                    <td>{i.ot_genere_code ?? "—"}</td>
                    <td>
                      <Badge tone={inspectionTone(i)}>
                        {i.statut === "realisee" && i.resultat
                          ? t(`maintenance.inspection_resultats.${i.resultat}`)
                          : t(`maintenance.inspection_statut.${i.statut}`)}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SectionCard>
      )}
    </>
  );
}