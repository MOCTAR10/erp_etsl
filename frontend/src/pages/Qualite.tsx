import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Award, ClipboardCheck, FileCheck2, ShieldAlert } from "lucide-react";
import { useTranslation } from "react-i18next";

import "../styles/pages/sections.css";
import { api } from "../api/client";
import { formatDate } from "../lib/format";
import { pagedQuery, usePagedList } from "../lib/usePagedList";
import { ActionBar, Badge, Board, BoardCard, BoardColumn, BoardSkeleton, ErrorState, Kpi, PageHeader, PagedDataGrid, QuickForm, SearchField, SectionCard } from "../components/ui";
import type { Column } from "../components/ui";
import { actionsColumn } from "../components/ui/DataTable";
import type {
  ControleQualite,
  NonConformite,
  Paginated,
  PvControle,
  QualificationSoudeur,
  StatutNC,
  WpsWpqr,
} from "../types";
import { ClotureM6Section } from "../components/qualite/ClotureM6Section";
import { EcartsM6Section } from "../components/qualite/EcartsM6Section";
import { EcartsM6bSection } from "../components/qualite/EcartsM6bSection";
import { EcartsM6m7Section } from "../components/qualite/EcartsM6m7Section";
import { EcartsA3Section } from "../components/qualite/EcartsA3Section";
import { SystemeQualiteSection } from "../components/qualite/SystemeQualiteSection";
import { ItpSection } from "../components/workflow/ItpSection";

type NcGroups = Record<StatutNC, NonConformite[]>;

const NC_BADGE: Record<StatutNC, "ok" | "warn" | "err" | "brand"> = {
  signalee: "warn",
  analysee: "brand",
  en_traitement: "warn",
  cloturee: "ok",
};
const NC_ORDER: StatutNC[] = ["signalee", "analysee", "en_traitement", "cloturee"];
const NC_VALID = new Set<StatutNC>(NC_ORDER);

type T = (key: string) => string;

function qualifColumns(t: T): Column<QualificationSoudeur>[] {
  return [
    { key: "code", header: t("qualite.col.code"), render: (q) => q.code },
    {
      key: "soudeur",
      header: t("qualite.col.soudeur"),
      render: (q) => (
        <>
          {q.soudeur_name}
          <span className="cell-sub">{q.soudeur_code}</span>
        </>
      ),
    },
    { key: "norme", header: t("qualite.col.norme"), render: (q) => t(`qualite.norms.${q.norme}`) },
    { key: "procede", header: t("qualite.col.procede"), render: (q) => `${q.procede_label} · ${q.position || "—"}` },
    { key: "validite", header: t("qualite.col.validite"), render: (q) => <span className="r3-nowrap">{formatDate(q.date_validite)}</span> },
    {
      key: "statut",
      header: t("qualite.col.statut"),
      render: (q) =>
        q.statut === "expiree" ? <Badge tone="err">{t("qualite.expiree")}</Badge> : <Badge tone="ok">{t("qualite.valide")}</Badge>,
    },
  ];
}

function wpsColumns(t: T): Column<WpsWpqr>[] {
  return [
    { key: "code", header: t("qualite.col.code"), render: (w) => w.code },
    { key: "type", header: t("qualite.col.type"), render: (w) => t(`qualite.wps_type.${w.type}`) },
    { key: "ref", header: t("qualite.col.reference"), render: (w) => w.reference || "—" },
    { key: "procede", header: t("qualite.col.procede"), render: (w) => w.procede_label },
    { key: "materiau", header: t("qualite.col.materiau"), render: (w) => w.materiau || "—" },
    {
      key: "statut",
      header: t("qualite.col.statut"),
      render: (w) => (
        <>
          <Badge tone={w.statut === "valide" ? "ok" : "brand"}>{t(`qualite.wps_status.${w.statut}`)}</Badge>
          {w.statut === "brouillon" && (
            <ActionBar actions={[{ label: t("actions.valider"), path: `/api/qualite/wps/${w.id}/valider/` }]} />
          )}
        </>
      ),
    },
  ];
}

function ctrlColumns(t: T): Column<ControleQualite>[] {
  return [
    { key: "code", header: t("qualite.col.code"), render: (c) => c.code },
    { key: "type", header: t("qualite.col.type"), render: (c) => t(`qualite.ctrl_types.${c.type_controle}`) },
    { key: "point", header: t("qualite.col.point"), render: (c) => c.point_controle || c.type_label },
    { key: "objet", header: t("qualite.col.objet"), render: (c) => c.affaire_code ?? c.ordre_code ?? c.lot_code ?? "—" },
    {
      key: "organisme",
      header: t("qualite.col.organisme"),
      render: (c) => (c.organisme === "agrege" ? c.organisme_libelle || t("qualite.agrege") : "—"),
    },
    {
      key: "resultat",
      header: t("qualite.col.resultat"),
      render: (c) => (
        <Badge tone={c.resultat === "conforme" ? "ok" : c.resultat === "reserve" ? "warn" : "err"}>
          {t(`qualite.ctrl_result.${c.resultat}`)}
        </Badge>
      ),
    },
  ];
}

