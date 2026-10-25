import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { BadgePercent, ClipboardList, CreditCard, Landmark } from "lucide-react";
import { useTranslation } from "react-i18next";

import "../styles/pages/sections.css";
import { api } from "../api/client";
import { Badge, Board, BoardCard, BoardColumn, BoardSkeleton, DataGrid, DataTable, ErrorState, FilterBar, Kpi, ModuleSettings, PageHeader, QuickForm, SearchField, SectionCard, SectionNav } from "../components/ui";
import { CardActions } from "../components/ui/Board";
import { actionsColumn } from "../components/ui/DataTable";
import type { ActionDef, Column } from "../components/ui";
import { ClotureSection } from "../components/workflow/ClotureSection";
import { FacturationSection } from "../components/workflow/FacturationSection";
import { BanqueSection } from "../components/workflow/BanqueSection";
import { LettrageSection } from "../components/workflow/LettrageSection";
import { EcartsM10Section, GabaritsEtatsSection } from "../components/comptabilite/EcartsM10Section";
import { EcartsA2Section } from "../components/comptabilite/EcartsA2Section";
import { ImportGrandLivreSection, RetenuesGarantieSection } from "../components/suivi/SuiviSections";
import { formatDate, formatMoney } from "../lib/format";
import { nomPersonne } from "../components/sections/affichage";
import { pagedQuery, usePagedList } from "../lib/usePagedList";
import { useFiltresListe } from "../lib/useFiltresListe";
import type {
  CompteBancaire,
  ControleInterne,
  DeclarationTva,
  Engagement,
  Paginated,
  Paiement,
  ReleveBancaire,
  StatutEngagement,
} from "../types";

type EngagementGroups = Record<StatutEngagement, Engagement[]>;

const ENG_BADGE: Record<StatutEngagement, "ok" | "warn" | "neutral" | "brand"> = {
  brouillon: "warn",
  soumis: "brand",
  approuve: "ok",
  annule: "neutral",
};
const ENG_ORDER: StatutEngagement[] = ["brouillon", "soumis", "approuve", "annule"];
const ENG_VALID = new Set<StatutEngagement>(ENG_ORDER);

function engagementActions(e: Engagement, t: (k: string) => string): ActionDef[] {
  const base = `/api/comptabilite/engagements/${e.id}`;
  return [
    ...(e.statut === "brouillon" ? [{ label: t("comptabilite.act.soumettre"), path: `${base}/soumettre/`, tone: "ghost" as const }] : []),
    ...(e.statut === "soumis" ? [{ label: t("comptabilite.act.approuver"), path: `${base}/approuver/` }] : []),
    ...(e.statut === "brouillon" || e.statut === "soumis"
      ? [{ label: t("comptabilite.act.annuler"), path: `${base}/annuler/`, tone: "danger" as const, confirm: t("comptabilite.act.confirmAnnuler") }]
      : []),
  ];
}

function EngagementCard({ e, index }: { e: Engagement; index: number }) {
  const { t } = useTranslation();
  const paye = Number(e.total_paye);
  // Engagement entièrement réglé : « Soldé » plutôt que de répéter le même montant deux fois.
  const solde = paye > 0 && paye >= Number(e.montant);
  return (
    <BoardCard delay={Math.min(index * 0.03, 0.3)}>
      <div className="card-top">
        <span className="card-code">
          {e.code}
          {e.compte_depense_code ? ` · ${e.compte_depense_code}` : ""}
        </span>
      </div>
      <div className="title">{e.objet}</div>
      {e.fournisseur_name ? <div className="meta">{e.fournisseur_name}</div> : null}
      <div className="card-foot">
        <span>{solde ? t("revueR3.compta.solde") : paye > 0 ? t("listes.compta.paye", { montant: formatMoney(paye) }) : null}</span>
        <span className="amount">{formatMoney(e.montant)}</span>
      </div>
      <CardActions actions={engagementActions(e, t)} />
    </BoardCard>
  );
}

const masque = "••••••";

/** « proc. 4.7 » (abréviation saisie) → « Procédure 4.7 » : aucun code abrégé à l'écran. */
function referenceProcedure(ref: string | null | undefined, t: (k: string, o?: Record<string, unknown>) => string) {
  if (!ref) return "—";
  const m = /^proc\.?\s*(.+)$/i.exec(ref.trim());
  return m ? t("revueR3.compta.procedure", { ref: m[1] }) : ref;
}

