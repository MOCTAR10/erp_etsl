import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { ArrowLeftRight, Boxes, FileDown, Package, Warehouse } from "lucide-react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { useSiteOptions } from "../components/sites/SiteFilter";
import { formatDate, formatMoney, formatNumber } from "../lib/format";
import { nomPersonne } from "../components/sections/affichage";
import { pagedQuery, usePagedList } from "../lib/usePagedList";
import { ActionBar, Badge, Board, BoardCard, BoardColumn, BoardSkeleton, DataGrid, DataTable, ErrorState, Kpi, PageHeader, PagedDataGrid, QuickForm, SearchField, SectionCard } from "../components/ui";
import { CardActions } from "../components/ui/Board";
import { actionsColumn } from "../components/ui/DataTable";
import type { Column } from "../components/ui";
import { AlertesStockSection, AuditValorisationSection, CertificatActions, ConfigArticlesSection, ParametresStockSection, TracabiliteSection, lotActions } from "../components/workflow/StocksEcartsSection";
import { ReservationsStockSection } from "../components/suivi/SuiviSections";
import { InventaireAnnuelSection } from "../components/stocks/EcartsM5m8Section";
import type {
  CertificatMatiere,
  Depot,
  Inventaire,
  LotMatiere,
  LotStatut,
  MouvementStock,
  OrdreFabrication,
  Paginated,
  PlanInventaireTournant,
  StockQuant,
  ValorisationMensuelle,
  ValorisationRow,
} from "../types";

type Groups = Record<LotStatut, LotMatiere[]>;

const STATUS_BADGE: Record<LotStatut, "ok" | "warn" | "err" | "brand"> = {
  disponible: "ok",
  partiel: "brand",
  epuise: "err",
  bloque: "warn",
};
const VALID_STATUSES = new Set<LotStatut>(["disponible", "partiel", "epuise", "bloque"]);
const BOARD_ORDER: LotStatut[] = ["disponible", "partiel", "bloque", "epuise"];

function LotCard({ lot, index }: { lot: LotMatiere; index: number }) {
  const { t } = useTranslation();
  const actions = lotActions(lot, t);
  return (
    <BoardCard delay={Math.min(index * 0.03, 0.3)}>
      <div className="card-top">
        <span className="card-code">
          {lot.code} · {lot.article_code}
        </span>
        {lot.certificats.length > 0 ? (
          <span className="card-tags">
            <Badge tone="neutral">{t("stocks.mtc")}</Badge>
          </span>
        ) : null}
      </div>
      <div className="title">{lot.article_label}</div>
      <div className="meta">
        {t("stocks.lot")} {lot.numero_lot} · {formatDate(lot.date_reception)}
        {lot.numero_coulee ? ` · ${t("m5e.lot.coulee")} ${lot.numero_coulee}` : ""}
      </div>
      {lot.statut === "bloque" && lot.motif_blocage && (
        <div className="meta" role="note">
          {t("m5e.lot.quarantaine")} : {lot.motif_blocage}
          {lot.nc_blocage_code ? ` (${lot.nc_blocage_code})` : ""}
        </div>
      )}
      <div className="card-foot">
        <Badge tone={STATUS_BADGE[lot.statut] ?? "brand"}>{t(`stocks.lot_status.${lot.statut}`)}</Badge>
        <span className="amount">
          {t("listes.stocks.restant", { restant: formatNumber(Number(lot.quantite_restante)), initial: formatNumber(Number(lot.quantite_initiale)) })}
        </span>
      </div>
      <CardActions actions={actions} primary={actions[0]?.label} />
    </BoardCard>
  );
}

type ValoLine = ValorisationRow & { id: string };
type QuantLine = StockQuant;

