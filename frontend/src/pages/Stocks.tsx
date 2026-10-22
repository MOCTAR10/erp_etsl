import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { ArrowLeftRight, Boxes, Package, Warehouse } from "lucide-react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { formatDate, formatNumber } from "../lib/format";
import { pagedQuery, usePagedList } from "../lib/usePagedList";
import { ActionBar, Badge, Board, BoardCard, BoardColumn, BoardSkeleton, ErrorState, Kpi, PageHeader, Pagination, QuickForm, SearchField, SectionCard } from "../components/ui";
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
const BOARD_ORDER: LotStatut[] = ["disponible", "partiel", "epuise", "bloque"];

function LotCard({ lot, index }: { lot: LotMatiere; index: number }) {
  const { t } = useTranslation();
  return (
    <BoardCard delay={Math.min(index * 0.03, 0.3)}>
      <div className="title">
        {lot.code} <span className="muted">· {lot.article_code}</span>
      </div>
      <div className="meta">{lot.article_label}</div>
      <div className="meta" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span className={`badge ${STATUS_BADGE[lot.statut] ?? "brand"}`}>
          {t(`stocks.lot_status.${lot.statut}`)}
        </span>
        <span>
          {t("stocks.restant")}: {formatNumber(Number(lot.quantite_restante))} /{" "}
          {formatNumber(Number(lot.quantite_initiale))}
        </span>
      </div>
      <div className="meta muted">
        {t("stocks.lot")} {lot.numero_lot} · {formatDate(lot.date_reception)}
        {lot.numero_coulee ? ` · ${t("m5e.lot.coulee")} ${lot.numero_coulee}` : ""}
        {lot.certificats.length > 0 ? ` · ${t("stocks.mtc")}` : ""}
      </div>
      {lot.statut === "bloque" && lot.motif_blocage && (
        <div className="meta" role="note">{t("m5e.lot.quarantaine")} : {lot.motif_blocage}{lot.nc_blocage_code ? ` (${lot.nc_blocage_code})` : ""}</div>
      )}
      <ActionBar actions={lotActions(lot, t)} />
    </BoardCard>
  );
}

function QuantCard({ quant, index }: { quant: StockQuant; index: number }) {
  const { t } = useTranslation();
  const masked = quant.stock_value === null;
  return (
    <Kpi
      label={`${quant.article_code} · ${quant.depot_code}${quant.lot_code ? ` · ${quant.lot_code}` : ""}`}
      value={formatNumber(Number(quant.quantity))}
      hint={
        masked && !quant.has_amount_access
          ? t("stocks.demi")
          : `${formatNumber(Number(quant.stock_value))} FCFA · ${t("stocks.stockValue")}`
      }
      icon={Boxes}
      tone="brand"
      delay={index * 0.05}
    />
  );
}

