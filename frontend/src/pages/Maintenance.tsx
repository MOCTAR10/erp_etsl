import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { ClipboardCheck, Coins, Hammer, Wrench } from "lucide-react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { SiteFilter, siteQuery, useSiteOptions } from "../components/sites/SiteFilter";
import { type ActionDef, Badge, Board, BoardCard, BoardColumn, BoardSkeleton, DataGrid, ErrorState, Kpi, PageHeader, QuickForm, SearchField, SectionCard } from "../components/ui";
import { CardActions } from "../components/ui/Board";
import { actionsColumn } from "../components/ui/DataTable";
import type { Column } from "../components/ui";
import { FiabiliteSection, ParametresMaintenanceSection, PiecesRechangeSection } from "../components/workflow/MaintenanceM8Section";
import { ExigencesHabilitationSection, OtDetails, PlansPreventifsSection } from "../components/workflow/MaintenancePlansSection";
import { CoutsMaintenanceSection } from "../components/maintenance/EcartsM5m8Section";
import { LiaisonBcGrSection } from "../components/maintenance/EcartsCorrectifSection";
import { formatDate, formatMoney, formatNumber } from "../lib/format";
import { pagedQuery, usePagedList } from "../lib/usePagedList";
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
  archive: "ok",
  annule: "err",
};
const OT_ORDER: StatutOT[] = ["demande", "planifie", "en_cours", "termine", "cloture", "archive", "annule"];
/** Colonnes du board : les OT annulés restent consultables via la recherche, sans colonne dédiée. */
const OT_BOARD: StatutOT[] = ["demande", "planifie", "en_cours", "termine", "cloture", "archive"];
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

function inspectionActions(i: Inspection, t: (k: string) => string): ActionDef[] {
  const base = `/api/maintenance/inspections/${i.id}`;
  if (i.statut === "planifiee")
    return [{
      label: t("m8e.insp.realiser"), path: `${base}/realiser/`,
      prompt: {
        name: "resultat", label: t("m8e.insp.resultat"),
        options: ["conforme", "sous_reserve", "non_conforme"].map((v) => ({ value: v, label: t(`maintenance.inspection_resultats.${v}`) })),
      },
    }];
  if (i.statut === "realisee" && !i.ot_genere_code && (i.resultat === "non_conforme" || i.resultat === "sous_reserve"))
    return [{ label: t("m8e.insp.creerOt"), path: `${base}/creer-ot/`, tone: "ghost" }];
  return [];
}

function otActions(ot: OrdreTravail, t: (k: string) => string) {
  const base = `/api/maintenance/ordres/${ot.id}`;
  const out: ActionDef[] = [];
  if (ot.statut === "demande" && !ot.qualifie_le)
    out.push({ label: t("m8e.ot.qualifier"), path: `${base}/qualifier/`, tone: "ghost", prompt: { name: "cause", label: t("m8e.ot.diagnostic") } });
  if (ot.statut === "demande") out.push({ label: t("maintenance.act.planifier"), path: `${base}/planifier/`, tone: "ghost" });
  if (ot.statut === "demande" || ot.statut === "planifie") out.push({ label: t("actions.demarrer"), path: `${base}/demarrer/` });
  if (ot.statut === "en_cours") out.push({ label: t("maintenance.act.terminer"), path: `${base}/terminer/` });
  if (ot.statut === "termine")
    out.push({ label: t("actions.cloturer"), path: `${base}/cloturer/`, confirm: t("actions.confirmCloturer") });
  if (ot.statut === "cloture")
    out.push({ label: t("maintenance.act.archiver"), path: `${base}/archiver/`, tone: "ghost", confirm: t("maintenance.act.confirmArchiver") });
  if (!["cloture", "archive", "annule"].includes(ot.statut))
    out.push({ label: t("maintenance.act.annuler"), path: `${base}/annuler/`, tone: "danger", confirm: t("maintenance.act.confirmAnnuler") });
  return out;
}

