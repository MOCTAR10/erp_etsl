import { useQuery } from "@tanstack/react-query";
import { motion } from "motion/react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { formatDate, formatNumber } from "../lib/format";
import { motionTokens } from "../theme/tokens";
import type {
  ChargeStats,
  OfStatus,
  OrdreFabrication,
  Paginated,
  SituationTravaux,
} from "../types";

type Groups = Record<OfStatus, OrdreFabrication[]>;

const STATUS_BADGE: Record<OfStatus, "ok" | "warn" | "err" | "brand"> = {
  prevu: "brand",
  lance: "brand",
  en_cours: "warn",
  termine: "ok",
  cloture: "ok",
  annule: "err",
};
const VALID_STATUSES = new Set<OfStatus>(["prevu", "lance", "en_cours", "termine", "cloture", "annule"]);
const BOARD_ORDER: OfStatus[] = ["en_cours", "lance", "prevu", "termine", "cloture"];

function OfCard({ of }: { of: OrdreFabrication }) {
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
        <span className="muted">{of.code}</span> · {of.label}
      </div>
      <div className="meta">
        {t("operations.scope")}: {of.scope_label}
        {of.affaire_code ? ` · ${of.affaire_code}` : ""}
      </div>
      {of.gamme_code ? (
        <div className="meta muted">
          {t("operations.gamme")}: {of.gamme_code}
        </div>
      ) : null}
      <div className="meta" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span className={`badge ${STATUS_BADGE[of.status] ?? "brand"}`}>{of.status_label}</span>
        <span>
          {formatNumber(Number(of.pointage_hours))}/{formatNumber(Number(of.calculated_hours))} h
        </span>
      </div>
      {of.planned_end ? (
        <div className="meta muted">
          {t("operations.due")} {formatDate(of.planned_end, "fr")}
        </div>
      ) : null}
    </motion.div>
  );
}

function Charge({ stats }: { stats: ChargeStats }) {
  const { t } = useTranslation();
  const scope = (key: "atelier" | "chantier") => (
    <div className="card kpi">
      <span className="kpi-label">{t(`operations.${key}`)}</span>
      <span className="kpi-value">
        {formatNumber(stats.totals[key].calculated)} h {t("operations.planned")}
      </span>
      <span className="meta muted">
        {formatNumber(stats.totals[key].pointed)} h {t("operations.pointed")} · {stats.totals[key].count} OF
      </span>
    </div>
  );
  return (
    <div className="kpis">
      {scope("atelier")}
      {scope("chantier")}
    </div>
  );
}

export function OperationsPage() {
  const { t } = useTranslation();

  const byStatus = useQuery({
    queryKey: ["ordres"],
    queryFn: () => api.ordres(`?page_size=100`),
    select: (page: Paginated<OrdreFabrication>) => {
      const groups: Groups = {
        prevu: [],
        lance: [],
        en_cours: [],
        termine: [],
        cloture: [],
        annule: [],
      };
      for (const of_ of page.results) {
        if (VALID_STATUSES.has(of_.status)) groups[of_.status].push(of_);
      }
      return groups;
    },
  });

  const charge = useQuery({
    queryKey: ["charge"],
    queryFn: () => api.charge(),
  });

  const situations = useQuery({
    queryKey: ["situations"],
    queryFn: () => api.situations(`?page_size=100`),
    select: (page: Paginated<SituationTravaux>) => page.results,
  });

  if (byStatus.isLoading || charge.isLoading || situations.isLoading)
    return <p className="muted">{t("common.loading")}</p>;
  if (byStatus.isError || charge.isError || situations.isError || !byStatus.data)
    return (
      <p>
        {t("common.error")}{" "}
        <button
          className="btn ghost"
          onClick={() => {
            void byStatus.refetch();
            void charge.refetch();
            void situations.refetch();
          }}
        >
          {t("common.retry")}
        </button>
      </p>
    );

  const groups = byStatus.data;
  const active = groups.en_cours.length + groups.lance.length + groups.prevu.length;
  const reported = situations.data?.reduce((a, s) => a + Number(s.ordered_hours), 0) ?? 0;

  return (
    <>
      <h2>{t("operations.title")}</h2>

      <div className="kpis">
        <div className="card kpi">
          <span className="kpi-label">{t("operations.of")}</span>
          <span className="kpi-value">{active}</span>
        </div>
        <div className="card kpi">
          <span className="kpi-label">{t("operations.reported")}</span>
          <span className="kpi-value">{formatNumber(reported)} h</span>
        </div>
      </div>
      {charge.data ? <Charge stats={charge.data} /> : null}

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
              <span>{t(`operations.${st}`)}</span>
              <span className={`badge ${STATUS_BADGE[st]}`}>{groups[st].length}</span>
            </div>
            {groups[st].length === 0 ? (
              <p className="muted" style={{ padding: "0.5rem 0.25rem" }}>
                {t("common.empty")}
              </p>
            ) : (
              groups[st].map((of_) => <OfCard key={of_.id} of={of_} />)
            )}
          </motion.div>
        ))}
      </div>

      {situations.data && situations.data.length > 0 ? (
        <h3 className="muted" style={{ marginTop: "2rem" }}>
          {t("operations.situations")}
        </h3>
      ) : null}
      <div className="kpis" style={{ flexWrap: "wrap" }}>
        {(situations.data ?? []).map((s) => (
          <div className="card kpi" key={s.id}>
            <span className="kpi-label">
              {s.code} · {s.status_label}
            </span>
            <span className="kpi-value">
              {s.amount === null ? t("operations.masked") : formatNumber(Number(s.amount))}
            </span>
            <span className="meta muted">
              {formatNumber(Number(s.ordered_hours))} h · {s.ordres_count} OF · {s.progress}%
            </span>
          </div>
        ))}
      </div>
    </>
  );
}