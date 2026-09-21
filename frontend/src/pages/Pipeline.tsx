import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "motion/react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { formatNumber } from "../lib/format";
import { motionTokens } from "../theme/tokens";
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

function OppCard({ opp }: { opp: Opportunity }) {
  const { t, i18n } = useTranslation();
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: motionTokens.distance.xs, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, scale: 0.96 }}
      transition={{ duration: motionTokens.duration.base, ease: motionTokens.ease.out }}
      className="task-card"
    >
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
    </motion.div>
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

  if (pages.isLoading) return <p className="muted">{t("common.loading")}</p>;
  if (pages.isError || !data)
    return (
      <p>
        {t("common.error")}{" "}
        <button className="btn ghost" onClick={() => void pages.refetch()}>
          {t("common.retry")}
        </button>
      </p>
    );

  const groups = groupByStage(data);
  const s = stats.data;

  return (
    <>
      <h2>{t("pipeline.title")}</h2>

      {s ? (
        <div className="kpis">
          <div className="card kpi">
            <span className="kpi-label">{t("pipeline.wonTotal")}</span>
            <span className="kpi-value">{formatNumber(s.won_total)}</span>
          </div>
          <div className="card kpi">
            <span className="kpi-label">{t("pipeline.conversion")}</span>
            <span className="kpi-value">{(s.conversion_rate * 100).toFixed(1)}%</span>
          </div>
          <div className="card kpi">
            <span className="kpi-label">{t("pipeline.activeSegments")}</span>
            <span className="kpi-value">{Object.keys(s.margin_by_segment).length}</span>
          </div>
        </div>
      ) : null}

      <div className="board" style={{ overflowX: "auto" }}>
        {COLUMNS.map((col) => (
          <motion.div
            key={col.stage}
            layout
            className="board-col"
            style={{ minWidth: 240 }}
            initial={{ opacity: 0, y: motionTokens.distance.sm }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: motionTokens.duration.base, ease: motionTokens.ease.out }}
          >
            <div className="board-col-head">
              <span>{t(`pipeline.${col.stage}`)}</span>
              <span className={`badge ${col.badge}`}>{groups[col.stage].length}</span>
            </div>
            <AnimatePresence initial={false}>
              {groups[col.stage].map((opp) => (
                <OppCard key={opp.id} opp={opp} />
              ))}
            </AnimatePresence>
          </motion.div>
        ))}
      </div>
    </>
  );
}