function OtCard({ ot, index }: { ot: OrdreTravail; index: number }) {
  const { t } = useTranslation();
  const prio = ot.priorite === "critique" ? "err" : "warn";
  const prioVisible = ot.priorite === "critique" || ot.priorite === "haute";
  return (
    <BoardCard delay={Math.min(index * 0.03, 0.3)}>
      <div className="card-top">
        <span className="card-code">
          {ot.code} · {t(`maintenance.ot_types.${ot.type_ot}`)}
        </span>
      </div>
      <div className="title">{ot.description || ot.actif_designation || "—"}</div>
      <div className="meta">{[ot.actif_code, ot.actif_designation].filter(Boolean).join(" · ") || "—"}</div>
      <div className="card-foot">
        {prioVisible ? <Badge tone={prio}>{t(`maintenance.ot_priorites.${ot.priorite}`)}</Badge> : null}
        <span>{[formatDate(ot.date_demande), ot.technicien_name].filter(Boolean).join(" · ")}</span>
        {ot.has_amount_access && ot.cout_total !== null && Number(ot.cout_total) > 0 ? <span className="amount">{formatMoney(ot.cout_total)}</span> : null}
      </div>
      <OtDetails ot={ot} />
      <CardActions actions={otActions(ot, t)} />
    </BoardCard>
  );
}

