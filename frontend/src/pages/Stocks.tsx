import { useQuery } from "@tanstack/react-query";
import { motion } from "motion/react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { formatDate, formatNumber } from "../lib/format";
import { motionTokens } from "../theme/tokens";
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

function LotCard({ lot }: { lot: LotMatiere }) {
  const { t } = useTranslation();
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: motionTokens.distance.xs, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: motionTokens.duration.base, ease: motionTokens.ease.out }}
      className="task-card"
    >
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
    </motion.div>
  );
}

function QuantCard({ quant }: { quant: StockQuant }) {
  const { t } = useTranslation();
  const masked = quant.stock_value === null;
  return (
    <div className="card kpi" key={quant.id}>
      <span className="kpi-label">
        {quant.article_code} · {quant.depot_code}
        {quant.lot_code ? ` · ${quant.lot_code}` : ""}
      </span>
      <span className="kpi-value">{formatNumber(Number(quant.quantity))}</span>
      <span className="meta muted">
        {masked && !quant.has_amount_access
          ? t("stocks.demi")
          : `${formatNumber(Number(quant.stock_value))} FCFA · ${t("stocks.stockValue")}`}
      </span>
    </div>
  );
}

function MvtCard({ mvt }: { mvt: MouvementStock }) {
  const { t } = useTranslation();
  return (
    <div className="card kpi" key={mvt.id}>
      <span className="kpi-label">
        {mvt.code} · {t(`stocks.type_labels.${mvt.type_mouvement}`)}
      </span>
      <span className="kpi-value">
        {mvt.quantite} <span className="muted">{mvt.article_code}</span>
      </span>
      <span className="meta muted">
        {(mvt.source_code ?? t("stocks.reserved"))} → {(mvt.destination_code ?? "—")}
        {mvt.ordre_code ? ` · ${mvt.ordre_code}` : ""}
        {mvt.document_reference ? ` · ${mvt.document_reference}` : ""} ·{" "}
        {formatDate(mvt.date, "fr")}
      </span>
    </div>
  );
}

