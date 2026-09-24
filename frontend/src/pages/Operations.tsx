import { useQuery } from "@tanstack/react-query";
import { ClipboardList, Clock3, Construction, Factory, HardHat } from "lucide-react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { formatDate, formatNumber } from "../lib/format";
import { Board, BoardCard, BoardColumn, BoardSkeleton, ErrorState, Kpi, PageHeader } from "../components/ui";
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

function OfCard({ of, index }: { of: OrdreFabrication; index: number }) {
  const { t } = useTranslation();
  return (
    <BoardCard delay={Math.min(index * 0.03, 0.3)}>
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
    </BoardCard>
  );
}

function Charge({ stats }: { stats: ChargeStats }) {
  const { t } = useTranslation();
  const scope = (key: "atelier" | "chantier", delay: number, icon: typeof Factory) => (
    <Kpi
      label={t(`operations.${key}`)}
      value={`${formatNumber(stats.totals[key].calculated)} h ${t("operations.planned")}`}
      hint={`${formatNumber(stats.totals[key].pointed)} h ${t("operations.pointed")} · ${stats.totals[key].count} OF`}
      icon={icon}
      tone="brand"
      delay={delay}
    />
  );
  return (
    <div className="kpi-grid">
      {scope("atelier", 0, Factory)}
      {scope("chantier", 0.05, Construction)}
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
    return <BoardSkeleton cols={5} rows={3} />;
  if (byStatus.isError || charge.isError || situations.isError || !byStatus.data)
    return (
      <ErrorState
        message={t("common.error")}
        onRetry={() => {
          void byStatus.refetch();
          void charge.refetch();
          void situations.refetch();
        }}
        retryLabel={t("common.retry")}
      />
    );

  const groups = byStatus.data;
  const active = groups.en_cours.length + groups.lance.length + groups.prevu.length;
  const reported = situations.data?.reduce((a, s) => a + Number(s.ordered_hours), 0) ?? 0;

  return (
    <>
      <PageHeader title={t("operations.title")} />

      <div className="kpi-grid">
        <Kpi label={t("operations.of")} value={active} icon={HardHat} tone="brand" delay={0} />
        <Kpi label={t("operations.reported")} value={`${formatNumber(reported)} h`} icon={Clock3} tone="accent" delay={0.05} />
      </div>
      {charge.data ? <Charge stats={charge.data} /> : null}

      <div style={{ overflowX: "auto" }}>
        <Board>
          {BOARD_ORDER.map((st, ci) => (
            <BoardColumn
              key={st}
              title={t(`operations.${st}`)}
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
                groups[st].map((of_, i) => <OfCard key={of_.id} of={of_} index={i} />)
              )}
            </BoardColumn>
          ))}
        </Board>
      </div>

      {situations.data && situations.data.length > 0 ? (
        <h3 className="muted" style={{ marginTop: "2rem" }}>
          {t("operations.situations")}
        </h3>
      ) : null}
      <div className="kpi-grid">
        {(situations.data ?? []).map((s, i) => (
          <Kpi
            key={s.id}
            label={`${s.code} · ${s.status_label}`}
            value={s.amount === null ? t("operations.masked") : formatNumber(Number(s.amount))}
            hint={`${formatNumber(Number(s.ordered_hours))} h · ${s.ordres_count} OF · ${s.progress}%`}
            icon={ClipboardList}
            tone="brand"
            delay={i * 0.05}
          />
        ))}
      </div>
    </>
  );
}