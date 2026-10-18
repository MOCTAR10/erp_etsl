import { useQuery } from "@tanstack/react-query";
import { Award, ClipboardCheck, FileCheck2, ShieldAlert } from "lucide-react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { formatDate } from "../lib/format";
import { ActionBar, Badge, Board, BoardCard, BoardColumn, BoardSkeleton, DataTable, ErrorState, Kpi, PageHeader, QuickForm, SectionCard } from "../components/ui";
import type { Column } from "../components/ui";
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
    { key: "soudeur", header: t("qualite.col.soudeur"), render: (q) => `${q.soudeur_name} (${q.soudeur_code})` },
    { key: "norme", header: t("qualite.col.norme"), render: (q) => t(`qualite.norms.${q.norme}`) },
    { key: "procede", header: t("qualite.col.procede"), render: (q) => `${q.procede_label} · ${q.position || "—"}` },
    { key: "validite", header: t("qualite.col.validite"), render: (q) => formatDate(q.date_validite) },
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
  ];
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

      {qualifsAll.length > 0 && (
        <SectionCard title={`${t("qualite.qualifs")} · ${qualifsAll.length}`}>
          <DataTable rows={qualifsAll} columns={qualifColumns(t)} caption={t("qualite.qualifs")} />
        </SectionCard>
      )}
      {wpsAll.length > 0 && (
        <SectionCard title={`${t("qualite.wps")} · ${wpsAll.length}`}>
          <DataTable rows={wpsAll} columns={wpsColumns(t)} caption={t("qualite.wps")} />
        </SectionCard>
      )}
      {ctrlAll.length > 0 && (
        <SectionCard title={`${t("qualite.controles")} · ${ctrlAll.length}`}>
          <DataTable rows={ctrlAll} columns={ctrlColumns(t)} caption={t("qualite.controles")} />
        </SectionCard>
      )}
      {pvAll.length > 0 && (
        <SectionCard title={`${t("qualite.pvs")} · ${pvAll.length}`}>
          <DataTable rows={pvAll} columns={pvColumns(t)} caption={t("qualite.pvs")} />
        </SectionCard>
      )}
      <ItpSection />
      <ClotureM6Section />
    </>
  );
}