import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Banknote, CalendarClock, FileText, Users } from "lucide-react";
import { useTranslation } from "react-i18next";

import "../styles/pages/sections.css";
import { api } from "../api/client";
import { SiteFilter, siteQuery } from "../components/sites/SiteFilter";
import { ActionBar, Badge, Board, BoardCard, BoardColumn, BoardSkeleton, DataGrid, ErrorState, Kpi, ModuleSettings, PageHeader, SearchField, SectionCard, SectionNav } from "../components/ui";
import type { ActionDef, Column } from "../components/ui";
import { actionsColumn } from "../components/ui/DataTable";
import { formatDate, formatMoney, formatNumber } from "../lib/format";
import { usePagedList } from "../lib/usePagedList";
import type {
  BulletinPaie,
  DemandeConge,
  Employe,
  Paginated,
  StatutConge,
} from "../types";
import { BaremesSection } from "../components/workflow/BaremesSection";
import { EcartsM9aSection } from "../components/rhpaie/EcartsM9aSection";
import { EcartsM9bSection } from "../components/rhpaie/EcartsM9bSection";
import { EcartsM9cSection } from "../components/rhpaie/EcartsM9cSection";
import { DeclarationsSection } from "../components/workflow/DeclarationsSection";
import { VirementsSection } from "../components/workflow/VirementsSection";

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

/** Actions de workflow d'un bulletin : l'action attendue d'abord (bouton), le reste dans « ⋯ ». */
function bulletinActions(b: BulletinPaie, t: (k: string) => string): ActionDef[] {
  const emis = b.statut === "valide" || b.statut === "cloture";
  return [
    ...(b.statut === "brouillon"
      ? [
          { label: t("actions.valider"), path: `/api/rh-paie/bulletins/${b.id}/valider/` },
          { label: t("m9a.preparer"), path: `/api/rh-paie/bulletins/${b.id}/preparer/` },
          { label: t("actions.calculer"), path: `/api/rh-paie/bulletins/${b.id}/calculer/`, tone: "ghost" as const },
          { label: t("declarations.integrer"), path: `/api/rh-paie/bulletins/${b.id}/integrer-temps/`, tone: "ghost" as const },
        ]
      : []),
    ...(emis && !b.move_number
      ? [{ label: t("actions.comptabiliser"), path: `/api/rh-paie/bulletins/${b.id}/comptabiliser/`, confirm: t("actions.confirmComptabiliser") }]
      : []),
    ...(emis && !b.disponible_le ? [{ label: t("actions.diffuser"), path: `/api/rh-paie/bulletins/${b.id}/diffuser/`, tone: "ghost" as const }] : []),
    ...(emis && (!b.signature_statut || b.signature_statut === "refused")
      ? [{ label: t("m9c.signature.demander"), path: `/api/rh-paie/bulletins/${b.id}/signer/`, tone: "ghost" as const }]
      : []),
    ...(emis && !b.document ? [{ label: t("virements.archiver"), path: `/api/rh-paie/bulletins/${b.id}/archiver/`, tone: "ghost" as const }] : []),
    ...(b.statut === "valide"
      ? [{ label: t("actions.cloturer"), path: `/api/rh-paie/bulletins/${b.id}/cloturer/`, tone: "ghost" as const, confirm: t("actions.confirmCloturer") }]
      : []),
  ];
}

const BULLETIN_TONE: Record<string, "ok" | "brand" | "err" | "warn"> = { cloture: "ok", valide: "brand", annule: "err" };