export function StocksPage() {
  const { t, i18n } = useTranslation();

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
  const quantsAll = quants.data ?? [];
  const valAll: ValorisationRow[] = valorisation.data ?? [];
  const hasAmount = valAll.length > 0 && valorisation.data !== undefined;
  const totalValue = hasAmount ? valAll.reduce((s, r) => s + (r.value ?? 0), 0) : null;

  return (
    <>
      <PageHeader title={t("stocks.title")} />
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
          {
            name: "article",
            label: t("stocks.col.article"),
            type: "select",
            required: true,
            options: (articles.data ?? []).map((a) => ({ value: a.id, label: `${a.code} · ${a.label}` })),
          },
          { name: "quantite", label: t("stocks.col.qty"), type: "number", required: true, min: 0, step: "0.001" },
          { name: "prix_unitaire", label: t("stocks.col.unitCost"), type: "number", min: 0, step: "0.01" },
          {
            name: "source",
            label: t("stocks.form.source"),
            type: "select",
            options: (depots.data ?? []).map((d) => ({ value: d.id, label: `${d.code} · ${d.label}` })),
          },
          {
            name: "destination",
            label: t("stocks.form.destination"),
            type: "select",
            options: (depots.data ?? []).map((d) => ({ value: d.id, label: `${d.code} · ${d.label}` })),
          },
          {
            name: "ordre",
            label: t("m5e.mvt.ordre"),
            type: "select",
            options: (ordres.data ?? []).map((o) => ({ value: o.id, label: `${o.code} · ${o.label}` })),
          },
          {
            name: "lot",
            label: t("stocks.col.lot"),
            type: "select",
            options: Object.values(groups)
              .flat()
              .map((l) => ({ value: l.id, label: `${l.code} · ${l.numero_lot}` })),
          },
          { name: "document_reference", label: t("stocks.form.reference") },
        ]}
      />

      <div className="kpi-grid">
        <Kpi
          label={t("stocks.valeurStock")}
          value={totalValue === null ? t("stocks.demi") : `${formatNumber(totalValue)} FCFA`}
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
        <Kpi
          label={t("stocks.totalLots")}
          value={Object.values(groups).reduce((s, arr) => s + arr.length, 0)}
          hint={`${t("stocks.perf")} · ${certificats.count}`}
          icon={Package}
          tone="brand"
          delay={0.1}
        />
        <Kpi
          label={t("stocks.totalMvt")}
          value={mouvements.count}
          hint={`${t("stocks.inventaires")} · ${inventaires.count}`}
          icon={ArrowLeftRight}
          tone="warn"
          delay={0.15}
        />
      </div>

      <SearchField value={lotSearch} onChange={setLotSearch} placeholder={t("stocks.searchLots")} />

      <div style={{ overflowX: "auto" }}>
        <Board>
          {BOARD_ORDER.map((st, ci) => (
            <BoardColumn
              limit={20}
              key={st}
              title={t(`stocks.lot_status.${st}`)}
              count={groups[st].length}
              tone={STATUS_BADGE[st]}
              delay={ci * 0.05}
              minWidth={260}
            >
              {groups[st].length === 0 ? (
                <p className="muted" style={{ padding: "0.5rem 0.25rem" }}>
                  {t("common.empty")}
                </p>
              ) : (
                groups[st].map((lot, i) => <LotCard key={lot.id} lot={lot} index={i} />)
              )}
            </BoardColumn>
          ))}
        </Board>
      </div>

      {valAll.length > 0 && (
        <SectionCard title={t("stocks.quants")}>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>{t("stocks.col.article")}</th>
                  <th>{t("stocks.col.depot")}</th>
                  <th>{t("stocks.col.method")}</th>
                  <th className="num">{t("stocks.col.qty")}</th>
                  <th className="num">{t("stocks.col.unitCost")}</th>
                  <th className="num">{t("stocks.col.value")}</th>
                </tr>
              </thead>
              <tbody>
                {valAll.map((row, i) => (
                  <tr key={`${row.depot}-${row.article}-${i}`}>
                    <td>{row.article}</td>
                    <td>{row.depot}</td>
                    <td>{t(`stocks.methods.${row.method}`)}</td>
                    <td className="num">{formatNumber(row.quantity)}</td>
                    <td className="num">{row.value === undefined ? "—" : formatNumber(row.unit_cost)}</td>
                    <td className="num">{row.value === undefined ? t("stocks.demi") : `${formatNumber(row.value)} FCFA`}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SectionCard>
      )}
      {valAll.length === 0 && quantsAll.length > 0 && (
        <SectionCard title={t("stocks.quants")}>
          <div className="kpi-grid">
            {quantsAll.map((q, i) => (
              <QuantCard key={q.id} quant={q} index={i} />
            ))}
          </div>
        </SectionCard>
      )}

      {(mouvements.count > 0 || mouvements.search) && (
        <SectionCard title={t("stocks.mouvements")}>
          <SearchField value={mouvements.search} onChange={mouvements.setSearch} placeholder={t("stocks.searchMouvements")} />
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>{t("stocks.col.code")}</th>
                  <th>{t("stocks.col.type")}</th>
                  <th>{t("stocks.col.article")}</th>
                  <th className="num">{t("stocks.col.qty")}</th>
                  <th>{t("stocks.col.flow")}</th>
                  <th>{t("stocks.col.date")}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {mouvements.rows.map((mvt) => (
                  <tr key={mvt.id}>
                    <td>{mvt.code}</td>
                    <td>{t(`stocks.type_labels.${mvt.type_mouvement}`)}</td>
                    <td>{mvt.article_code}</td>
                    <td className="num">{mvt.quantite}</td>
                    <td>
                      {mvt.source_code ?? t("stocks.reserved")} → {mvt.destination_code ?? "—"}
                      {mvt.ordre_code ? ` · ${mvt.ordre_code}` : ""}
                    </td>
                    <td>{formatDate(mvt.date, i18n.language)}</td>
                    <td>
                      {(mvt.type_mouvement === "consommation" || mvt.type_mouvement === "transfert") && (
                        <button type="button" className="btn ghost" onClick={() => void api.download(`/api/stocks/mouvements/${mvt.id}/bon-de-sortie/`, `BS-${mvt.code}.pdf`)}>
                          {t("m5e.mvt.bonSortie")}
                        </button>
                      )}
                      {mvt.document_titre && <span className="muted"> · {mvt.document_titre}</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination
            page={mouvements.page}
            pageSize={mouvements.pageSize}
            count={mouvements.count}
            onPageChange={mouvements.setPage}
            onPageSizeChange={mouvements.setPageSize}
          />
        </SectionCard>
      )}

      <QuickForm
        title={t("m5e.lot.nouveau")}
        endpoint="/api/stocks/lots/"
        fields={[
          {
            name: "article", label: t("stocks.col.article"), type: "select", required: true,
            options: (articles.data ?? []).map((a) => ({ value: a.id, label: `${a.code} · ${a.label}` })),
          },
          { name: "numero_lot", label: t("m5e.lot.numero"), required: true },
          { name: "numero_coulee", label: t("m5e.lot.coulee") },
          { name: "date_reception", label: t("m5e.lot.reception"), type: "date", required: true },
          { name: "date_peremption", label: t("m5e.lot.peremption"), type: "date" },
          { name: "quantite_initiale", label: t("m5e.lot.quantite"), type: "number", required: true, min: 0, step: "0.001" },
        ]}
      />
      <QuickForm
        title={t("m5e.cert.nouveau")}
        endpoint="/api/stocks/certificats/"
        fields={[
          {
            name: "lot", label: t("stocks.col.lot"), type: "select", required: true,
            options: Object.values(groups).flat().map((l) => ({ value: l.id, label: `${l.code} · ${l.numero_lot}` })),
          },
          { name: "type", label: t("stocks.col.type"), type: "select", required: true, defaultValue: "mtc", options: [{ value: "mtc", label: t("stocks.mtc") }, { value: "coc", label: t("stocks.coc") }] },
          { name: "numero_certificat", label: t("stocks.col.certNo"), required: true },
          { name: "organisme", label: t("stocks.col.organisme") },
          { name: "date_emission", label: t("m5e.cert.emission"), type: "date" },
        ]}
      />
      <QuickForm
        title={t("m5e.depot.nouveau")}
        endpoint="/api/stocks/depots/"
        transform={(v) => ({ ...v, is_global_rental: v.is_global_rental === "true" })}
        fields={[
          { name: "label", label: t("m5e.depot.label"), required: true },
          { name: "site", label: t("m5e.depot.site") },
          {
            name: "methode_valorisation", label: t("m5e.depot.methode"), type: "select",
            options: ["fifo", "cump", "pp"].map((m) => ({ value: m, label: t(`m5e.depot.methodes.${m}`) })),
          },
          {
            name: "is_global_rental", label: t("m5e.depot.gr"), type: "select", required: true, defaultValue: "false",
            options: [{ value: "false", label: t("m5e.non") }, { value: "true", label: t("m5e.oui") }],
          },
        ]}
      />
      <AuditValorisationSection depots={depots.data ?? []} articles={articles.data ?? []} />
      <AlertesStockSection />
      <TracabiliteSection lots={Object.values(groups).flat()} />
      <ConfigArticlesSection articles={articles.data ?? []} />
      <ParametresStockSection />
      <ReservationsStockSection />
      <InventaireAnnuelSection />

      {certificats.count > 0 && (
        <SectionCard title={t("stocks.certificats")}>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>{t("stocks.col.code")}</th>
                  <th>{t("stocks.col.type")}</th>
                  <th>{t("stocks.col.certNo")}</th>
                  <th>{t("stocks.col.lot")}</th>
                  <th>{t("stocks.col.organisme")}</th>
                  <th>{t("stocks.col.status")}</th>
                  <th>{t("m5e.cert.validation")}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {certificats.rows.map((cert) => (
                  <tr key={cert.id}>
                    <td>{cert.code}</td>
                    <td>{cert.type === "mtc" ? t("stocks.mtc") : t("stocks.coc")}</td>
                    <td>{cert.numero_certificat}</td>
                    <td>{cert.lot_code}</td>
                    <td>{cert.organisme || "—"}</td>
                    <td>
                      <Badge tone={cert.conforme ? "ok" : "err"}>
                        {cert.conforme ? t("stocks.certConforme") : t("stocks.certNonConforme")}
                      </Badge>
                    </td>
                    <td>
                      {cert.date_validation
                        ? `${formatDate(cert.date_validation)}${cert.valide_par_name ? ` · ${cert.valide_par_name}` : ""}`
                        : <Badge tone="warn">{t("m5e.cert.aValider")}</Badge>}
                      {cert.document_titre && <div className="muted">{t("m5e.cert.ged")}</div>}
                    </td>
                    <td><CertificatActions cert={cert} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination
            page={certificats.page}
            pageSize={certificats.pageSize}
            count={certificats.count}
            onPageChange={certificats.setPage}
            onPageSizeChange={certificats.setPageSize}
          />
        </SectionCard>
      )}

      {(inventaires.count > 0 || inventaires.search) && (
        <SectionCard title={t("stocks.inventaires")}>
          <SearchField value={inventaires.search} onChange={inventaires.setSearch} placeholder={t("stocks.searchInventaires")} />
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>{t("stocks.col.code")}</th>
                  <th>{t("stocks.col.depot")}</th>
                  <th>{t("stocks.col.date")}</th>
                  <th>{t("stocks.col.status")}</th>
                  <th className="num">{t("stocks.ecarts")}</th>
                </tr>
              </thead>
              <tbody>
                {inventaires.rows.map((inv) => (
                  <tr key={inv.id}>
                    <td>{inv.code}</td>
                    <td>{inv.depot_label}</td>
                    <td>{formatDate(inv.date, i18n.language)}</td>
                    <td>
                      {t(`stocks.inv_status.${inv.statut}`)}
                      {(inv.statut === "brouillon" || inv.statut === "en_cours") && (
                        <ActionBar
                          actions={[{ label: t("actions.cloturer"), path: `/api/stocks/inventaires/${inv.id}/cloturer/`, confirm: t("stocks.form.confirmCloture") }]}
                        />
                      )}
                    </td>
                    <td className="num">{formatNumber(Number(inv.ecart_total))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination
            page={inventaires.page}
            pageSize={inventaires.pageSize}
            count={inventaires.count}
            onPageChange={inventaires.setPage}
            onPageSizeChange={inventaires.setPageSize}
          />
        </SectionCard>
      )}

      <SectionCard title={t("stocks.valoMensuelle")}>
        <ActionBar
          actions={[{ label: t("stocks.figer"), path: "/api/stocks/valorisations/figer/", confirm: t("stocks.figerConfirm"), prompt: { name: "periode", label: t("stocks.figerPrompt") } }]}
        />
        {(valoMensuelles.data ?? []).length > 0 && (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>{t("stocks.periode")}</th>
                  <th>{t("stocks.col.depot")}</th>
                  <th className="num">{t("stocks.col.value")}</th>
                  <th className="num">{t("stocks.consoMois")}</th>
                  <th>{t("m5e.valo.ecriture")}</th>
                </tr>
              </thead>
              <tbody>
                {(valoMensuelles.data ?? []).map((v) => (
                  <tr key={v.id}>
                    <td>{v.periode}</td>
                    <td>{v.depot_code}</td>
                    <td className="num">{v.valeur_stock === null ? t("stocks.demi") : `${formatNumber(Number(v.valeur_stock))} FCFA`}</td>
                    <td className="num">{v.consommation === null ? t("stocks.demi") : `${formatNumber(Number(v.consommation))} FCFA`}</td>
                    <td>{v.move_number ? <Badge tone="ok">{v.move_number}</Badge> : <span className="muted">{v.motif_ecriture || "—"}</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>

      {(plans.data ?? []).length > 0 && (
        <SectionCard title={t("stocks.plansTournants")}>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>{t("stocks.col.code")}</th>
                  <th>{t("stocks.col.depot")}</th>
                  <th className="num">{t("stocks.periodicite")}</th>
                  <th className="num">{t("stocks.parPassage")}</th>
                  <th>{t("stocks.prochainPassage")}</th>
                </tr>
              </thead>
              <tbody>
                {(plans.data ?? []).map((plan) => (
                  <tr key={plan.id}>
                    <td>{plan.code}</td>
                    <td>{plan.depot_label}</td>
                    <td className="num">{plan.periodicite_jours}</td>
                    <td className="num">{plan.articles_par_passage}</td>
                    <td>
                      {formatDate(plan.prochaine_date, i18n.language)}
                      <ActionBar actions={[{ label: t("stocks.generer"), path: `/api/stocks/plans-inventaire/${plan.id}/generer/` }]} />
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