function CertCard({ cert }: { cert: CertificatMatiere }) {
  const { t } = useTranslation();
  return (
    <div className="card kpi" key={cert.id}>
      <span className="kpi-label">
        {cert.code} · {cert.type === "mtc" ? t("stocks.mtc") : t("stocks.coc")}
      </span>
      <span className="kpi-value">{cert.numero_certificat}</span>
      <span className="meta muted">
        {cert.lot_code} · {cert.organisme || "—"}
        {cert.conforme ? (
          <span className="badge ok"> {t("stocks.certConforme")}</span>
        ) : (
          <span className="badge err"> {t("stocks.certNonConforme")}</span>
        )}
      </span>
    </div>
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

  if (lots.isLoading || quants.isLoading)
    return <p className="muted">{t("common.loading")}</p>;
  if (lots.isError || quants.isError || !lots.data)
    return (
      <p>
        {t("common.error")}{" "}
        <button
          className="btn ghost"
          onClick={() => {
            void lots.refetch();
            void quants.refetch();
            void depots.refetch();
            void mouvements.refetch();
            void valorisation.refetch();
            void certificats.refetch();
            void inventaires.refetch();
          }}
        >
          {t("common.retry")}
        </button>
      </p>
    );

  const groups = lots.data;
  const quantsAll = quants.data ?? [];
  const valAll: ValorisationRow[] = valorisation.data ?? [];
  const hasAmount = valAll.length > 0 && valorisation.data !== undefined;
  const totalValue = hasAmount ? valAll.reduce((s, r) => s + (r.value ?? 0), 0) : null;

  return (
    <>
      <h2>{t("stocks.title")}</h2>

      <div className="kpis">
        <div className="card kpi">
          <span className="kpi-label">{t("stocks.valeurStock")}</span>
          <span className="kpi-value">
            {totalValue === null ? t("stocks.demi") : `${formatNumber(totalValue)} FCFA`}
          </span>
          <span className="meta muted">
            {t("stocks.quants")} · {quantsAll.length}
          </span>
        </div>
        <div className="card kpi">
          <span className="kpi-label">{t("stocks.depots")}</span>
          <span className="kpi-value">{depots.data?.length ?? "—"}</span>
          <span className="meta muted">
            {(depots.data ?? [])
              .map((d) => d.code)
              .slice(0, 3)
              .join(" · ") || "—"}
          </span>
        </div>
        <div className="card kpi">
          <span className="kpi-label">{t("stocks.totalLots")}</span>
          <span className="kpi-value">
            {Object.values(groups).reduce((s, arr) => s + arr.length, 0)}
          </span>
          <span className="meta muted">{t("stocks.perf")} · {certificats.data?.length ?? "—"}</span>
        </div>
        <div className="card kpi">
          <span className="kpi-label">{t("stocks.totalMvt")}</span>
          <span className="kpi-value">{mouvements.data?.length ?? "—"}</span>
          <span className="meta muted">{t("stocks.inventaires")} · {inventaires.data?.length ?? "—"}</span>
        </div>
      </div>

      <div className="board" style={{ overflowX: "auto" }}>
        {BOARD_ORDER.map((st) => (
          <motion.div
            key={st}
            layout
            className="board-col"
            style={{ minWidth: 260 }}
            initial={{ opacity: 0, y: motionTokens.distance.sm }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: motionTokens.duration.base, ease: motionTokens.ease.out }}
          >
            <div className="board-col-head">
              <span>{t(`stocks.lot_status.${st}`)}</span>
              <span className={`badge ${STATUS_BADGE[st]}`}>{groups[st].length}</span>
            </div>
            {groups[st].length === 0 ? (
              <p className="muted" style={{ padding: "0.5rem 0.25rem" }}>
                {t("common.empty")}
              </p>
            ) : (
              groups[st].map((lot) => <LotCard key={lot.id} lot={lot} />)
            )}
          </motion.div>
        ))}
      </div>

      {(quantsAll.length > 0 || (valAll.length > 0 && valorisation.isSuccess)) ? (
        <>
          <h3 className="muted" style={{ marginTop: "2rem" }}>
            {t("stocks.quants")}
          </h3>
          <div className="kpis" style={{ flexWrap: "wrap" }}>
            {valAll.map((row, i) => (
              <div className="card kpi" key={`${row.depot}-${row.article}-${i}`}>
                <span className="kpi-label">
                  {row.article} · {row.depot} · {t(`stocks.methods.${row.method}`)}
                </span>
                <span className="kpi-value">{formatNumber(row.quantity)}</span>
                <span className="meta muted">
                  {row.value === undefined
                    ? t("stocks.demi")
                    : `${formatNumber(row.value)} FCFA · ${formatNumber(row.unit_cost)} u.`}
                </span>
              </div>
            ))}
            {valAll.length === 0
              ? quantsAll.map((q) => <QuantCard key={q.id} quant={q} />)
              : null}
          </div>
        </>
      ) : null}

      {(mouvements.data ?? []).length > 0 ? (
        <>
          <h3 className="muted" style={{ marginTop: "2rem" }}>
            {t("stocks.mouvements")}
          </h3>
          <div className="kpis" style={{ flexWrap: "wrap" }}>
            {(mouvements.data ?? []).map((mvt) => (
              <MvtCard key={mvt.id} mvt={mvt} />
            ))}
          </div>
        </>
      ) : null}

      {(certificats.data ?? []).length > 0 ? (
        <>
          <h3 className="muted" style={{ marginTop: "2rem" }}>
            {t("stocks.certificats")}
          </h3>
          <div className="kpis" style={{ flexWrap: "wrap" }}>
            {(certificats.data ?? []).map((cert) => (
              <CertCard key={cert.id} cert={cert} />
            ))}
          </div>
        </>
      ) : null}

      {(inventaires.data ?? []).length > 0 ? (
        <>
          <h3 className="muted" style={{ marginTop: "2rem" }}>
            {t("stocks.inventaires")}
          </h3>
          <div className="kpis" style={{ flexWrap: "wrap" }}>
            {(inventaires.data ?? []).map((inv) => (
              <div className="card kpi" key={inv.id}>
                <span className="kpi-label">
                  {inv.code} · {inv.depot_label} · {t(`stocks.inv_status.${inv.statut}`)}
                </span>
                <span className="kpi-value">{formatDate(inv.date, "fr")}</span>
                <span className="meta muted">
                  {t("stocks.ecarts")}: {formatNumber(Number(inv.ecart_total))}
                </span>
              </div>
            ))}
          </div>
        </>
      ) : null}
    </>
  );
}