function pvColumns(t: T): Column<PvControle>[] {
  return [
    { key: "code", header: t("qualite.col.code"), render: (p) => p.code },
    { key: "intitule", header: t("qualite.intitule"), render: (p) => p.intitule },
    { key: "affaire", header: t("qualite.col.objet"), render: (p) => p.affaire_code ?? "—" },
    { key: "date", header: t("qualite.col.date"), render: (p) => formatDate(p.date_pv) },
    { key: "retention", header: t("qualite.col.retention"), num: true, render: (p) => `${p.retention_years} ${t("qualite.col.ans")}` },
    {
      key: "statut",
      header: t("qualite.col.statut"),
      render: (p) => (
        <Badge tone={p.statut === "receptionne" ? "ok" : p.statut === "reserve" ? "warn" : p.statut === "rejete" ? "err" : "brand"}>
          {t(`qualite.pv_statut.${p.statut}`)}
        </Badge>
      ),
    },
    {
      key: "dossier",
      header: <span className="sr-only">{t("m6e.pv.dossier")}</span>,
      render: (p) => (
        <button type="button" className="btn ghost sm r3-nowrap" onClick={() => void api.download(`/api/qualite/pvs/${p.id}/dossier/`, `dossier-qualite-${p.code}.pdf`)}>
          {t("m6e.pv.dossier")}
        </button>
      ),
    },
    actionsColumn<PvControle>(t("listes.col.actions"), (p) =>
      p.statut === "en_cours" || p.statut === "reserve"
        ? [
            { label: t("m6e.pv.receptionner"), path: `/api/qualite/pvs/${p.id}/levee-reserve/`, body: { reserve: false }, confirm: t("m6e.pv.confirmReception"), tone: "ghost" },
            { label: t("m6e.pv.reserve"), path: `/api/qualite/pvs/${p.id}/levee-reserve/`, body: { reserve: true }, tone: "ghost", prompt: { name: "motif", label: t("m6e.pv.motif") } },
          ]
        : [],
    ),
  ];
}

function NcCard({ nc, index }: { nc: NonConformite; index: number }) {
  const { t } = useTranslation();
  return (
    <BoardCard delay={Math.min(index * 0.03, 0.3)}>
      <div className="card-top">
        <span className="card-code">
          {nc.code} · {t(`qualite.nc_source.${nc.source}`)}
          {nc.controle_code ? ` · ${nc.controle_code}` : ""}
        </span>
      </div>
      <div className="title">{nc.description}</div>
      <div className="card-foot">
        <Badge tone={nc.gravite === "critique" ? "err" : nc.gravite === "majeure" ? "warn" : "neutral"}>{t(`qualite.nc_gravite.${nc.gravite}`)}</Badge>
        <span className="meta">
          {t(`qualite.nc_traitement.${nc.traitement}`)}
          {nc.actions_count > 0 ? ` · ${t("revueR3.qualite.capa", { count: nc.actions_count })}` : ""}
        </span>
      </div>
      <ActionBar
        actions={[
          ...(nc.statut !== "cloturee"
            ? [{
                label: t("qualite.act.traiter"),
                path: `/api/qualite/non-conformites/${nc.id}/traiter/`,
                tone: "ghost" as const,
                prompt: {
                  name: "traitement",
                  label: t("qualite.act.choisirTraitement"),
                  options: ["reprise", "reparation", "rejet", "acceptation", "arbitrage"].map((v) => ({ value: v, label: t(`qualite.nc_traitement.${v}`) })),
                },
              }]
            : []),
          ...(nc.statut === "en_traitement"
            ? [{ label: t("actions.cloturer"), path: `/api/qualite/non-conformites/${nc.id}/cloturer/`, confirm: t("actions.confirmCloturer") }]
            : []),
        ]}
      />
    </BoardCard>
  );
}

