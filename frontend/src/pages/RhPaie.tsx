import { useQuery } from "@tanstack/react-query";
import { Banknote, CalendarClock, FileText, Inbox, Users } from "lucide-react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { ActionBar, Badge, Board, BoardCard, BoardColumn, BoardSkeleton, DataTable, EmptyState, ErrorState, Kpi, PageHeader, SectionCard } from "../components/ui";
import type { Column } from "../components/ui";
import { formatDate, formatNumber } from "../lib/format";
import type {
  BulletinPaie,
  DemandeConge,
  Employe,
  Paginated,
  StatutConge,
} from "../types";
import { BaremesSection } from "../components/workflow/BaremesSection";

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

function CongeCard({ c, index }: { c: DemandeConge; index: number }) {
  const { t } = useTranslation();
  return (
    <BoardCard delay={Math.min(index * 0.03, 0.3)}>
      <div className="title">
        {c.code} <span className="muted">· {t(`rhPaie.conges_types.${c.type}`)}</span>
      </div>
      <div className="meta">{c.employe_nom}</div>
      <div className="meta">
        {formatDate(c.date_debut)} → {formatDate(c.date_fin)} · {c.nb_jours} j
        {c.motif ? ` · ${c.motif}` : ""}
      </div>
      <ActionBar
        actions={[
          ...(c.statut === "demande" ? [{ label: t("rhPaie.act.approuver"), path: `/api/rh-paie/conges/${c.id}/approuver/`, tone: "ghost" as const }] : []),
          ...(c.statut === "approuve" ? [{ label: t("actions.valider"), path: `/api/rh-paie/conges/${c.id}/valider/` }] : []),
          ...(c.statut === "demande" || c.statut === "approuve"
            ? [{ label: t("actions.refuser"), path: `/api/rh-paie/conges/${c.id}/refuser/`, tone: "danger" as const }]
            : []),
        ]}
      />
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
        {b.code} · {b.matricule} · {formatDate(b.periode)}{" "}
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
        {b.disponible_le && <span className="badge ok"> {t("baremes.diffuse")}</span>}
        {b.move_number && <span className="badge brand"> {b.move_number}</span>}
      </span>
      <ActionBar
        actions={[
          ...(b.statut === "brouillon"
            ? [
                { label: t("actions.calculer"), path: `/api/rh-paie/bulletins/${b.id}/calculer/`, tone: "ghost" as const },
                { label: t("actions.valider"), path: `/api/rh-paie/bulletins/${b.id}/valider/` },
              ]
            : []),
          ...((b.statut === "valide" || b.statut === "cloture") && !b.disponible_le
            ? [{ label: t("actions.diffuser"), path: `/api/rh-paie/bulletins/${b.id}/diffuser/`, tone: "ghost" as const }]
            : []),
          ...((b.statut === "valide" || b.statut === "cloture") && !b.move_number
            ? [
                {
                  label: t("actions.comptabiliser"),
                  path: `/api/rh-paie/bulletins/${b.id}/comptabiliser/`,
                  confirm: t("actions.confirmComptabiliser"),
                },
              ]
            : []),
          ...(b.statut === "valide"
            ? [
                {
                  label: t("actions.cloturer"),
                  path: `/api/rh-paie/bulletins/${b.id}/cloturer/`,
                  tone: "ghost" as const,
                  confirm: t("actions.confirmCloturer"),
                },
              ]
            : []),
        ]}
      />
    </div>
  );
}

function employeTone(e: Employe): "ok" | "warn" | "err" | "brand" {
  return e.statut === "actif" ? "ok" : e.statut === "sorti" ? "err" : e.statut === "suspendu" ? "warn" : "brand";
}

export function RhPaiePage() {
  const { t, i18n } = useTranslation();
  const employeColumns: Column<Employe>[] = [
    { key: "code", header: t("rhPaie.col.matricule"), render: (e) => e.code },
    { key: "nom", header: t("rhPaie.col.nom"), render: (e) => e.nom_complet },
    { key: "fonction", header: t("rhPaie.col.fonction"), render: (e) => [e.fonction, e.departement].filter(Boolean).join(" · ") || "—" },
    { key: "cat", header: t("rhPaie.col.categorie"), render: (e) => t(`rhPaie.categories.${e.categorie}`) },
    {
      key: "contrat",
      header: t("rhPaie.contrat"),
      render: (e) =>
        e.contrat_actif ? (
          <>
            {t(`rhPaie.contrats_types.${e.contrat_actif.type}`)} · {formatDate(e.contrat_actif.date_debut, i18n.language)}{" "}
            {e.contrat_actif.a_renouveler && <Badge tone="warn">≤ 90 j</Badge>}
          </>
        ) : (
          "—"
        ),
    },
    { key: "solde", header: t("rhPaie.soldeConges"), num: true, render: (e) => `${formatNumber(e.solde_conges)} j` },
    { key: "statut", header: t("rhPaie.col.statut"), render: (e) => <Badge tone={employeTone(e)}>{t(`rhPaie.statut_employe.${e.statut}`)}</Badge> },
  ];

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

      {employesAll.length > 0 && (
        <SectionCard title={`${t("rhPaie.employes")} · ${employesAll.length}`}>
          <DataTable rows={employesAll} columns={employeColumns} caption={t("rhPaie.employes")} />
        </SectionCard>
      )}

      {bulletinsAll.length > 0 ? (
        <>
          <h3 className="section-heading">
            {t("rhPaie.bulletins")}
          </h3>
          <div className="card-list">
            {bulletinsAll.map((b) => <BulletinCard key={b.id} b={b} />)}
          </div>
        </>
      ) : null}
      <BaremesSection />
    </>
  );
}