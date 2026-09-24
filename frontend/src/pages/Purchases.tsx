import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, ShoppingCart, Truck } from "lucide-react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { formatDate, formatNumber } from "../lib/format";
import { Board, BoardCard, BoardColumn, BoardSkeleton, ErrorState, Kpi, PageHeader } from "../components/ui";
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

function OrderCard({ order, index }: { order: PurchaseOrder; index: number }) {
  const { t } = useTranslation();
  return (
    <BoardCard delay={Math.min(index * 0.03, 0.3)}>
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
    </BoardCard>
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
  if (byStatus.isLoading) return <BoardSkeleton cols={4} rows={3} />;
  if (byStatus.isError || !data)
    return <ErrorState message={t("common.error")} onRetry={() => void byStatus.refetch()} retryLabel={t("common.retry")} />;

  const groups = data.groups;
  const total = (Object.values(groups) as PurchaseOrder[][]).reduce((a, l) => a + l.length, 0);

  return (
    <>
      <PageHeader title={t("purchases.title")} />

      <div className="kpi-grid">
        <Kpi label={t("purchases.orders")} value={total} icon={ShoppingCart} tone="brand" delay={0} />
        <Kpi label={t("purchases.confirmed")} value={groups.confirmee.length + groups.partielle.length + groups.cloturee.length} icon={CheckCircle2} tone="ok" delay={0.05} />
        <Kpi label={t("purchases.gr")} value={data.grCount} icon={Truck} tone="warn" delay={0.1} />
      </div>

      <div style={{ overflowX: "auto" }}>
        <Board>
          {(["confirmee", "partielle", "cloturee", "brouillon"] as PoStatus[]).map((st, ci) => (
            <BoardColumn
              key={st}
              title={t(`purchases.${st}`)}
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
                groups[st].map((o, i) => <OrderCard key={o.id} order={o} index={i} />)
              )}
            </BoardColumn>
          ))}
        </Board>
      </div>
    </>
  );
}