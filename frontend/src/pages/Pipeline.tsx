import { useQuery } from "@tanstack/react-query";
import { Layers, Scale, Target, TrendingUp } from "lucide-react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { formatDate, formatMoney, formatPercent } from "../lib/format";
import { CommercialSections } from "../components/commercial/CommercialSections";
import { EcartsM1Section } from "../components/commercial/EcartsM1Section";
import { Badge, Board, BoardCard, BoardColumn, BoardSkeleton, ErrorState, Kpi, PageHeader, SectionNav } from "../components/ui";
import { CardActions } from "../components/ui/Board";
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
  const { t } = useTranslation();
  return (
    <BoardCard delay={Math.min(index * 0.03, 0.3)}>
      <div className="card-top">
        <span className="card-code">{opp.code}</span>
        <span className="card-tags">
          <Badge tone="neutral" title={t("listes.pipeline.probabilite")}>
            {formatPercent(opp.probability)}
          </Badge>
        </span>
      </div>
      <div className="title">{opp.subject}</div>
      <div className="meta">{opp.client_name ?? "—"}</div>
      <div className="card-foot">
        <span>{opp.expected_close ? `${t("pipeline.echeance")} ${formatDate(opp.expected_close)}` : null}</span>
        <span className="amount">{opp.amount === null ? t("pipeline.masked") : formatMoney(opp.amount)}</span>
      </div>
      {opp.stage !== "gagne" && opp.stage !== "perdu" ? (
        <CardActions
          actions={[
            {
              label: t("ecarts_m1.pipe.changer"),
              path: `/api/commercial/opportunities/${opp.id}/changer-etape/`,
              tone: "ghost",
              prompt: {
                name: "stage",
                label: t("ecarts_m1.pipe.etape"),
                options: COLUMNS.filter((c) => c.stage !== opp.stage).map((c) => ({ value: c.stage, label: t(`pipeline.${c.stage}`) })),
              },
            },
          ]}
        />
      ) : null}
    </BoardCard>
  );
}

/** Somme des montants visibles d'une étape (`null` si tous masqués). */
function stageTotal(opps: Opportunity[]): number | null {
  const visible = opps.filter((o) => o.amount !== null);
  return visible.length ? visible.reduce((s, o) => s + Number(o.amount), 0) : null;
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
    <div className="listes-page">
      <PageHeader title={t("pipeline.title")} subtitle={t("listes.sub.pipeline")} />
      <SectionNav
        items={[
          { id: "com-opportunites", label: t("premiumVague2.sections.pipeline.opportunites") },
          { id: "com-offres", label: t("premiumVague2.sections.pipeline.offres") },
          { id: "com-relances", label: t("premiumVague2.sections.pipeline.relances") },
          { id: "com-chiffrage", label: t("premiumVague2.sections.pipeline.chiffrage") },
          { id: "com-profils", label: t("premiumVague2.sections.pipeline.profils") },
          { id: "com-parametres", label: t("premiumVague2.sections.pipeline.parametres") },
        ]}
      />

      {s ? (
        <div className="kpi-grid">
          <Kpi label={t("pipeline.wonTotal")} value={s.won_total} kind="money" icon={TrendingUp} tone="ok" delay={0} />
          <Kpi label={t("pipeline.conversion")} value={formatPercent(s.conversion_rate, { ratio: true, decimals: 1 })} icon={Target} tone="accent" delay={0.05} />
          <Kpi label={t("pipeline.activeSegments")} value={Object.keys(s.margin_by_segment).length} icon={Layers} tone="brand" delay={0.1} />
          {s.pipe_pondere ? (
            <Kpi
              label={t("pipeline.pipePondereTous")}
              value={s.pipe_pondere.total}
              kind="money"
              hint={
                <span title={t("pipeline.pipePondereInfo")}>
                  {s.pipe_pondere_exercice
                    ? t("pipeline.pipePondereExercice", {
                        annee: s.pipe_pondere_exercice.annee,
                        montant: formatMoney(s.pipe_pondere_exercice.total),
                      })
                    : null}
                  {s.pipe_pondere.ponderations
                    ? t("pipeline.pipePonderePoids", {
                        signe: Math.round(s.pipe_pondere.ponderations.signe * 100),
                        enCours: Math.round(s.pipe_pondere.ponderations.en_cours * 100),
                        prospect: Math.round(s.pipe_pondere.ponderations.prospect * 100),
                      })
                    : t("pipeline.pipePondereHint")}
                </span>
              }
              icon={Scale}
              tone="accent"
              delay={0.15}
            />
          ) : null}
        </div>
      ) : null}

      <div id="com-opportunites" className="page-section">
      <Board label={t("listes.boardLabel.pipeline")}>
        {COLUMNS.map((col, ci) => {
          const sum = stageTotal(groups[col.stage]);
          return (
            <BoardColumn
              key={col.stage}
              title={t(`pipeline.${col.stage}`)}
              count={groups[col.stage].length}
              tone={col.badge}
              delay={ci * 0.04}
              limit={20}
              summary={groups[col.stage].length && sum !== null ? formatMoney(sum) : undefined}
            >
              {groups[col.stage].map((opp, i) => (
                <OppCard key={opp.id} opp={opp} index={i} />
              ))}
            </BoardColumn>
          );
        })}
      </Board>
      </div>

      <div id="com-offres" className="page-section">
        <CommercialSections />
      </div>
      <EcartsM1Section />
    </div>
  );
}