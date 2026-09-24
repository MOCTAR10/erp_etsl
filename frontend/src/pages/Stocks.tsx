import { useQuery } from "@tanstack/react-query";
import { ArrowLeftRight, Boxes, Package, Warehouse } from "lucide-react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { formatDate, formatNumber } from "../lib/format";
import { Board, BoardCard, BoardColumn, BoardSkeleton, ErrorState, Kpi, PageHeader } from "../components/ui";
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
        {t("stocks.lot")} {lot.numero_lot} · {formatDate(lot.date_reception, "fr")}
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

function MvtCard({ mvt, index }: { mvt: MouvementStock; index: number }) {
  const { t } = useTranslation();
  return (
    <Kpi
      label={`${mvt.code} · ${t(`stocks.type_labels.${mvt.type_mouvement}`)}`}
      value={`${mvt.quantite} ${mvt.article_code}`}
      hint={`${mvt.source_code ?? t("stocks.reserved")} → ${mvt.destination_code ?? "—"}${
        mvt.ordre_code ? ` · ${mvt.ordre_code}` : ""
      }${mvt.document_reference ? ` · ${mvt.document_reference}` : ""} · ${formatDate(mvt.date, "fr")}`}
      icon={ArrowLeftRight}
      tone="warn"
      delay={index * 0.05}
    />
  );
}

function CertCard({ cert, index }: { cert: CertificatMatiere; index: number }) {
  const { t } = useTranslation();
  return (
    <Kpi
      label={`${cert.code} · ${cert.type === "mtc" ? t("stocks.mtc") : t("stocks.coc")}`}
      value={cert.numero_certificat}
      hint={
        <>
          {cert.lot_code} · {cert.organisme || "—"}
          {cert.conforme ? (
            <span className="badge ok"> {t("stocks.certConforme")}</span>
          ) : (
            <span className="badge err"> {t("stocks.certNonConforme")}</span>
          )}
        </>
      }
      icon={Package}
      tone="brand"
      delay={index * 0.05}
    />
  );
}

export function StocksPage() {
  const { t } = useTranslation();

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

      {quantsAll.length > 0 || (valAll.length > 0 && valorisation.isSuccess) ? (
        <>
          <h3 className="muted" style={{ marginTop: "2rem" }}>
            {t("stocks.quants")}
          </h3>
          <div className="kpi-grid">
            {valAll.map((row, i) => (
              <Kpi
                key={`${row.depot}-${row.article}-${i}`}
                label={`${row.article} · ${row.depot} · ${t(`stocks.methods.${row.method}`)}`}
                value={formatNumber(row.quantity)}
                hint={
                  row.value === undefined
                    ? t("stocks.demi")
                    : `${formatNumber(row.value)} FCFA · ${formatNumber(row.unit_cost)} u.`
                }
                icon={Boxes}
                tone="brand"
                delay={i * 0.05}
              />
            ))}
            {valAll.length === 0
              ? quantsAll.map((q, i) => <QuantCard key={q.id} quant={q} index={i} />)
              : null}
          </div>
        </>
      ) : null}

      {(mouvements.data ?? []).length > 0 ? (
        <>
          <h3 className="muted" style={{ marginTop: "2rem" }}>
            {t("stocks.mouvements")}
          </h3>
          <div className="kpi-grid">
            {(mouvements.data ?? []).map((mvt, i) => (
              <MvtCard key={mvt.id} mvt={mvt} index={i} />
            ))}
          </div>
        </>
      ) : null}

      {(certificats.data ?? []).length > 0 ? (
        <>
          <h3 className="muted" style={{ marginTop: "2rem" }}>
            {t("stocks.certificats")}
          </h3>
          <div className="kpi-grid">
            {(certificats.data ?? []).map((cert, i) => (
              <CertCard key={cert.id} cert={cert} index={i} />
            ))}
          </div>
        </>
      ) : null}

      {(inventaires.data ?? []).length > 0 ? (
        <>
          <h3 className="muted" style={{ marginTop: "2rem" }}>
            {t("stocks.inventaires")}
          </h3>
          <div className="kpi-grid">
            {(inventaires.data ?? []).map((inv, i) => (
              <Kpi
                key={inv.id}
                label={`${inv.code} · ${inv.depot_label} · ${t(`stocks.inv_status.${inv.statut}`)}`}
                value={formatDate(inv.date, "fr")}
                hint={`${t("stocks.ecarts")}: ${formatNumber(Number(inv.ecart_total))}`}
                icon={Warehouse}
                tone="accent"
                delay={i * 0.05}
              />
            ))}
          </div>
        </>
      ) : null}
    </>
  );
}