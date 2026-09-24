import { useQuery } from "@tanstack/react-query";
import { Banknote, CalendarClock, FileText, Inbox, Users } from "lucide-react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { Board, BoardCard, BoardColumn, BoardSkeleton, EmptyState, ErrorState, Kpi, PageHeader } from "../components/ui";
import { formatDate, formatNumber } from "../lib/format";
import type {
  BulletinPaie,
  DemandeConge,
  Employe,
  Paginated,
  StatutConge,
} from "../types";

type CongeGroups = Record<StatutConge, DemandeConge[]>;

const CONGE_BADGE: Record<StatutConge, "ok" | "warn" | "err" | "brand"> = {
  demande: "brand",
  approuve: "warn",
  valide: "ok",
  refuse: "err",
  annule: "err",
};
const CONGE_ORDER: StatutConge[] = ["demande", "approuve", "valide", "refuse", "annule"];
const CONGE_VALID = new Set<StatutConge>(CONGE_ORDER);

function EmployeCard({ emp }: { emp: Employe }) {
  const { t } = useTranslation();
  const badge =
    emp.statut === "actif" ? "ok" : emp.statut === "sorti" ? "err" : emp.statut === "suspendu" ? "warn" : "brand";
  const contrat = emp.contrat_actif;
  return (
    <div className="card kpi" key={emp.id}>
      <span className="kpi-label">
        {emp.code} · {t(`rhPaie.categories.${emp.categorie}`)}{" "}
        <span className={`badge ${badge}`}>{t(`rhPaie.statut_employe.${emp.statut}`)}</span>
        {contrat?.a_renouveler ? <span className="badge warn"> {t("rhPaie.contrat")} ≤ 90 j</span> : null}
      </span>
      <span className="kpi-value">{emp.nom_complet}</span>
      <span className="meta muted">
        {emp.fonction || "—"} · {emp.departement || "—"}
        {emp.site ? ` · ${emp.site}` : ""}
      </span>
      <span className="meta muted">
        {contrat ? `${t(`rhPaie.contrats_types.${contrat.type}`)} · ${formatDate(contrat.date_debut, "fr")}` : "—"}
        {" · "}
        {t("rhPaie.soldeConges")} {formatNumber(emp.solde_conges)} j
      </span>
    </div>
  );
}

function CongeCard({ c, index }: { c: DemandeConge; index: number }) {
  const { t } = useTranslation();
  return (
    <BoardCard delay={Math.min(index * 0.03, 0.3)}>
      <div className="title">
        {c.code} <span className="muted">· {t(`rhPaie.conges_types.${c.type}`)}</span>
      </div>
      <div className="meta">{c.employe_nom}</div>
      <div className="meta">
        {formatDate(c.date_debut, "fr")} → {formatDate(c.date_fin, "fr")} · {c.nb_jours} j
        {c.motif ? ` · ${c.motif}` : ""}
      </div>
    </BoardCard>
  );
}

function BulletinCard({ b }: { b: BulletinPaie }) {
  const { t } = useTranslation();
  const badge =
    b.statut === "cloture" ? "ok" : b.statut === "valide" ? "brand" : b.statut === "annule" ? "err" : "warn";
  return (
    <div className="card kpi" key={b.id}>
      <span className="kpi-label">
        {b.code} · {b.matricule} · {formatDate(b.periode, "fr")}{" "}
        <span className={`badge ${badge}`}>{t(`rhPaie.bulletins_statut.${b.statut}`)}</span>
      </span>
      <span className="kpi-value">{b.employe_nom}</span>
      <span className="meta muted">
        {b.has_amount_access && b.net !== null ? (
          <>
            Net {formatNumber(b.net)} F · Brut {formatNumber(b.brut)} F
          </>
        ) : (
          "••••••"
        )}
      </span>
    </div>
  );
}

