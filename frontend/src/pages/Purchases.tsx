import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { CheckCircle2, ShoppingCart, Truck } from "lucide-react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { formatDate, formatMoney } from "../lib/format";
import { pagedQuery } from "../lib/usePagedList";
import { Badge, Board, BoardCard, BoardColumn, BoardSkeleton, ErrorState, Kpi, PageHeader, SearchField, SectionNav } from "../components/ui";
import type { Paginated, PoStatus, PurchaseOrder } from "../types";
import { DemandesAchat } from "../components/workflow/DemandesAchat";
import { AchatsPilotage } from "../components/achats/AchatsPilotage";
import { AchatsSaisie } from "../components/achats/AchatsSaisie";
import { EcartsM2Section } from "../components/achats/EcartsM2Section";

type Groups = Record<PoStatus, PurchaseOrder[]>;

const STATUS_TONE: Record<PoStatus, "ok" | "warn" | "err" | "brand"> = {
  brouillon: "brand",
  confirmee: "warn",
  partielle: "warn",
  cloturee: "ok",
  annulee: "err",
  previ: "brand",
};
const VALID_STATUSES = new Set<PoStatus>(["brouillon", "confirmee", "partielle", "cloturee", "annulee"]);
const BOARD_ORDER: PoStatus[] = ["brouillon", "confirmee", "partielle", "cloturee"];

/** Somme des montants visibles d'une colonne (« — » si tous masqués). */
function columnTotal(orders: PurchaseOrder[]): number | null {
  const visible = orders.filter((o) => o.total !== null);
  return visible.length ? visible.reduce((s, o) => s + Number(o.total), 0) : null;
}

function OrderCard({ order, index }: { order: PurchaseOrder; index: number }) {
  const { t } = useTranslation();
  // Le statut est porté par la colonne : la carte ne le répète pas (évite les libellés longs qui débordent).
  return (
    <BoardCard delay={Math.min(index * 0.03, 0.3)}>
      <div className="card-top">
        <span className="card-code">{order.code}</span>
        {order.is_global_rental ? (
          <span className="card-tags">
            <Badge tone="brand" title={t("purchases.gr")}>
              GR
            </Badge>
          </span>
        ) : null}
      </div>
      <div className="title">{order.supplier_name ?? "—"}</div>
      <div className="meta">
        {[order.request_code, t("listes.purchases.lignes", { count: order.lines_count })].filter(Boolean).join(" · ")}
      </div>
      <div className="card-foot">
        <span>{order.expected_date ? t("listes.purchases.livraison", { date: formatDate(order.expected_date) }) : null}</span>
        <span className="amount">{order.total === null ? t("purchases.masked") : formatMoney(order.total)}</span>
      </div>
    </BoardCard>
  );
}

export function PurchasesPage() {
  const { t } = useTranslation();
  const [search, setSearch] = useState("");

  // Kanban : jusqu'à 500 BC (plafond serveur) filtrés par la recherche ; « Voir plus » par colonne.
  const byStatus = useQuery({
    queryKey: ["purchase-orders", search],
    queryFn: () => api.purchaseOrders(pagedQuery(1, 500, search)),
    placeholderData: keepPreviousData,
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
      return { groups, count: page.count, grCount: page.results.filter((o) => o.is_global_rental).length } as const;
    },
  });

  const data = byStatus.data;
  if (byStatus.isLoading) return <BoardSkeleton cols={4} rows={3} />;
  if (byStatus.isError || !data)
    return <ErrorState message={t("common.error")} onRetry={() => void byStatus.refetch()} retryLabel={t("common.retry")} />;

  const groups = data.groups;
  const total = data.count;

  return (
    <div className="listes-page">
      <PageHeader title={t("purchases.title")} subtitle={t("listes.sub.purchases")} />
      <SectionNav
        items={[
          { id: "ach-commandes", label: t("premiumVague2.sections.purchases.commandes") },
          { id: "ach-demandes", label: t("premiumVague2.sections.purchases.demandes") },
          { id: "ach-consultations", label: t("premiumVague2.sections.purchases.consultations") },
          { id: "ach-receptions", label: t("premiumVague2.sections.purchases.receptions") },
          { id: "ach-fournisseurs", label: t("premiumVague2.sections.purchases.fournisseurs") },
          { id: "ach-parametres", label: t("premiumVague2.sections.purchases.parametres") },
        ]}
      />

      <div className="kpi-grid">
        <Kpi label={t("purchases.orders")} value={total} icon={ShoppingCart} tone="brand" delay={0} />
        {/* « Actives » = confirmées ou partiellement reçues (les commandes clôturées n'en font plus partie). */}
        <Kpi label={t("purchases.confirmed")} value={groups.confirmee.length + groups.partielle.length} icon={CheckCircle2} tone="ok" delay={0.05} />
        {/* GLOBAL RENTAL : métrique neutre (pas une alerte) → ton acier. */}
        <Kpi label={t("purchases.gr")} value={data.grCount} icon={Truck} tone="accent" delay={0.1} />
      </div>

      <section id="ach-commandes" className="listes-block">
        <div className="list-toolbar">
          <SearchField value={search} onChange={setSearch} placeholder={t("purchases.search")} />
        </div>
        <Board label={t("listes.boardLabel.purchases")}>
          {BOARD_ORDER.map((st, ci) => {
            const sum = columnTotal(groups[st]);
            return (
              <BoardColumn
                key={st}
                title={t(`purchases.${st}`)}
                count={groups[st].length}
                tone={STATUS_TONE[st]}
                delay={ci * 0.04}
                limit={20}
                summary={groups[st].length && sum !== null ? formatMoney(sum) : undefined}
              >
                {groups[st].map((o, i) => (
                  <OrderCard key={o.id} order={o} index={i} />
                ))}
              </BoardColumn>
            );
          })}
        </Board>
      </section>

      <div id="ach-demandes" className="page-section">
        <DemandesAchat />
      </div>

      <div id="ach-consultations" className="page-section">
        <AchatsSaisie />
      </div>

      <div id="ach-receptions" className="page-section">
        <AchatsPilotage />
      </div>

      <EcartsM2Section />
    </div>
  );
}