export function QualitePage() {
  const { t } = useTranslation();

  // Indicateurs (KPI) : listes complètes, toutes pages ; tableaux : listes paginées avec recherche.
  const qualifsTous = useQuery({ queryKey: ["qualifs-tous"], queryFn: () => api.listAll<QualificationSoudeur>("/api/qualite/qualifications/") });
  const wpsTous = useQuery({ queryKey: ["wps-tous"], queryFn: () => api.listAll<WpsWpqr>("/api/qualite/wps/") });
  const pvsTous = useQuery({ queryKey: ["pvs-tous"], queryFn: () => api.listAll<PvControle>("/api/qualite/pvs/") });
  const qualifs = usePagedList<QualificationSoudeur>("qualifs", (q) => api.qualifications(q));
  const wps = usePagedList<WpsWpqr>("wps", (q) => api.wps(q));
  const controles = usePagedList<ControleQualite>("controles-qualite", (q) => api.controlesQualite(q));
  const pvs = usePagedList<PvControle>("pvs-controle", (q) => api.pvsControle(q));

  const [ncSearch, setNcSearch] = useState("");
  const ncs = useQuery({
    queryKey: ["non-conformites", ncSearch],
    queryFn: () => api.nonConformites(pagedQuery(1, 500, ncSearch)),
    placeholderData: keepPreviousData,
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
    queryFn: () => api.listAll<import("../types").ActionCorrective>("/api/qualite/actions-correctives/"),
  });

  if (qualifsTous.isLoading || ncs.isLoading) return <BoardSkeleton cols={4} rows={3} />;
  if (qualifsTous.isError || ncs.isError || !ncs.data)
    return (
      <ErrorState
        message={t("common.error")}
        onRetry={() => {
          void qualifsTous.refetch();
          void wpsTous.refetch();
          void pvsTous.refetch();
          void qualifs.query.refetch();
          void wps.query.refetch();
          void controles.query.refetch();
          void pvs.query.refetch();
          void ncs.refetch();
          void capa.refetch();
        }}
        retryLabel={t("common.retry")}
      />
    );

  const qualifsAll = qualifsTous.data ?? [];
  const wpsAll = wpsTous.data ?? [];
  const pvAll = pvsTous.data ?? [];
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
      <PageHeader
        title={t("qualite.title")}
        subtitle={t("tableaux.entetes.qualite")}
        actions={
          <QuickForm
            title={t("qualite.form.title")}
            endpoint="/api/qualite/non-conformites/"
            fields={[
              {
                name: "gravite",
                label: t("qualite.form.gravite"),
                type: "select",
                required: true,
                defaultValue: "mineure",
                options: ["mineure", "majeure", "critique"].map((v) => ({ value: v, label: t(`qualite.nc_gravite.${v}`) })),
              },
              { name: "description", label: t("qualite.form.description"), type: "textarea", required: true },
            ]}
          />
        }
      />

      <div className="kpi-grid">
        <Kpi
          label={t("qualite.qualifsValides")}
          value={valids}
          hint={t("revueR3.qualite.surQualifs", { total: qualifsAll.length })}
          icon={Award}
          tone="ok"
          delay={0}
        />
        <Kpi
          label={t("qualite.ncOuvertes")}
          value={openNc}
          hint={t("revueR3.qualite.capaHint", { ouvertes: capaAll.filter((a) => a.statut !== "cloturee").length, total: capaAll.length })}
          icon={ShieldAlert}
          tone="warn"
          delay={0.05}
        />
        <Kpi
          label={t("qualite.wpsValides")}
          value={wpsValid}
          hint={t("revueR3.qualite.surWps", { total: wpsAll.length })}
          icon={FileCheck2}
          tone="brand"
          delay={0.1}
        />
        <Kpi
          label={t("qualite.reservations")}
          value={reservations}
          hint={t("revueR3.qualite.pvHint", { total: pvAll.length })}
          icon={ClipboardCheck}
          tone="accent"
          delay={0.15}
        />
      </div>

      <h3 className="section-heading">{t("revueR3.qualite.nc")}</h3>
      <SearchField value={ncSearch} onChange={setNcSearch} placeholder={t("qualite.searchNc")} />

      <Board label={t("revueR3.qualite.nc")}>
        {NC_ORDER.map((st, ci) => (
          <BoardColumn key={st} title={t(`qualite.nc_statut.${st}`)} count={groups[st].length} tone={NC_BADGE[st]} delay={ci * 0.05} limit={6}>
            {groups[st].map((nc, i) => (
              <NcCard key={nc.id} nc={nc} index={i} />
            ))}
          </BoardColumn>
        ))}
      </Board>

      {(qualifs.count > 0 || qualifs.search) && (
        <SectionCard title={`${t("qualite.qualifs")} · ${qualifs.count}`}>
          <PagedDataGrid list={qualifs} columns={qualifColumns(t)} caption={t("qualite.qualifs")} searchPlaceholder={t("qualite.searchQualifs")} />
        </SectionCard>
      )}
      {(wps.count > 0 || wps.search) && (
        <SectionCard title={`${t("qualite.wps")} · ${wps.count}`}>
          <PagedDataGrid list={wps} columns={wpsColumns(t)} caption={t("qualite.wps")} searchPlaceholder={t("qualite.searchWps")} />
        </SectionCard>
      )}
      {(controles.count > 0 || controles.search) && (
        <SectionCard title={`${t("qualite.controles")} · ${controles.count}`}>
          <PagedDataGrid list={controles} columns={ctrlColumns(t)} caption={t("qualite.controles")} searchPlaceholder={t("qualite.searchControles")} />
        </SectionCard>
      )}
      {(pvs.count > 0 || pvs.search) && (
        <SectionCard title={`${t("qualite.pvs")} · ${pvs.count}`}>
          <PagedDataGrid list={pvs} columns={pvColumns(t)} caption={t("qualite.pvs")} searchPlaceholder={t("qualite.searchPvs")} />
        </SectionCard>
      )}
      <ItpSection />
      <ClotureM6Section />
      <EcartsM6Section />
      <EcartsM6bSection />
      <EcartsM6m7Section />
      <EcartsA3Section />
      <SystemeQualiteSection />
    </>
  );
}