export function RhPaiePage() {
  const { t } = useTranslation();

  const stats = useQuery({ queryKey: ["rhpaie-stats"], queryFn: api.rhPaieStats });

  const employes = useQuery({
    queryKey: ["rhpaie-employes"],
    queryFn: () => api.employes(`?page_size=50`),
    select: (page: Paginated<Employe>) => page.results,
  });

  const conges = useQuery({
    queryKey: ["rhpaie-conges"],
    queryFn: () => api.congesRh(`?page_size=100`),
    select: (page: Paginated<DemandeConge>) => {
      const groups: CongeGroups = { demande: [], approuve: [], valide: [], refuse: [], annule: [] };
      for (const c of page.results) {
        if (CONGE_VALID.has(c.statut)) groups[c.statut].push(c);
      }
      return groups;
    },
  });

  const bulletins = useQuery({
    queryKey: ["rhpaie-bulletins"],
    queryFn: () => api.bulletinsPaie(`?page_size=50`),
    select: (page: Paginated<BulletinPaie>) => page.results,
  });

  const masse = useQuery({
    queryKey: ["rhpaie-masse"],
    queryFn: () => api.masseSalariale(""),
  });

  if (stats.isLoading || conges.isLoading || !stats.data || !conges.data)
    return <BoardSkeleton cols={5} rows={3} />;
  if (stats.isError || conges.isError || !masse.data)
    return (
      <ErrorState
        message={t("common.error")}
        onRetry={() => {
          void stats.refetch();
          void employes.refetch();
          void conges.refetch();
          void bulletins.refetch();
          void masse.refetch();
        }}
        retryLabel={t("common.retry")}
      />
    );

  const s = stats.data;
  const employesAll = employes.data ?? [];
  const groups = conges.data;
  const bulletinsAll = bulletins.data ?? [];
  const m = masse.data;
  const enAttente = groups["demande"].length + groups["approuve"].length;

  return (
    <>
      <PageHeader title={t("rhPaie.title")} />

      <div className="kpi-grid">
        <Kpi label={t("rhPaie.effectif")} value={s.effectif} hint={`${t("rhPaie.enConge")} · ${s.en_conge} · ${t("rhPaie.contratsExpirants")} · ${s.contrats_expirants_30}`} icon={Users} tone="brand" delay={0} />
        <Kpi label={t("rhPaie.congesEnAttente")} value={enAttente || s.conges_en_attente} hint={`${t("rhPaie.qualsExpirees")} · ${s.qualifications_expirees}`} icon={CalendarClock} tone="warn" delay={0.05} />
        <Kpi label={t("rhPaie.bulletinsMois")} value={s.bulletins_mois} hint={`${m.mois} · ${t("rhPaie.masseBrute")} ${formatNumber(m.brut_total)} F`} icon={FileText} tone="brand" delay={0.1} />
        <Kpi label={t("rhPaie.masseNette")} value={`${formatNumber(m.net_total)} F`} hint={`${t("rhPaie.bulletins")} · ${m.bulletins}`} icon={Banknote} tone="accent" delay={0.15} />
      </div>

      <div style={{ overflowX: "auto" }}>
        <Board>
          {CONGE_ORDER.map((st, ci) => (
            <BoardColumn
              key={st}
              title={t(`rhPaie.conges_statut.${st}`)}
              count={groups[st].length}
              tone={CONGE_BADGE[st]}
              delay={ci * 0.05}
              minWidth={240}
            >
              {groups[st].length === 0 ? (
                <EmptyState icon={Inbox} label={t("common.empty")} />
              ) : (
                groups[st].map((c, i) => <CongeCard key={c.id} c={c} index={i} />)
              )}
            </BoardColumn>
          ))}
        </Board>
      </div>

      <p className="muted" style={{ marginTop: "0.5rem" }}>
        {t("rhPaie.pendingNote")}
      </p>

      {employesAll.length > 0 ? (
        <>
          <h3 className="muted" style={{ marginTop: "2rem" }}>
            {t("rhPaie.employes")} · {employesAll.length}
          </h3>
          <div className="kpis" style={{ flexWrap: "wrap" }}>
            {employesAll.map((e) => <EmployeCard key={e.id} emp={e} />)}
          </div>
        </>
      ) : null}

      {bulletinsAll.length > 0 ? (
        <>
          <h3 className="muted" style={{ marginTop: "2rem" }}>
            {t("rhPaie.bulletins")}
          </h3>
          <div className="kpis" style={{ flexWrap: "wrap" }}>
            {bulletinsAll.map((b) => <BulletinCard key={b.id} b={b} />)}
          </div>
        </>
      ) : null}
    </>
  );
}