export function StocksPage() {
  const { t } = useTranslation();

  const [lotSearch, setLotSearch] = useState("");
  const lots = useQuery({
    queryKey: ["lots", lotSearch],
    queryFn: () => api.lotsStocks(pagedQuery(1, 500, lotSearch)),
    placeholderData: keepPreviousData,
    select: (page: Paginated<LotMatiere>) => {
      const groups: Groups = { disponible: [], partiel: [], epuise: [], bloque: [] };
      for (const lot of page.results) {
        if (VALID_STATUSES.has(lot.statut)) groups[lot.statut].push(lot);
      }
      return groups;
    },
  });

  const ordres = useQuery({
    queryKey: ["stocks-ordres"],
    queryFn: () => api.listAll<OrdreFabrication>("/api/operations/ordres/"),
    select: (rows: OrdreFabrication[]) => rows.filter((o) => !["cloture", "annule"].includes(o.status)),
    retry: 0,
  });
  const articles = useQuery({
    queryKey: ["articles-stock"],
    queryFn: () => api.listAll<{ id: string; code: string; label: string }>("/api/referentiels/articles/"),
  });

  const siteOpts = useSiteOptions();
  const depots = useQuery({
    queryKey: ["depots"],
    queryFn: () => api.listAll<Depot>("/api/stocks/depots/?active=1"),
  });

  const quants = useQuery({
    queryKey: ["quants"],
    queryFn: () => api.quantsStock(`?positive=1&page_size=500`),
    select: (page: Paginated<StockQuant>) => page.results,
  });

  const mouvements = usePagedList<MouvementStock>("mouvements-stock", (q) => api.mouvementsStock(q), { pageSize: 20 });

  const valorisation = useQuery({
    queryKey: ["valorisation"],
    queryFn: () => api.valorisation(),
  });

  const certificats = usePagedList<CertificatMatiere>("certificats", (q) => api.certificats(q), { pageSize: 20 });

  const inventaires = usePagedList<Inventaire>("inventaires", (q) => api.inventaires(q), { pageSize: 20 });

  const valoMensuelles = useQuery({
    queryKey: ["valorisations-mensuelles"],
    queryFn: () => api.listAll<ValorisationMensuelle>("/api/stocks/valorisations/"),
  });

  const plans = useQuery({
    queryKey: ["plans-inventaire"],
    queryFn: () => api.listAll<PlanInventaireTournant>("/api/stocks/plans-inventaire/"),
  });

  if (lots.isLoading || quants.isLoading) return <BoardSkeleton cols={4} rows={3} />;
  if (lots.isError || quants.isError || !lots.data)
    return (
      <ErrorState
        message={t("common.error")}
        onRetry={() => {
          void lots.refetch();
          void quants.refetch();
          void depots.refetch();
          void mouvements.query.refetch();
          void valorisation.refetch();
          void certificats.query.refetch();
          void inventaires.query.refetch();
        }}
        retryLabel={t("common.retry")}
      />
    );

  const groups = lots.data;
  const allLots = Object.values(groups).flat();
  const quantsAll = quants.data ?? [];
  const valAll: ValoLine[] = (valorisation.data ?? []).map((r, i) => ({ ...r, id: `${r.depot}-${r.article}-${r.lot ?? ""}-${i}` }));
  const hasAmount = valAll.length > 0 && valorisation.data !== undefined;
  const totalValue = hasAmount ? valAll.reduce((s, r) => s + (r.value ?? 0), 0) : null;
  const depotOptions = (depots.data ?? []).map((d) => ({ value: d.id, label: `${d.code} · ${d.label}` }));
  const lotOptions = allLots.map((l) => ({ value: l.id, label: `${l.code} · ${l.numero_lot}` }));
  const articleOptions = (articles.data ?? []).map((a) => ({ value: a.id, label: `${a.code} · ${a.label}` }));

  const valoColumns: Column<ValoLine>[] = [
    { key: "article", header: t("stocks.col.article"), sortValue: (r) => r.article, render: (r) => <span className="cell-nowrap">{r.article}</span> },
    { key: "depot", header: t("stocks.col.depot"), sortValue: (r) => r.depot, render: (r) => <span className="cell-nowrap">{r.depot}</span> },
    { key: "method", header: t("stocks.col.method"), render: (r) => t(`stocks.methods.${r.method}`) },
    { key: "qty", header: t("stocks.col.qty"), num: true, sortValue: (r) => r.quantity, render: (r) => formatNumber(r.quantity) },
    { key: "pu", header: t("stocks.col.unitCost"), num: true, render: (r) => (r.value === undefined ? "—" : formatMoney(r.unit_cost)) },
    { key: "value", header: t("stocks.col.value"), num: true, sortValue: (r) => r.value, render: (r) => (r.value === undefined ? t("stocks.demi") : formatMoney(r.value)) },
  ];
  const quantColumns: Column<QuantLine>[] = [
    { key: "article", header: t("stocks.col.article"), render: (q) => <><span className="cell-nowrap">{q.article_code}</span><span className="cell-sub">{q.article_label}</span></> },
    { key: "depot", header: t("stocks.col.depot"), render: (q) => <span className="cell-nowrap">{q.depot_code}</span> },
    { key: "lot", header: t("stocks.col.lot"), render: (q) => <span className="cell-nowrap">{q.lot_code ?? "—"}</span> },
    { key: "qty", header: t("stocks.col.qty"), num: true, render: (q) => formatNumber(Number(q.quantity)) },
    { key: "value", header: t("stocks.col.value"), num: true, render: (q) => (q.stock_value === null ? t("stocks.demi") : formatMoney(q.stock_value)) },
  ];
  const mvtColumns: Column<MouvementStock>[] = [
    { key: "code", header: t("stocks.col.code"), render: (m) => <span className="cell-nowrap">{m.code}</span> },
    { key: "type", header: t("stocks.col.type"), render: (m) => t(`stocks.type_labels.${m.type_mouvement}`) },
    { key: "article", header: t("stocks.col.article"), render: (m) => <span className="cell-nowrap">{m.article_code ?? "—"}</span> },
    { key: "qty", header: t("stocks.col.qty"), num: true, sortValue: (m) => Number(m.quantite), render: (m) => formatNumber(Number(m.quantite), { decimals: Number(m.quantite) % 1 ? 2 : 0 }) },
    {
      key: "flow",
      header: t("stocks.col.flow"),
      render: (m) => (
        <>
          <span className="cell-nowrap">
            {m.source_code ?? (m.type_mouvement === "inventaire" ? "—" : t("revueR2.stocks.exterieur"))} →{" "}
            {m.destination_code ?? m.ordre_code ?? (m.type_mouvement === "inventaire" ? "—" : t("revueR2.stocks.exterieur"))}
          </span>
          {m.ordre_code && m.destination_code ? <span className="cell-sub">{m.ordre_code}</span> : null}
        </>
      ),
    },
    { key: "date", header: t("stocks.col.date"), sortValue: (m) => m.date, render: (m) => formatDate(m.date) },
    {
      key: "doc",
      header: <span className="sr-only">{t("listes.col.actions")}</span>,
      render: (m) =>
        m.type_mouvement === "consommation" || m.type_mouvement === "transfert" ? (
          <button
            type="button"
            className="btn ghost sm"
            title={m.document_titre || undefined}
            onClick={() => void api.download(`/api/stocks/mouvements/${m.id}/bon-de-sortie/`, `BS-${m.code}.pdf`)}
          >
            <FileDown size={14} aria-hidden /> <span className="cell-nowrap">{t("m5e.mvt.bonSortie")}</span>
          </button>
        ) : m.document_titre ? (
          <span className="cell-sub">{m.document_titre}</span>
        ) : null,
    },
  ];
  const certColumns: Column<CertificatMatiere>[] = [
    { key: "code", header: t("stocks.col.code"), render: (c) => <span className="cell-nowrap">{c.code}</span> },
    { key: "type", header: t("stocks.col.type"), render: (c) => (c.type === "mtc" ? t("stocks.mtc") : t("stocks.coc")) },
    { key: "num", header: t("stocks.col.certNo"), render: (c) => <span className="cell-nowrap">{c.numero_certificat}</span> },
    { key: "lot", header: t("stocks.col.lot"), render: (c) => <span className="cell-nowrap">{c.lot_code ?? "—"}</span> },
    { key: "org", header: t("stocks.col.organisme"), render: (c) => c.organisme || "—" },
    {
      key: "statut",
      header: t("stocks.col.status"),
      render: (c) => <Badge tone={c.conforme ? "ok" : "err"}>{c.conforme ? t("stocks.certConforme") : t("stocks.certNonConforme")}</Badge>,
    },
    {
      key: "validation",
      header: t("m5e.cert.validation"),
      render: (c) => (
        <>
          {c.date_validation ? (
            <>
              {formatDate(c.date_validation)}
              {c.valide_par_name ? <span className="cell-sub">{nomPersonne(t, c.valide_par_name)}</span> : null}
            </>
          ) : (
            <Badge tone="warn">{t("m5e.cert.aValider")}</Badge>
          )}
          {c.document_titre && <span className="cell-sub">{t("m5e.cert.ged")}</span>}
        </>
      ),
    },
    { key: "actions", header: <span className="sr-only">{t("listes.col.actions")}</span>, render: (c) => <CertificatActions cert={c} /> },
  ];
  const invColumns: Column<Inventaire>[] = [
    { key: "code", header: t("stocks.col.code"), render: (i) => <span className="cell-nowrap">{i.code}</span> },
    { key: "depot", header: t("stocks.col.depot"), render: (i) => i.depot_label },
    { key: "date", header: t("stocks.col.date"), render: (i) => formatDate(i.date) },
    {
      key: "statut",
      header: t("stocks.col.status"),
      render: (i) => <Badge tone={i.statut === "cloture" ? "ok" : i.statut === "annule" ? "err" : "warn"}>{t(`stocks.inv_status.${i.statut}`)}</Badge>,
    },
    { key: "ecart", header: t("stocks.ecarts"), num: true, render: (i) => formatNumber(Number(i.ecart_total)) },
    actionsColumn<Inventaire>(t("listes.col.actions"), (i) =>
      i.statut === "brouillon" || i.statut === "en_cours"
        ? [{ label: t("actions.cloturer"), path: `/api/stocks/inventaires/${i.id}/cloturer/`, confirm: t("stocks.form.confirmCloture") }]
        : [],
    ),
  ];
  const valoMensColumns: Column<ValorisationMensuelle>[] = [
    { key: "periode", header: t("stocks.periode"), sortValue: (v) => v.periode, render: (v) => v.periode },
    { key: "depot", header: t("stocks.col.depot"), render: (v) => <span className="cell-nowrap">{v.depot_code}</span> },
    { key: "valeur", header: t("stocks.col.value"), num: true, render: (v) => (v.valeur_stock === null ? t("stocks.demi") : formatMoney(v.valeur_stock)) },
    { key: "conso", header: t("stocks.consoMois"), num: true, render: (v) => (v.consommation === null ? t("stocks.demi") : formatMoney(v.consommation)) },
    { key: "ecriture", header: t("m5e.valo.ecriture"), render: (v) => (v.move_number ? <Badge tone="ok">{v.move_number}</Badge> : <span className="muted">{v.motif_ecriture || "—"}</span>) },
  ];
  const planColumns: Column<PlanInventaireTournant>[] = [
    { key: "code", header: t("stocks.col.code"), render: (p) => <span className="cell-nowrap">{p.code}</span> },
    { key: "depot", header: t("stocks.col.depot"), render: (p) => p.depot_label },
    { key: "per", header: t("stocks.periodicite"), num: true, render: (p) => p.periodicite_jours },
    { key: "pass", header: t("stocks.parPassage"), num: true, render: (p) => p.articles_par_passage },
    { key: "next", header: t("stocks.prochainPassage"), render: (p) => formatDate(p.prochaine_date) },
    actionsColumn<PlanInventaireTournant>(t("listes.col.actions"), (p) => [{ label: t("stocks.generer"), path: `/api/stocks/plans-inventaire/${p.id}/generer/` }]),
  ];

  return (
    <div className="listes-page">
      <PageHeader
        title={t("stocks.title")}
        subtitle={t("listes.sub.stocks")}
        actions={
          <QuickForm
            title={t("stocks.form.title")}
            endpoint="/api/stocks/mouvements/"
            fields={[
              {
                name: "type_mouvement",
                label: t("stocks.col.type"),
                type: "select",
                required: true,
                defaultValue: "reception",
                options: ["reception", "transfert", "consommation", "retour"].map((v) => ({ value: v, label: t(`stocks.type_labels.${v}`) })),
              },
              { name: "article", label: t("stocks.col.article"), type: "select", required: true, options: articleOptions },
              { name: "quantite", label: t("stocks.col.qty"), type: "number", required: true, min: 0, step: "0.001" },
              { name: "prix_unitaire", label: t("stocks.col.unitCost"), type: "number", min: 0, step: "0.01" },
              { name: "source", label: t("stocks.form.source"), type: "select", options: depotOptions },
              { name: "destination", label: t("stocks.form.destination"), type: "select", options: depotOptions },
              {
                name: "ordre",
                label: t("m5e.mvt.ordre"),
                type: "select",
                options: (ordres.data ?? []).map((o) => ({ value: o.id, label: `${o.code} · ${o.label}` })),
              },
              { name: "lot", label: t("stocks.col.lot"), type: "select", options: lotOptions },
              { name: "document_reference", label: t("stocks.form.reference") },
            ]}
          />
        }
      />

      <div className="kpi-grid">
        <Kpi
          label={t("stocks.valeurStock")}
          value={totalValue === null ? t("stocks.demi") : totalValue}
          kind="money"
          hint={`${t("stocks.quants")} · ${quantsAll.length}`}
          icon={Boxes}
          tone="brand"
          delay={0}
        />
        <Kpi
          label={t("stocks.depots")}
          value={depots.data?.length ?? "—"}
          hint={(depots.data ?? []).map((d) => d.code).slice(0, 3).join(" · ") || "—"}
          icon={Warehouse}
          tone="accent"
          delay={0.05}
        />
        <Kpi label={t("stocks.totalLots")} value={allLots.length} hint={`${t("stocks.perf")} · ${certificats.count}`} icon={Package} tone="brand" delay={0.1} />
        <Kpi label={t("stocks.totalMvt")} value={mouvements.count} hint={`${t("stocks.inventaires")} · ${inventaires.count}`} icon={ArrowLeftRight} tone="warn" delay={0.15} />
      </div>

      <section className="listes-block">
        <div className="list-toolbar">
          <SearchField value={lotSearch} onChange={setLotSearch} placeholder={t("stocks.searchLots")} />
          <div className="list-toolbar-end">
            <QuickForm
              title={t("m5e.lot.nouveau")}
              endpoint="/api/stocks/lots/"
              fields={[
                { name: "article", label: t("stocks.col.article"), type: "select", required: true, options: articleOptions },
                { name: "numero_lot", label: t("m5e.lot.numero"), required: true },
                { name: "numero_coulee", label: t("m5e.lot.coulee") },
                { name: "date_reception", label: t("m5e.lot.reception"), type: "date", required: true },
                { name: "date_peremption", label: t("m5e.lot.peremption"), type: "date" },
                { name: "quantite_initiale", label: t("m5e.lot.quantite"), type: "number", required: true, min: 0, step: "0.001" },
              ]}
            />
          </div>
        </div>
        <Board label={t("listes.boardLabel.stocks")}>
          {BOARD_ORDER.map((st, ci) => (
            <BoardColumn key={st} limit={20} title={t(`stocks.lot_status.${st}`)} count={groups[st].length} tone={STATUS_BADGE[st]} delay={ci * 0.04}>
              {groups[st].map((lot, i) => (
                <LotCard key={lot.id} lot={lot} index={i} />
              ))}
            </BoardColumn>
          ))}
        </Board>
      </section>

      {(valAll.length > 0 || quantsAll.length > 0) && (
        <SectionCard
          title={t("listes.stocks.stockParDepot")}
          actions={
            <QuickForm
              title={t("m5e.depot.nouveau")}
              endpoint="/api/stocks/depots/"
              transform={(v) => ({ ...v, is_global_rental: v.is_global_rental === "true" })}
              fields={[
                { name: "label", label: t("m5e.depot.label"), required: true },
                { name: "site", label: t("m5e.depot.site") },
                { name: "site_etsl", label: t("ecarts_a5.site"), type: "select", options: siteOpts },
                {
                  name: "methode_valorisation",
                  label: t("m5e.depot.methode"),
                  type: "select",
                  options: ["fifo", "cump", "pp"].map((m) => ({ value: m, label: t(`m5e.depot.methodes.${m}`) })),
                },
                {
                  name: "is_global_rental",
                  label: t("m5e.depot.gr"),
                  type: "select",
                  required: true,
                  defaultValue: "false",
                  options: [
                    { value: "false", label: t("m5e.non") },
                    { value: "true", label: t("m5e.oui") },
                  ],
                },
              ]}
            />
          }
        >
          {valAll.length > 0 ? (
            <DataGrid rows={valAll} columns={valoColumns} caption={t("stocks.quants")} density="compact" />
          ) : (
            <DataGrid rows={quantsAll} columns={quantColumns} caption={t("stocks.quants")} density="compact" />
          )}
        </SectionCard>
      )}

      {(mouvements.count > 0 || mouvements.search) && (
        <SectionCard title={`${t("stocks.mouvements")} · ${mouvements.count}`}>
          <PagedDataGrid list={mouvements} columns={mvtColumns} caption={t("stocks.mouvements")} searchPlaceholder={t("stocks.searchMouvements")} />
        </SectionCard>
      )}

      <AuditValorisationSection depots={depots.data ?? []} articles={articles.data ?? []} />
      <AlertesStockSection />
      <TracabiliteSection lots={allLots} />
      <ConfigArticlesSection articles={articles.data ?? []} />
      <ParametresStockSection />
      <ReservationsStockSection />
      <InventaireAnnuelSection />

      <SectionCard
        title={`${t("stocks.certificats")} · ${certificats.count}`}
        actions={
          <QuickForm
            title={t("m5e.cert.nouveau")}
            endpoint="/api/stocks/certificats/"
            fields={[
              { name: "lot", label: t("stocks.col.lot"), type: "select", required: true, options: lotOptions },
              {
                name: "type",
                label: t("stocks.col.type"),
                type: "select",
                required: true,
                defaultValue: "mtc",
                options: [
                  { value: "mtc", label: t("stocks.mtc") },
                  { value: "coc", label: t("stocks.coc") },
                ],
              },
              { name: "numero_certificat", label: t("stocks.col.certNo"), required: true },
              { name: "organisme", label: t("stocks.col.organisme") },
              { name: "date_emission", label: t("m5e.cert.emission"), type: "date" },
            ]}
          />
        }
      >
        <PagedDataGrid list={certificats} columns={certColumns} caption={t("stocks.certificats")} />
      </SectionCard>

      {(inventaires.count > 0 || inventaires.search) && (
        <SectionCard title={t("stocks.inventaires")}>
          <PagedDataGrid list={inventaires} columns={invColumns} caption={t("stocks.inventaires")} searchPlaceholder={t("stocks.searchInventaires")} />
        </SectionCard>
      )}

      <SectionCard
        title={t("stocks.valoMensuelle")}
        actions={
          <ActionBar
            actions={[{ label: t("stocks.figer"), path: "/api/stocks/valorisations/figer/", tone: "ghost", confirm: t("stocks.figerConfirm"), prompt: { name: "periode", label: t("stocks.figerPrompt") } }]}
          />
        }
      >
        <DataTable rows={valoMensuelles.data ?? []} columns={valoMensColumns} caption={t("stocks.valoMensuelle")} density="compact" />
      </SectionCard>

      {(plans.data ?? []).length > 0 && (
        <SectionCard title={t("stocks.plansTournants")}>
          <DataTable rows={plans.data ?? []} columns={planColumns} caption={t("stocks.plansTournants")} density="compact" />
        </SectionCard>
      )}
    </div>
  );
}
