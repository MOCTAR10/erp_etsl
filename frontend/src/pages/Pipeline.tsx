import { useQuery } from "@tanstack/react-query";
import { AnimatePresence } from "motion/react";
import { Layers, Target, TrendingUp } from "lucide-react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { formatNumber } from "../lib/format";
import { Board, BoardCard, BoardColumn, BoardSkeleton, ErrorState, Kpi, PageHeader } from "../components/ui";
import type { Opportunity, OpportunityStage, Paginated } from "../types";

const COLUMNS: Array<{ stage: OpportunityStage; badge: "brand" | "warn" | "ok" | "err" }> = [
  { stage: "prospection", badge: "brand" },
  { stage: "qualification", badge: "brand" },
  { stage: "offre", badge: "warn" },
  { stage: "negociation", badge: "warn" },
  { stage: "gagne", badge: "ok" },
  { stage: "perdu", badge: "err" },
];

function groupByStage(pages: Paginated<Opportunity>[]): Record<OpportunityStage, Opportunity[]> {
  const groups: Record<OpportunityStage, Opportunity[]> = {
    prospection: [],
    qualification: [],
    offre: [],
    negociation: [],
    gagne: [],
    perdu: [],
  };
  for (const page of pages) for (const opp of page.results) groups[opp.stage].push(opp);
  return groups;
}

function OppCard({ opp, index }: { opp: Opportunity; index: number }) {
  const { t, i18n } = useTranslation();
  return (
    <BoardCard delay={Math.min(index * 0.03, 0.3)}>
      <div className="title">
        <span className="muted">{opp.code}</span> · {opp.subject}
      </div>
      <div className="meta">
        {opp.client_name ?? "—"} {opp.expected_close ? `· éch. ${new Date(opp.expected_close).toLocaleDateString(i18n.language)}` : ""}
      </div>
      <div className="meta" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span className="badge brand">{opp.probability}%</span>
        <span>{opp.amount === null ? t("pipeline.masked") : formatNumber(opp.amount)}</span>
      </div>
    </BoardCard>
  );
}

export function PipelinePage() {
  const { t } = useTranslation();
  const pages = useQuery({
    queryKey: ["opportunities"],
    queryFn: () => api.opportunities(),
    select: (page) => [page],
  });
  const stats = useQuery({ queryKey: ["pipeline"], queryFn: api.pipeline });

  const data = pages.data;

  if (pages.isLoading) return <BoardSkeleton cols={6} rows={3} />;
  if (pages.isError || !data)
    return <ErrorState message={t("common.error")} onRetry={() => void pages.refetch()} retryLabel={t("common.retry")} />;

  const groups = groupByStage(data);
  const s = stats.data;

  return (
    <>
      <PageHeader title={t("pipeline.title")} />

      {s ? (
        <div className="kpi-grid">
          <Kpi label={t("pipeline.wonTotal")} value={s.won_total} icon={TrendingUp} tone="ok" delay={0} />
          <Kpi label={t("pipeline.conversion")} value={`${(s.conversion_rate * 100).toFixed(1)}%`} icon={Target} tone="accent" delay={0.05} />
          <Kpi label={t("pipeline.activeSegments")} value={Object.keys(s.margin_by_segment).length} icon={Layers} tone="brand" delay={0.1} />
        </div>
      ) : null}

      <div style={{ overflowX: "auto" }}>
        <Board>
          {COLUMNS.map((col, ci) => (
            <BoardColumn
              key={col.stage}
              title={t(`pipeline.${col.stage}`)}
              count={groups[col.stage].length}
              tone={col.badge}
              delay={ci * 0.05}
              minWidth={240}
            >
              <AnimatePresence initial={false}>
                {groups[col.stage].map((opp, i) => (
                  <OppCard key={opp.id} opp={opp} index={i} />
                ))}
              </AnimatePresence>
            </BoardColumn>
          ))}
        </Board>
      </div>
    </>
  );
}