export function MaintenancePage() {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;

  const stats = useQuery({ queryKey: ["maintenance-stats"], queryFn: api.maintenanceStats });

  // Tableau des actifs paginé ; liste complète (toutes les pages) pour le formulaire et le décompte des arrêts.
  const [actifSite, setActifSite] = useState("");
  const siteOpts = useSiteOptions();
  const actifs = usePagedList<Actif>("maintenance-actifs", (q) => api.actifs(q), { extra: siteQuery(actifSite) });
  const actifsTous = useQuery({
    queryKey: ["maintenance-actifs-choix"],
    queryFn: () => api.listAll<Actif>("/api/maintenance/actifs/"),
  });

  const [otSearch, setOtSearch] = useState("");
  const ordres = useQuery({
    queryKey: ["maintenance-ordres", otSearch],
    queryFn: () => api.ordresTravail(pagedQuery(1, 500, otSearch)),
    placeholderData: keepPreviousData,
    select: (page: Paginated<OrdreTravail>) => {
      const groups: OtGroups = { demande: [], planifie: [], en_cours: [], termine: [], cloture: [], archive: [], annule: [] };
      for (const ot of page.results) {
        if (OT_VALID.has(ot.statut)) groups[ot.statut].push(ot);
      }
      return groups;
    },
  });

  const inspections = usePagedList<Inspection>("maintenance-inspections", (q) => api.inspections(q));

  if (stats.isLoading || ordres.isLoading || !stats.data)
    return <BoardSkeleton cols={6} rows={3} />;
  if (stats.isError || ordres.isError || !ordres.data)
    return (
      <ErrorState
        message={t("common.error")}
        onRetry={() => {
          void stats.refetch();
          void actifs.query.refetch();
          void actifsTous.refetch();
          void ordres.refetch();
          void inspections.query.refetch();
        }}
        retryLabel={t("common.retry")}
      />
    );

  const s = stats.data;
  const actifsAll = actifs.rows;
  const actifsChoix = actifsTous.data ?? [];
  const groups = ordres.data;
  const inspectionsAll = inspections.rows;
  const arrete = actifsChoix.filter((a) => a.en_arret).length;
  const ouvertNonClos = Object.entries(groups)
    .filter(([k]) => !["cloture", "archive", "annule"].includes(k))
    .reduce((sum, [, arr]) => sum + arr.length, 0);

  const actifColumns: Column<Actif>[] = [
    { key: "code", header: t("maintenance.col.code"), sortValue: (a) => a.code, render: (a) => <span className="cell-nowrap">{a.code}</span> },
    {
      key: "designation",
      header: t("maintenance.col.designation"),
      sortValue: (a) => a.designation,
      render: (a) => (
        <>
          {a.designation} {a.is_global_rental && <Badge tone="brand">{t("maintenance.GR")}</Badge>}
          {a.signe_618 && <Badge tone="neutral">{t("maintenance.cpt618")}</Badge>}
        </>
      ),
    },
    { key: "categorie", header: t("maintenance.col.category"), render: (a) => t(`maintenance.categories.${a.categorie}`) },
    { key: "site", header: t("maintenance.col.site"), render: (a) => a.site || "—" },
    { key: "compteur", header: t("maintenance.compteur"), num: true, render: (a) => formatNumber(a.compteur_lecture ?? a.compteur_value) },
    { key: "statut", header: t("maintenance.col.status"), render: (a) => <Badge tone={actifTone(a)}>{t(`maintenance.statut_actif.${a.statut}`)}</Badge> },
    actionsColumn<Actif>(t("listes.col.actions"), (a) =>
      !a.is_global_rental && a.compteur_type !== "aucun"
        ? [{ label: t("revueR2.maintenance.relever"), path: `/api/maintenance/actifs/${a.id}/releve-compteur/`, tone: "ghost", prompt: { name: "valeur", label: t("m8e.actif.nouvelleValeur") } }]
        : [],
    ),
  ];
  const inspectionColumns: Column<Inspection>[] = [
    { key: "code", header: t("maintenance.col.code"), sortValue: (i) => i.code, render: (i) => <span className="cell-nowrap">{i.code}</span> },
    { key: "actif", header: t("maintenance.col.designation"), render: (i) => i.actif_designation },
    { key: "type", header: t("maintenance.col.type"), render: (i) => t(`maintenance.inspection_types.${i.type_inspection}`) },
    { key: "date", header: t("maintenance.col.date"), sortValue: (i) => i.date_inspection, render: (i) => formatDate(i.date_inspection, lang) },
    { key: "prochaine", header: t("maintenance.prochaine"), sortValue: (i) => i.prochaine_inspection, render: (i) => formatDate(i.prochaine_inspection, lang) },
    { key: "ot", header: t("maintenance.col.ot"), render: (i) => i.ot_genere_code ?? "—" },
    {
      key: "statut",
      header: t("maintenance.col.status"),
      render: (i) => (
        <Badge tone={inspectionTone(i)}>
          {i.statut === "realisee" && i.resultat ? t(`maintenance.inspection_resultats.${i.resultat}`) : t(`maintenance.inspection_statut.${i.statut}`)}
        </Badge>
      ),
    },
    actionsColumn<Inspection>(t("listes.col.actions"), (i) => inspectionActions(i, t)),
  ];

  return (
    <div className="listes-page">
      <PageHeader
        title={t("maintenance.title")}
        subtitle={t("listes.sub.maintenance")}
        actions={
          <QuickForm
            title={t("maintenance.form.title")}
            endpoint="/api/maintenance/ordres/"
            fields={[
              {
                name: "actif",
                label: t("maintenance.form.actif"),
                type: "select",
                required: true,
                options: actifsChoix.map((a) => ({ value: a.id, label: `${a.code} · ${a.designation}` })),
              },
              {
                name: "type_ot",
                label: t("maintenance.col.type"),
                type: "select",
                required: true,
                defaultValue: "correctif",
                options: ["correctif", "preventif", "urgence", "inspection"].map((v) => ({ value: v, label: t(`maintenance.ot_types.${v}`) })),
              },
              {
                name: "priorite",
                label: t("maintenance.form.priorite"),
                type: "select",
                required: true,
                defaultValue: "moyenne",
                options: ["basse", "moyenne", "haute", "critique"].map((v) => ({ value: v, label: t(`maintenance.ot_priorites.${v}`) })),
              },
              { name: "date_planifiee", label: t("maintenance.form.datePlanifiee"), type: "date" },
              { name: "description", label: t("maintenance.form.description"), type: "textarea", required: true },
            ]}
          />
        }
      />

      <div className="kpi-grid">
        <Kpi label={t("maintenance.otOuverts")} value={s.ot_ouverts} hint={t("revueR2.maintenance.hintOuverts", { enCours: formatNumber(s.ot_en_cours), count: s.ot_critiques })} icon={Wrench} tone="brand" delay={0} />
        <Kpi label={t("maintenance.actifsArret")} value={arrete || s.actifs_arret} hint={t("revueR2.maintenance.hintArret", { n: formatNumber(s.actifs_operationnels) })} icon={Hammer} tone="warn" delay={0.05} />
        <Kpi label={t("maintenance.inspectionsPrevues")} value={s.inspections_prevues} hint={t("revueR2.maintenance.hintInspections", { h: formatNumber(s.heures_total) })} icon={ClipboardCheck} tone="accent" delay={0.1} />
        <Kpi label={t("maintenance.coutTotal")} value={s.cout_total} kind="money" hint={t("revueR2.maintenance.hintCout", { n: formatNumber(actifs.count) })} icon={Coins} tone="brand" delay={0.15} />
      </div>

      <section className="listes-block">
        <div className="list-toolbar">
          <SearchField value={otSearch} onChange={setOtSearch} placeholder={t("maintenance.searchOt")} />
        </div>
        <Board label={t("listes.boardLabel.maintenance")}>
          {OT_BOARD.map((st, ci) => (
            <BoardColumn key={st} title={t(`maintenance.ot_statut.${st}`)} count={groups[st].length} tone={OT_BADGE[st]} delay={ci * 0.04} limit={20}>
              {groups[st].map((ot, i) => (
                <OtCard key={ot.id} ot={ot} index={i} />
              ))}
            </BoardColumn>
          ))}
        </Board>
        {ouvertNonClos > 0 ? <p className="listes-note">{t("maintenance.pendingNote")}</p> : null}
      </section>

      <SectionCard
        title={`${t("maintenance.actifs")} · ${actifs.count}`}
        actions={
          <QuickForm
            title={t("m8e.actif.nouveau")}
            endpoint="/api/maintenance/actifs/"
            fields={[
              { name: "designation", label: t("maintenance.col.designation"), required: true },
              { name: "site_etsl", label: t("ecarts_a5.site"), type: "select", options: siteOpts },
              {
                name: "categorie", label: t("maintenance.col.category"), type: "select", required: true, defaultValue: "machine",
                options: ["machine", "engin", "levage", "atelier", "chantier", "outillage"].map((v) => ({ value: v, label: t(`maintenance.categories.${v}`) })),
              },
              { name: "numero_serie", label: t("m8e.actif.serie") },
              { name: "site", label: t("maintenance.col.site") },
              {
                name: "compteur_type", label: t("m8e.actif.compteur"), type: "select", required: true, defaultValue: "heures",
                options: ["heures", "km", "aucun"].map((v) => ({ value: v, label: t(`maintenance.compteur_types.${v}`) })),
              },
              { name: "compteur_value", label: t("m8e.actif.valeurCompteur"), type: "number", min: 0, step: "0.01" },
              { name: "date_mise_en_service", label: t("m8e.actif.miseEnService"), type: "date" },
            ]}
          />
        }
      >
        <div className="list-toolbar">
          <SearchField value={actifs.search} onChange={actifs.setSearch} placeholder={t("maintenance.searchActifs")} />
          <SiteFilter value={actifSite} onChange={setActifSite} />
        </div>
        <DataGrid
          rows={actifsAll}
          columns={actifColumns}
          caption={t("maintenance.actifs")}
          loading={actifs.query.isFetching}
          pagination={{ page: actifs.page, pageSize: actifs.pageSize, count: actifs.count, onPageChange: actifs.setPage, onPageSizeChange: actifs.setPageSize }}
        />
      </SectionCard>

      <PlansPreventifsSection actifs={actifsChoix} />
      <FiabiliteSection />
      <PiecesRechangeSection />
      <ExigencesHabilitationSection />
      <CoutsMaintenanceSection />
      <LiaisonBcGrSection />
      <ParametresMaintenanceSection />

      <SectionCard
        title={`${t("maintenance.inspections")} · ${inspections.count}`}
        actions={
          <QuickForm
            title={t("m8e.insp.nouvelle")}
            endpoint="/api/maintenance/inspections/"
            fields={[
              {
                name: "actif", label: t("maintenance.form.actif"), type: "select", required: true,
                options: actifsChoix.map((a) => ({ value: a.id, label: `${a.code} · ${a.designation}` })),
              },
              {
                name: "type_inspection", label: t("maintenance.col.type"), type: "select", required: true, defaultValue: "visuelle",
                options: ["visuelle", "fonctionnelle", "securite", "levage", "atex", "metrologie"].map((v) => ({ value: v, label: t(`maintenance.inspection_types.${v}`) })),
              },
              { name: "date_inspection", label: t("m8e.insp.date"), type: "date", required: true },
              { name: "prochaine_inspection", label: t("maintenance.prochaine"), type: "date" },
              { name: "organisme_libelle", label: t("m8e.insp.organisme") },
            ]}
          />
        }
      >
        <div className="list-toolbar">
          <SearchField value={inspections.search} onChange={inspections.setSearch} placeholder={t("maintenance.searchInspections")} />
        </div>
        <DataGrid
          rows={inspectionsAll}
          columns={inspectionColumns}
          caption={t("maintenance.inspections")}
          loading={inspections.query.isFetching}
          pagination={{ page: inspections.page, pageSize: inspections.pageSize, count: inspections.count, onPageChange: inspections.setPage, onPageSizeChange: inspections.setPageSize }}
        />
      </SectionCard>
    </div>
  );
}