export function ComptabilitePage() {
  const { t, i18n } = useTranslation();

  const banques = useQuery({ queryKey: ["compta-banques"], queryFn: () => api.listAll<CompteBancaire>("/api/comptabilite/comptes-bancaires/") });

  // Paiements : tableau paginé avec recherche ; liste complète pour le décompte des validés.
  const filtresPai = useFiltresListe("/api/comptabilite/paiements/");
  const paiements = usePagedList<Paiement>("compta-paiements", (q) => api.paiements(q), { extra: filtresPai.extra });
  const paiementsTous = useQuery({ queryKey: ["compta-paiements-tous"], queryFn: () => api.listAll<Paiement>("/api/comptabilite/paiements/") });

  // Engagements : liste complète pour le choix du formulaire (approuvés), Kanban filtré par la recherche.
  const engagementsTous = useQuery({ queryKey: ["compta-engagements-tous"], queryFn: () => api.listAll<Engagement>("/api/comptabilite/engagements/") });
  const [engSearch, setEngSearch] = useState("");
  const engagements = useQuery({
    queryKey: ["compta-engagements", engSearch],
    queryFn: () => api.engagements(pagedQuery(1, 500, engSearch)),
    placeholderData: keepPreviousData,
    select: (page: Paginated<Engagement>) => {
      const groups: EngagementGroups = { brouillon: [], soumis: [], approuve: [], annule: [] };
      for (const e of page.results) {
        if (ENG_VALID.has(e.statut)) groups[e.statut].push(e);
      }
      return groups;
    },
  });

  const tva = useQuery({ queryKey: ["compta-tva"], queryFn: () => api.listAll<DeclarationTva>("/api/comptabilite/declarations-tva/") });

  const controles = useQuery({ queryKey: ["compta-controles"], queryFn: () => api.listAll<ControleInterne>("/api/comptabilite/controles/") });

  const releves = usePagedList<ReleveBancaire>("compta-releves", (q) => api.relevesBancaires(q));
  const analytiques = useQuery({
    queryKey: ["compta-analytiques"],
    queryFn: () => api.listAll<{ id: string; code: string; label: string }>("/api/referentiels/analytic-accounts/"),
    retry: 0,
  });

  if (paiementsTous.isLoading || engagements.isLoading || !paiementsTous.data || !engagements.data)
    return <BoardSkeleton cols={4} rows={3} />;

  if (paiementsTous.isError || engagements.isError || !tva.data || !controles.data)
    return (
      <ErrorState
        message={t("common.error")}
        onRetry={() => {
          void banques.refetch();
          void paiements.query.refetch();
          void paiementsTous.refetch();
          void engagementsTous.refetch();
          void engagements.refetch();
          void tva.refetch();
          void controles.refetch();
          void releves.query.refetch();
        }}
        retryLabel={t("common.retry")}
      />
    );

  const pay = paiements.rows;
  const groups = engagements.data;
  const tvaAll = tva.data;
  const controlesAll = controles.data;
  const relevesAll = releves.rows;
  const banquesAll = banques.data ?? [];
  const valides = (paiementsTous.data ?? []).filter((p) => p.statut === "valide");
  // B05 : une déclaration jamais calculée porte des montants à 0 par défaut — ce n'est pas une TVA nulle.
  const tvaCalculees = tvaAll.filter((d) => Boolean(d.source_calcul));
  const tvaDue = tvaCalculees.reduce(
    (acc, d) => acc + (d.statut !== "deposee" && d.has_amount_access && d.net_a_payer !== null ? Number(d.net_a_payer) : 0),
    0,
  );
  const aCalculer = <span className="muted">{t("vague3C2.compta.aCalculer")}</span>;
  const montantTva = (d: DeclarationTva, v: string | null) => (!d.has_amount_access ? masque : d.source_calcul ? formatMoney(v) : aCalculer);
  const enCours = groups["brouillon"].length + groups["soumis"].length;

  const bankColumns: Column<CompteBancaire>[] = [
    { key: "banque", header: t("listes.compta.banque"), sortValue: (b) => b.banque, render: (b) => b.banque },
    { key: "libelle", header: t("listes.compta.libelle"), render: (b) => <>{b.label}<span className="cell-sub">{b.code}</span></> },
    { key: "numero", header: t("listes.compta.numero"), render: (b) => (b.numero ? <span className="cell-mono">{b.numero}</span> : "—") },
    { key: "compte", header: t("listes.compta.compte"), render: (b) => b.compte_comptable_code },
    { key: "solde", header: t("listes.compta.solde"), num: true, sortValue: (b) => Number(b.solde_initial), render: (b) => formatMoney(b.solde_initial) },
  ];
  const releveColumns: Column<ReleveBancaire>[] = [
    { key: "code", header: t("comptabilite.col.code"), render: (r) => r.code },
    { key: "bank", header: t("comptabilite.col.bank"), render: (r) => r.compte_bancaire_label },
    { key: "period", header: t("comptabilite.col.period"), render: (r) => `${formatDate(r.date_debut, i18n.language)} → ${formatDate(r.date_fin, i18n.language)}` },
    { key: "debit", header: t("comptabilite.col.debit"), num: true, render: (r) => formatMoney(r.total_debit) },
    { key: "credit", header: t("comptabilite.col.credit"), num: true, render: (r) => formatMoney(r.total_credit) },
    { key: "statut", header: t("comptabilite.col.status"), render: (r) => <Badge tone={r.statut === "valide" ? "ok" : "warn"}>{t(`comptabilite.releve_statut.${r.statut}`)}</Badge> },
  ];
  const paiementColumns: Column<Paiement>[] = [
    { key: "code", header: t("comptabilite.col.code"), sortValue: (p) => p.code, render: (p) => p.code },
    { key: "date", header: t("comptabilite.col.date"), sortValue: (p) => p.date, render: (p) => <span className="r3-nowrap">{formatDate(p.date, i18n.language)}</span> },
    { key: "sens", header: t("comptabilite.col.direction"), render: (p) => t(`comptabilite.sens_${p.sens}`) },
    { key: "mode", header: t("comptabilite.col.mode"), render: (p) => t(`comptabilite.mode_${p.mode}`) },
    {
      key: "tiers",
      header: t("comptabilite.col.party"),
      render: (p) => (
        <>
          {p.tiers_name ?? "—"}
          {p.imputation_618 ? <Badge tone="neutral">618</Badge> : null}
        </>
      ),
    },
    {
      key: "montant",
      header: t("comptabilite.col.amount"),
      num: true,
      sortValue: (p) => (p.has_amount_access && p.montant !== null ? Number(p.montant) : null),
      render: (p) => (p.has_amount_access && p.montant !== null ? formatMoney(p.montant) : masque),
    },
    { key: "ecriture", header: t("comptabilite.col.entry"), render: (p) => p.move_number ?? "—" },
    {
      key: "statut",
      header: t("comptabilite.col.status"),
      render: (p) => (
        <Badge tone={p.statut === "valide" ? "ok" : p.statut === "annule" ? "err" : "warn"}>{t(`comptabilite.paiement_statut.${p.statut}`)}</Badge>
      ),
    },
    actionsColumn<Paiement>(t("listes.col.actions"), (p) =>
      p.statut === "brouillon"
        ? [
            { label: t("actions.comptabiliser"), path: `/api/comptabilite/paiements/${p.id}/comptabiliser/`, confirm: t("comptabilite.act.confirmComptabiliser") },
            { label: t("comptabilite.act.annuler"), path: `/api/comptabilite/paiements/${p.id}/annuler/`, tone: "danger" },
          ]
        : [],
    ),
  ];
  const tvaColumns: Column<DeclarationTva>[] = [
    { key: "code", header: t("comptabilite.col.code"), render: (d) => d.code },
    { key: "mois", header: t("listes.compta.mois"), sortValue: (d) => d.mois, render: (d) => formatDate(d.mois) },
    { key: "taux", header: t("listes.compta.taux"), render: (d) => d.taux_tva_code },
    { key: "base", header: t("listes.compta.base"), num: true, render: (d) => montantTva(d, d.base_imposable) },
    { key: "collectee", header: t("listes.compta.collectee"), num: true, render: (d) => montantTva(d, d.tva_collectee) },
    { key: "deductible", header: t("listes.compta.deductible"), num: true, render: (d) => montantTva(d, d.tva_deductible) },
    { key: "net", header: t("listes.compta.net"), num: true, render: (d) => montantTva(d, d.net_a_payer) },
    { key: "statut", header: t("listes.compta.statut"), render: (d) => <Badge tone={d.statut === "deposee" ? "ok" : "warn"}>{t(`comptabilite.tva_statut.${d.statut}`)}</Badge> },
  ];
  const controleColumns: Column<ControleInterne>[] = [
    { key: "code", header: t("comptabilite.col.code"), render: (c) => c.code },
    { key: "libelle", header: t("listes.compta.controle"), render: (c) => c.libelle },
    { key: "ref", header: t("listes.compta.reference"), render: (c) => referenceProcedure(c.reference_procedure, t) },
    { key: "resp", header: t("listes.compta.responsable"), render: (c) => nomPersonne(t, c.responsable_name) },
    { key: "date", header: t("listes.compta.datePrevue"), sortValue: (c) => c.date_prevue, render: (c) => formatDate(c.date_prevue) },
    {
      key: "statut",
      header: t("listes.compta.statut"),
      render: (c) => (
        <Badge tone={c.statut === "cloture" ? "ok" : c.statut === "realise" ? "brand" : "warn"}>{t(`comptabilite.controle_statut.${c.statut}`)}</Badge>
      ),
    },
  ];

  return (
    <div className="listes-page">
      <PageHeader
        title={t("comptabilite.title")}
        subtitle={t("listes.sub.comptabilite")}
        actions={
          <QuickForm
            title={t("comptabilite.form.title")}
            endpoint="/api/comptabilite/paiements/"
            fields={[
              {
                name: "sens",
                label: t("comptabilite.col.direction"),
                type: "select",
                required: true,
                defaultValue: "sortie",
                options: ["sortie", "entree"].map((v) => ({ value: v, label: t(`comptabilite.sens_${v}`) })),
              },
              {
                name: "mode",
                label: t("comptabilite.col.mode"),
                type: "select",
                required: true,
                defaultValue: "virement",
                options: ["virement", "cheque", "especes", "cfonb", "autre"].map((v) => ({ value: v, label: t(`comptabilite.mode_${v}`) })),
              },
              { name: "montant", label: t("comptabilite.col.amount"), type: "number", required: true, min: 0, step: "0.01" },
              { name: "date", label: t("comptabilite.col.date"), type: "date", required: true, defaultValue: new Date().toLocaleDateString("sv-SE") },
              {
                name: "compte_bancaire",
                label: t("comptabilite.col.bank"),
                type: "select",
                options: banquesAll.map((b) => ({ value: b.id, label: `${b.code} · ${b.label}` })),
              },
              {
                name: "engagement",
                label: t("comptabilite.form.engagement"),
                type: "select",
                options: (engagementsTous.data ?? []).filter((e) => e.statut === "approuve").map((e) => ({ value: e.id, label: `${e.code} · ${e.objet}` })),
              },
              { name: "reference", label: t("comptabilite.form.reference") },
              {
                name: "analytic_account",
                label: t("ecarts_m10.paiement.analytique"),
                type: "select",
                options: (analytiques.data ?? []).map((a) => ({ value: String(a.id), label: `${a.code} · ${a.label}` })),
              },
              { name: "retenue_source", label: t("ecarts_m10.paiement.retenue"), type: "select", options: [{ value: "true", label: t("ecarts_m10.paiement.oui") }] },
            ]}
          />
        }
      />

      <SectionNav
        items={[
          { id: "cpt-tresorerie", label: t("premiumVague2.sections.comptabilite.tresorerie") },
          { id: "cpt-facturation", label: t("premiumVague2.sections.comptabilite.facturation") },
          { id: "cpt-lettrage", label: t("premiumVague2.sections.comptabilite.lettrage") },
          { id: "cpt-etats", label: t("premiumVague2.sections.comptabilite.etats") },
          { id: "cpt-devises", label: t("premiumVague2.sections.comptabilite.devises") },
          { id: "cpt-cloture", label: t("premiumVague2.sections.comptabilite.cloture") },
          { id: "cpt-parametres", label: t("premiumKit.moduleSettings.nav") },
        ]}
      />

      <div className="kpi-grid">
        <Kpi
          label={t("comptabilite.banques")}
          value={banquesAll.length}
          hint={t("revueR3.compta.soldesOuverture", { montant: formatMoney(banquesAll.reduce((n, b) => n + Number(b.solde_initial || 0), 0)) })} icon={Landmark} tone="brand" delay={0} />
        <Kpi label={t("comptabilite.engagements")} value={enCours} hint={t("revueR3.compta.engagementsEnCours", { count: enCours })} icon={ClipboardList} tone="warn" delay={0.05} />
        <Kpi label={t("comptabilite.paiements")} value={valides.length} hint={t("comptabilite.paiementsValides")} icon={CreditCard} tone="brand" delay={0.1} />
        {tvaCalculees.length > 0 ? (
          <Kpi label={t("comptabilite.tva")} value={tvaDue} kind="money" hint={t("comptabilite.tvaDue")} icon={BadgePercent} tone="accent" delay={0.15} />
        ) : (
          <Kpi label={t("comptabilite.tva")} value={t("vague3C2.compta.aCalculer")} hint={t("vague3C2.compta.tvaACalculerHint")} icon={BadgePercent} tone="warn" delay={0.15} />
        )}
      </div>

      <div id="cpt-tresorerie" className="page-section">
      <section className="listes-block">
        <div className="list-toolbar">
          <SearchField value={engSearch} onChange={setEngSearch} placeholder={t("comptabilite.searchEngagements")} />
        </div>
        <Board label={t("listes.boardLabel.comptabilite")}>
          {ENG_ORDER.map((st, ci) => (
            <BoardColumn
              key={st}
              title={t(`comptabilite.engagement_statut.${st}`)}
              count={groups[st].length}
              tone={ENG_BADGE[st]}
              delay={ci * 0.04}
              limit={6}
              summary={groups[st].length ? formatMoney(groups[st].reduce((n, e) => n + Number(e.montant), 0)) : undefined}
            >
              {groups[st].map((e, i) => (
                <EngagementCard key={e.id} e={e} index={i} />
              ))}
            </BoardColumn>
          ))}
        </Board>
      </section>

      {banquesAll.length > 0 ? (
        <SectionCard title={`${t("listes.compta.banques")} · ${banquesAll.length}`}>
          <DataTable rows={banquesAll} columns={bankColumns} caption={t("listes.compta.banques")} />
        </SectionCard>
      ) : null}

      {(releves.count > 0 || releves.search) && (
        <SectionCard title={`${t("comptabilite.releves")} · ${releves.count}`}>
          <div className="list-toolbar">
            <SearchField value={releves.search} onChange={releves.setSearch} placeholder={t("comptabilite.searchReleves")} />
          </div>
          <DataGrid
            rows={relevesAll}
            columns={releveColumns}
            caption={t("comptabilite.releves")}
            loading={releves.query.isFetching}
            pagination={{ page: releves.page, pageSize: releves.pageSize, count: releves.count, onPageChange: releves.setPage, onPageSizeChange: releves.setPageSize }}
          />
        </SectionCard>
      )}

      {(paiements.count > 0 || paiements.search || filtresPai.extra) && (
        <SectionCard title={`${t("comptabilite.paiements")} · ${paiements.count}`}>
          <div className="list-toolbar">
            <SearchField value={paiements.search} onChange={paiements.setSearch} placeholder={t("comptabilite.searchPaiements")} />
          </div>
          <FilterBar defs={filtresPai.defs} value={filtresPai.criteres} onChange={filtresPai.setCriteres} idPrefix="pai-f" />
          <DataGrid
            rows={pay}
            columns={paiementColumns}
            caption={t("comptabilite.paiements")}
            loading={paiements.query.isFetching}
            pagination={{ page: paiements.page, pageSize: paiements.pageSize, count: paiements.count, onPageChange: paiements.setPage, onPageSizeChange: paiements.setPageSize }}
          />
        </SectionCard>
      )}

      <BanqueSection />
      </div>

      <div id="cpt-facturation" className="page-section">
      <FacturationSection />
      <RetenuesGarantieSection />
      </div>

      <div id="cpt-lettrage" className="page-section">
      <LettrageSection />
      </div>

      <div id="cpt-etats" className="page-section">
      <EcartsM10Section />
      {tvaAll.length > 0 ? (
        <SectionCard title={`${t("listes.compta.tva")} · ${tvaAll.length}`}>
          <DataTable rows={tvaAll} columns={tvaColumns} caption={t("listes.compta.tva")} />
        </SectionCard>
      ) : null}

      {controlesAll.length > 0 ? (
        <SectionCard title={`${t("listes.compta.controles")} · ${controlesAll.length}`}>
          <DataTable rows={controlesAll} columns={controleColumns} caption={t("listes.compta.controles")} />
        </SectionCard>
      ) : null}
      </div>

      <div id="cpt-devises" className="page-section">
      <EcartsA2Section />
      </div>

      <div id="cpt-cloture" className="page-section">
      <ClotureSection />
      </div>

      <ModuleSettings id="cpt-parametres">
        <GabaritsEtatsSection />
        <ImportGrandLivreSection />
      </ModuleSettings>
    </div>
  );
}