/** « 2026-10 » → « Octobre 2026 » (langue de l'interface) ; valeur inattendue renvoyée telle quelle. */
function moisLong(mois: string, langue: string): string {
  const m = /^(\d{4})-(\d{2})$/.exec(mois);
  if (!m) return mois;
  const texte = new Date(Number(m[1]), Number(m[2]) - 1, 1).toLocaleDateString(langue, { month: "long", year: "numeric" });
  return texte.charAt(0).toUpperCase() + texte.slice(1);
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
            {t(`rhPaie.contrats_types.${e.contrat_actif.type}`)}
            <span className="cell-sub">
              {t("revueR3.rh.depuis", { date: formatDate(e.contrat_actif.date_debut, i18n.language) })}
            </span>{" "}
            {e.contrat_actif.a_renouveler && <Badge tone="warn">≤ 90 j</Badge>}
          </>
        ) : (
          "—"
        ),
    },
    { key: "solde", header: t("rhPaie.soldeConges"), num: true, render: (e) => `${formatNumber(e.solde_conges)} j` },
    { key: "statut", header: t("rhPaie.col.statut"), render: (e) => <Badge tone={employeTone(e)}>{t(`rhPaie.statut_employe.${e.statut}`)}</Badge> },
  ];

  const bulletinColumns: Column<BulletinPaie>[] = [
    {
      key: "salarie",
      header: t("revueR3.rh.salarie"),
      sortValue: (b) => b.employe_nom,
      render: (b) => (
        <>
          {b.employe_nom}
          <span className="cell-sub">
            {b.code} · {b.matricule}
          </span>
        </>
      ),
    },
    { key: "periode", header: t("revueR3.rh.periode"), sortValue: (b) => b.periode, render: (b) => <span className="r3-nowrap">{moisLong(b.periode.slice(0, 7), i18n.language)}</span> },
    {
      key: "brut",
      header: t("revueR3.rh.brut"),
      num: true,
      sortValue: (b) => Number(b.brut ?? 0),
      render: (b) => (b.has_amount_access && b.brut !== null ? formatMoney(b.brut) : "••••••"),
    },
    {
      key: "net",
      header: t("revueR3.rh.net"),
      num: true,
      sortValue: (b) => Number(b.net ?? 0),
      render: (b) => (b.has_amount_access && b.net !== null ? <strong>{formatMoney(b.net)}</strong> : "••••••"),
    },
    {
      key: "statut",
      header: t("rhPaie.col.statut"),
      render: (b) => {
        const suivi = [
          b.move_number ? t("revueR3.rh.comptabilise") : null,
          b.disponible_le ? t("baremes.diffuse") : null,
          b.signature_statut ? t(`m9c.signature.${b.signature_statut}`) : null,
          b.document ? t("virements.archive") : null,
        ].filter(Boolean);
        return (
          <>
            <Badge tone={BULLETIN_TONE[b.statut] ?? "warn"}>{t(`rhPaie.bulletins_statut.${b.statut}`)}</Badge>
            {suivi.length > 0 ? <span className="cell-sub">{suivi.join(" · ")}</span> : null}
          </>
        );
      },
    },
    {
      key: "pdf",
      header: <span className="sr-only">{t("virements.pdf")}</span>,
      render: (b) =>
        b.statut !== "annule" ? (
          <button type="button" className="btn ghost sm" onClick={() => void api.download(`/api/rh-paie/bulletins/${b.id}/pdf/`, `${b.code}.pdf`)}>
            {t("virements.pdf")}
          </button>
        ) : null,
    },
    actionsColumn<BulletinPaie>(t("listes.col.actions"), (b) => bulletinActions(b, t)),
  ];

  const stats = useQuery({ queryKey: ["rhpaie-stats"], queryFn: api.rhPaieStats });

  const [employeSite, setEmployeSite] = useState("");
  const employes = usePagedList<Employe>("rhpaie-employes", (q) => api.employes(q), { pageSize: 20, extra: siteQuery(employeSite) });

  const conges = useQuery({
    queryKey: ["rhpaie-conges"],
    queryFn: () => api.congesRh(`?page_size=500`),
    select: (page: Paginated<DemandeConge>) => {
      const groups: CongeGroups = { demande: [], approuve: [], valide: [], refuse: [], annule: [] };
      for (const c of page.results) {
        if (CONGE_VALID.has(c.statut)) groups[c.statut].push(c);
      }
      return groups;
    },
  });

  const bulletins = usePagedList<BulletinPaie>("rhpaie-bulletins", (q) => api.bulletinsPaie(q), { pageSize: 20 });

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
          void employes.query.refetch();
          void conges.refetch();
          void bulletins.query.refetch();
          void masse.refetch();
        }}
        retryLabel={t("common.retry")}
      />
    );

  const s = stats.data;
  const employesAll = employes.rows;
  const groups = conges.data;
  const bulletinsAll = bulletins.rows;
  const m = masse.data;
  const enAttente = groups["demande"].length + groups["approuve"].length;
  // Un seul avertissement de taux provisoires pour la page de bulletins, pas un pavé par bulletin.
  const avertissement = bulletinsAll.find((b) => b.avertissement)?.avertissement;

  return (
    <>
      <PageHeader title={t("rhPaie.title")} subtitle={t("tableaux.entetes.rhPaie")} />
      <SectionNav
        items={[
          { id: "rh-conges", label: t("premiumVague2.sections.rhPaie.conges") },
          { id: "rh-employes", label: t("premiumVague2.sections.rhPaie.employes") },
          { id: "rh-paie", label: t("premiumVague2.sections.rhPaie.paie") },
          { id: "rh-formation", label: t("premiumVague2.sections.rhPaie.formation") },
          { id: "rh-declarations", label: t("premiumVague2.sections.rhPaie.declarations") },
          { id: "rh-parametres", label: t("premiumKit.moduleSettings.nav") },
        ]}
      />

      <div className="kpi-grid">
        <Kpi label={t("rhPaie.effectif")} value={s.effectif} hint={`${s.en_conge} ${t("rhPaie.enConge")} · ${s.contrats_expirants_30} ${t("rhPaie.contratsExpirants")}`} icon={Users} tone="brand" delay={0} />
        <Kpi label={t("rhPaie.congesEnAttente")} value={enAttente || s.conges_en_attente} hint={t("revueR3.rh.qualsExpirees", { count: s.qualifications_expirees })} icon={CalendarClock} tone="warn" delay={0.05} />
        <Kpi label={t("rhPaie.bulletinsMois")} value={s.bulletins_mois} hint={`${moisLong(m.mois, i18n.language)} · ${t("rhPaie.masseBrute")} ${formatMoney(m.brut_total)}`} icon={FileText} tone="brand" delay={0.1} />
        <Kpi label={t("rhPaie.masseNette")} value={m.net_total} kind="money" hint={`${t("rhPaie.bulletins")} · ${formatNumber(m.bulletins)}`} icon={Banknote} tone="accent" delay={0.15} />
      </div>

      <div id="rh-conges" className="page-section">
      <h3 className="section-heading">{t("revueR3.rh.conges")}</h3>
      <Board label={t("revueR3.rh.conges")}>
        {CONGE_ORDER.map((st, ci) => (
          <BoardColumn
            key={st}
            title={t(`rhPaie.conges_statut.${st}`)}
            count={groups[st].length}
            tone={CONGE_BADGE[st]}
            delay={ci * 0.05}
            limit={6}
          >
            {groups[st].map((c, i) => (
              <CongeCard key={c.id} c={c} index={i} />
            ))}
          </BoardColumn>
        ))}
      </Board>
      </div>

      <div id="rh-employes" className="page-section">
      {(employes.count > 0 || employes.search || employeSite) && (
        <SectionCard title={`${t("rhPaie.employes")} · ${employes.count}`}>
          <div className="r3-toolbar">
            <SearchField value={employes.search} onChange={employes.setSearch} placeholder={t("rhPaie.searchEmployes")} />
            <SiteFilter value={employeSite} onChange={setEmployeSite} />
          </div>
          <DataGrid
            rows={employesAll}
            columns={employeColumns}
            caption={t("rhPaie.employes")}
            loading={employes.query.isFetching}
            emptyLabel={t("common.empty")}
            pagination={{ page: employes.page, pageSize: employes.pageSize, count: employes.count, onPageChange: employes.setPage, onPageSizeChange: employes.setPageSize }}
          />
        </SectionCard>
      )}
      <EcartsM9aSection />
      </div>

      <div id="rh-paie" className="page-section">
      {bulletins.count > 0 || bulletins.search ? (
        <SectionCard title={`${t("rhPaie.bulletins")} · ${bulletins.count}`}>
          {avertissement ? (
            <p className="r3-note" role="note" data-testid="avertissement-provisoire" title={avertissement}>
              {t("revueR3.rh.avertissement")}
            </p>
          ) : null}
          <div className="list-toolbar">
            <SearchField value={bulletins.search} onChange={bulletins.setSearch} placeholder={t("rhPaie.searchBulletins")} />
          </div>
          <DataGrid
            rows={bulletinsAll}
            columns={bulletinColumns}
            caption={t("rhPaie.bulletins")}
            loading={bulletins.query.isFetching}
            emptyLabel={t("common.empty")}
            pagination={{ page: bulletins.page, pageSize: bulletins.pageSize, count: bulletins.count, onPageChange: bulletins.setPage, onPageSizeChange: bulletins.setPageSize }}
          />
        </SectionCard>
      ) : null}
      <EcartsM9bSection />
      <VirementsSection />
      </div>

      <div id="rh-formation" className="page-section">
        <EcartsM9cSection />
      </div>

      <div id="rh-declarations" className="page-section">
        <DeclarationsSection />
      </div>

      <ModuleSettings id="rh-parametres">
        <BaremesSection />
      </ModuleSettings>
    </>
  );
}