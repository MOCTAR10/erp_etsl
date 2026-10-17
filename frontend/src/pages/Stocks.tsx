import { useQuery } from "@tanstack/react-query";
import { ArrowLeftRight, Boxes, Package, Warehouse } from "lucide-react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { formatDate, formatNumber } from "../lib/format";
import { ActionBar, Badge, Board, BoardCard, BoardColumn, BoardSkeleton, ErrorState, Kpi, PageHeader, QuickForm, SectionCard } from "../components/ui";
import type {
  CertificatMatiere,
  Depot,
  Inventaire,
  LotMatiere,
  LotStatut,
  MouvementStock,
  Paginated,
  StockQuant,
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
        {lot.certificats.length > 0 ? ` · ${t("stocks.mtc")}` : ""}
      </div>
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

  const lots = useQuery({
    queryKey: ["lots"],
    queryFn: () => api.lotsStocks(`?page_size=200`),
    select: (page: Paginated<LotMatiere>) => {
      const groups: Groups = { disponible: [], partiel: [], epuise: [], bloque: [] };
      for (const lot of page.results) {
        if (VALID_STATUSES.has(lot.statut)) groups[lot.statut].push(lot);
      }
      return groups;
    },
  });

  const articles = useQuery({
    queryKey: ["articles-stock"],
    queryFn: () => api.get<Paginated<{ id: string; code: string; label: string }>>("/api/referentiels/articles/?page_size=500"),
    select: (page) => page.results,
  });

  const depots = useQuery({
    queryKey: ["depots"],
    queryFn: () => api.depots(`?active=1&page_size=100`),
    select: (page: Paginated<Depot>) => page.results,
  });

  const quants = useQuery({
    queryKey: ["quants"],
    queryFn: () => api.quantsStock(`?positive=1&page_size=200`),
    select: (page: Paginated<StockQuant>) => page.results,
  });

  const mouvements = useQuery({
    queryKey: ["mouvements-stock"],
    queryFn: () => api.mouvementsStock(`?page_size=12`),
    select: (page: Paginated<MouvementStock>) => page.results,
  });

  const valorisation = useQuery({
    queryKey: ["valorisation"],
    queryFn: () => api.valorisation(),
  });

  const certificats = useQuery({
    queryKey: ["certificats"],
    queryFn: () => api.certificats(`?page_size=30`),
    select: (page: Paginated<CertificatMatiere>) => page.results,
  });

  const inventaires = useQuery({
    queryKey: ["inventaires"],
    queryFn: () => api.inventaires(`?page_size=20`),
    select: (page: Paginated<Inventaire>) => page.results,
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
          void mouvements.refetch();
          void valorisation.refetch();
          void certificats.refetch();
          void inventaires.refetch();
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
          hint={`${t("stocks.perf")} · ${certificats.data?.length ?? "—"}`}
          icon={Package}
          tone="brand"
          delay={0.1}
        />
        <Kpi
          label={t("stocks.totalMvt")}
          value={mouvements.data?.length ?? "—"}
          hint={`${t("stocks.inventaires")} · ${inventaires.data?.length ?? "—"}`}
          icon={ArrowLeftRight}
          tone="warn"
          delay={0.15}
        />
      </div>

      <div style={{ overflowX: "auto" }}>
        <Board>
          {BOARD_ORDER.map((st, ci) => (
            <BoardColumn
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

      {(mouvements.data ?? []).length > 0 && (
        <SectionCard title={t("stocks.mouvements")}>
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
                </tr>
              </thead>
              <tbody>
                {(mouvements.data ?? []).map((mvt) => (
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
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SectionCard>
      )}

      {(certificats.data ?? []).length > 0 && (
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
                </tr>
              </thead>
              <tbody>
                {(certificats.data ?? []).map((cert) => (
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
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SectionCard>
      )}

      {(inventaires.data ?? []).length > 0 && (
        <SectionCard title={t("stocks.inventaires")}>
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
                {(inventaires.data ?? []).map((inv) => (
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
        </SectionCard>
      )}
    </>
  );
}