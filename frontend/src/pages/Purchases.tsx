import { useQuery } from "@tanstack/react-query";
import { motion } from "motion/react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { formatDate, formatNumber } from "../lib/format";
import { motionTokens } from "../theme/tokens";
import type { Paginated, PoStatus, PurchaseOrder } from "../types";

type Groups = Record<PoStatus, PurchaseOrder[]>;

const STATUS_BADGE: Record<PoStatus, "ok" | "warn" | "err" | "brand"> = {
  brouillon: "brand",
  confirmee: "warn",
  partielle: "warn",
  cloturee: "ok",
  annulee: "err",
  previ: "brand",
};
const VALID_STATUSES = new Set<PoStatus>(["brouillon", "confirmee", "partielle", "cloturee", "annulee"]);

function OrderCard({ order }: { order: PurchaseOrder }) {
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
        <span className="muted">{order.code}</span> · {order.supplier_name ?? "—"}
        {order.is_global_rental ? <span className="badge err">GR</span> : null}
      </div>
      <div className="meta">
        {order.request_code ? `${order.request_code} · ` : ""}
        {t("purchases.lines")}: {order.lines_count}
      </div>
      <div className="meta" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span className={`badge ${STATUS_BADGE[order.status] ?? "brand"}`}>{order.status_label}</span>
        <span>{order.total === null ? t("purchases.masked") : formatNumber(order.total)}</span>
      </div>
      {order.expected_date ? (
        <div className="meta muted">
          {t("purchases.expected")} {formatDate(order.expected_date, "fr")}
        </div>
      ) : null}
    </motion.div>
  );
}

export function PurchasesPage() {
  const { t } = useTranslation();

  const byStatus = useQuery({
    queryKey: ["purchase-orders"],
    queryFn: () => api.purchaseOrders(`?page_size=100`),
    select: (page: Paginated<PurchaseOrder>) => {
      const groups: Groups = {
        brouillon: [],
        confirmee: [],
        partielle: [],
        cloturee: [],
        annulee: [],
        previ: [],
      };
      for (const o of page.results) {
        if (VALID_STATUSES.has(o.status)) groups[o.status].push(o);
      }
      return { groups, grCount: page.results.filter((o) => o.is_global_rental).length } as const;
    },
  });

  const data = byStatus.data;
  if (byStatus.isLoading) return <p className="muted">{t("common.loading")}</p>;
  if (byStatus.isError || !data)
    return (
      <p>
        {t("common.error")}{" "}
        <button className="btn ghost" onClick={() => void byStatus.refetch()}>
          {t("common.retry")}
        </button>
      </p>
    );

  const groups = data.groups;
  const total = (Object.values(groups) as PurchaseOrder[][]).reduce((a, l) => a + l.length, 0);

  return (
    <>
      <h2>{t("purchases.title")}</h2>

      <div className="kpis">
        <div className="card kpi">
          <span className="kpi-label">{t("purchases.orders")}</span>
          <span className="kpi-value">{total}</span>
        </div>
        <div className="card kpi">
          <span className="kpi-label">{t("purchases.confirmed")}</span>
          <span className="kpi-value">{groups.confirmee.length + groups.partielle.length + groups.cloturee.length}</span>
        </div>
        <div className="card kpi">
          <span className="kpi-label">{t("purchases.gr")}</span>
          <span className="kpi-value">{data.grCount}</span>
        </div>
      </div>

      <div className="board" style={{ overflowX: "auto" }}>
        {(["confirmee", "partielle", "cloturee", "brouillon"] as PoStatus[]).map((st) => (
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
              <span>{t(`purchases.${st}`)}</span>
              <span className={`badge ${STATUS_BADGE[st]}`}>{groups[st].length}</span>
            </div>
            {groups[st].length === 0 ? (
              <p className="muted" style={{ padding: "0.5rem 0.25rem" }}>
                {t("common.empty")}
              </p>
            ) : (
              groups[st].map((o) => <OrderCard key={o.id} order={o} />)
            )}
          </motion.div>
        ))}
      </div>
    </>
  );
}