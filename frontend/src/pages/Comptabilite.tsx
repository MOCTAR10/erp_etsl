import { useQuery } from "@tanstack/react-query";
import { BadgePercent, ClipboardList, CreditCard, Inbox, Landmark } from "lucide-react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { ActionBar, Badge, Board, BoardCard, BoardColumn, BoardSkeleton, EmptyState, ErrorState, Kpi, PageHeader, QuickForm, SectionCard } from "../components/ui";
import { LettrageSection } from "../components/workflow/LettrageSection";
import { formatDate, formatNumber } from "../lib/format";
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

const ENG_BADGE: Record<StatutEngagement, "ok" | "warn" | "err" | "brand"> = {
  brouillon: "warn",
  soumis: "brand",
  approuve: "ok",
  annule: "err",
};
const ENG_ORDER: StatutEngagement[] = ["brouillon", "soumis", "approuve", "annule"];
const ENG_VALID = new Set<StatutEngagement>(ENG_ORDER);

function BankCard({ b }: { b: CompteBancaire }) {
  const { t } = useTranslation();
  return (
    <div className="card kpi" key={b.id}>
      <span className="kpi-label">
        {b.code} · {t("comptabilite.banque")} {b.banque} · {t("comptabilite.compte")} {b.compte_comptable_code}
      </span>
      <span className="kpi-value">{b.label}</span>
      <span className="meta muted">
        {b.numero ? `${t("comptabilite.reference")} ${b.numero} · ` : ""}
        {t("comptabilite.soldeInitial")} {formatNumber(b.solde_initial)} F
      </span>
    </div>
  );
}

function EngagementCard({ e, index }: { e: Engagement; index: number }) {
  const { t } = useTranslation();
  return (
    <BoardCard delay={Math.min(index * 0.03, 0.3)}>
      <div className="title">
        {e.code} <span className="muted">· {e.compte_depense_code ?? "—"}</span>
      </div>
      <div className="meta">{e.objet}</div>
      <div className="meta">
        {formatNumber(e.montant)} F · {t("comptabilite.totalDepenses")} {formatNumber(e.total_paye)} F
        {e.fournisseur_name ? ` · ${e.fournisseur_name}` : ""}
      </div>
      <ActionBar
        actions={[
          ...(e.statut === "brouillon"
            ? [{ label: t("comptabilite.act.soumettre"), path: `/api/comptabilite/engagements/${e.id}/soumettre/`, tone: "ghost" as const }]
            : []),
          ...(e.statut === "soumis"
            ? [{ label: t("comptabilite.act.approuver"), path: `/api/comptabilite/engagements/${e.id}/approuver/` }]
            : []),
          ...(e.statut === "brouillon" || e.statut === "soumis"
            ? [{ label: t("comptabilite.act.annuler"), path: `/api/comptabilite/engagements/${e.id}/annuler/`, tone: "danger" as const, confirm: t("comptabilite.act.confirmAnnuler") }]
            : []),
        ]}
      />
    </BoardCard>
  );
}

function TvaCard({ d }: { d: DeclarationTva }) {
  const { t } = useTranslation();
  const badge = d.statut === "deposee" ? "ok" : "warn";
  return (
    <div className="card kpi" key={d.id}>
      <span className="kpi-label">
        {d.code} · {formatDate(d.mois)} · {d.taux_tva_code}{" "}
        <span className={`badge ${badge}`}>{t(`comptabilite.tva_statut.${d.statut}`)}</span>
      </span>
      <span className="meta muted">
        {d.has_amount_access ? (
          <>
            {formatNumber(d.base_imposable)} {t("comptabilite.baseImposable")} ·{" "}
            {formatNumber(d.tva_collectee)} {t("comptabilite.tvaCollectee")} ·{" "}
            {formatNumber(d.tva_deductible)} {t("comptabilite.tvaDeductible")}
          </>
        ) : (
          "••••••"
        )}
      </span>
      {d.has_amount_access ? (
        <span className="meta muted">{t("comptabilite.tvaNet")} {formatNumber(d.net_a_payer)} F</span>
      ) : (
        <span className="meta muted">••••••</span>
      )}
    </div>
  );
}

function ControleCard({ c }: { c: ControleInterne }) {
  const { t } = useTranslation();
  const badge = c.statut === "cloture" ? "ok" : c.statut === "realise" ? "brand" : "warn";
  return (
    <div className="card kpi" key={c.id}>
      <span className="kpi-label">
        {c.code} · {t("comptabilite.procedure")} {c.reference_procedure || "—"}{" "}
        <span className={`badge ${badge}`}>{t(`comptabilite.controle_statut.${c.statut}`)}</span>
      </span>
      <span className="kpi-value">{c.libelle}</span>
      <span className="meta muted">
        {c.responsable_name ? ` · ${c.responsable_name}` : ""}
        {c.date_prevue ? ` · ${formatDate(c.date_prevue)}` : ""}
      </span>
    </div>
  );
}

export function ComptabilitePage() {
  const { t, i18n } = useTranslation();

  const banques = useQuery({
    queryKey: ["compta-banques"],
    queryFn: () => api.comptesBancaires("?page_size=50"),
    select: (page: Paginated<CompteBancaire>) => page.results,
  });

  const paiements = useQuery({
    queryKey: ["compta-paiements"],
    queryFn: () => api.paiements("?page_size=50"),
    select: (page: Paginated<Paiement>) => page.results,
  });

  const engagements = useQuery({
    queryKey: ["compta-engagements"],
    queryFn: () => api.engagements("?page_size=100"),
    select: (page: Paginated<Engagement>) => {
      const groups: EngagementGroups = { brouillon: [], soumis: [], approuve: [], annule: [] };
      for (const e of page.results) {
        if (ENG_VALID.has(e.statut)) groups[e.statut].push(e);
      }
      return groups;
    },
  });

  const tva = useQuery({
    queryKey: ["compta-tva"],
    queryFn: () => api.declarationsTva("?page_size=50"),
    select: (page: Paginated<DeclarationTva>) => page.results,
  });

  const controles = useQuery({
    queryKey: ["compta-controles"],
    queryFn: () => api.controlesCompta("?page_size=50"),
    select: (page: Paginated<ControleInterne>) => page.results,
  });

  const releves = useQuery({
    queryKey: ["compta-releves"],
    queryFn: () => api.relevesBancaires("?page_size=50"),
    select: (page: Paginated<ReleveBancaire>) => page.results,
  });

  if (paiements.isLoading || engagements.isLoading || !paiements.data || !engagements.data)
    return <BoardSkeleton cols={4} rows={3} />;

  if (paiements.isError || engagements.isError || !tva.data || !controles.data)
    return (
      <ErrorState
        message={t("common.error")}
        onRetry={() => {
          void banques.refetch();
          void paiements.refetch();
          void engagements.refetch();
          void tva.refetch();
          void controles.refetch();
          void releves.refetch();
        }}
        retryLabel={t("common.retry")}
      />
    );

  const pay = paiements.data;
  const groups = engagements.data;
  const tvaAll = tva.data;
  const controlesAll = controles.data;
  const relevesAll = releves.data ?? [];
  const banquesAll = banques.data ?? [];
  const valides = pay.filter((p) => p.statut === "valide");
  const tvaDue = tvaAll.reduce(
    (acc, d) => acc + (d.has_amount_access && d.net_a_payer !== null ? Number(d.net_a_payer) : 0),
    0,
  );
  const enCours = groups["brouillon"].length + groups["soumis"].length;

  return (
    <>
      <PageHeader title={t("comptabilite.title")} />
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
            options: groups.approuve.map((e) => ({ value: e.id, label: `${e.code} · ${e.objet}` })),
          },
          { name: "reference", label: t("comptabilite.form.reference") },
        ]}
      />

      <div className="kpi-grid">
        <Kpi label={t("comptabilite.banques")} value={banquesAll.length} hint={`512 · ${t("comptabilite.compte")}`} icon={Landmark} tone="brand" delay={0} />
        <Kpi label={t("comptabilite.engagements")} value={enCours} hint={t("comptabilite.engagementsEnCours")} icon={ClipboardList} tone="warn" delay={0.05} />
        <Kpi label={t("comptabilite.paiements")} value={valides.length} hint={t("comptabilite.paiementsValides")} icon={CreditCard} tone="brand" delay={0.1} />
        <Kpi label={t("comptabilite.tva")} value={`${formatNumber(tvaDue)} F`} hint={t("comptabilite.tvaDue")} icon={BadgePercent} tone="accent" delay={0.15} />
      </div>

      <div style={{ overflowX: "auto" }}>
        <Board>
          {ENG_ORDER.map((st, ci) => (
            <BoardColumn
              key={st}
              title={t(`comptabilite.engagement_statut.${st}`)}
              count={groups[st].length}
              tone={ENG_BADGE[st]}
              delay={ci * 0.05}
              minWidth={260}
            >
              {groups[st].length === 0 ? (
                <EmptyState icon={Inbox} label={t("common.empty")} />
              ) : (
                groups[st].map((e, i) => <EngagementCard key={e.id} e={e} index={i} />)
              )}
            </BoardColumn>
          ))}
        </Board>
      </div>

      <p className="muted" style={{ marginTop: "0.5rem" }}>
        {t("comptabilite.pendingNote")}
      </p>

      {banquesAll.length > 0 ? (
        <>
          <h3 className="section-heading">
            {t("comptabilite.banques")} · {banquesAll.length}
          </h3>
          <div className="card-list">
            {banquesAll.map((b) => <BankCard key={b.id} b={b} />)}
          </div>
        </>
      ) : null}

      {relevesAll.length > 0 && (
        <SectionCard title={`${t("comptabilite.releves")} · ${relevesAll.length}`}>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>{t("comptabilite.col.code")}</th>
                  <th>{t("comptabilite.col.bank")}</th>
                  <th>{t("comptabilite.col.period")}</th>
                  <th className="num">{t("comptabilite.col.debit")}</th>
                  <th className="num">{t("comptabilite.col.credit")}</th>
                  <th>{t("comptabilite.col.status")}</th>
                </tr>
              </thead>
              <tbody>
                {relevesAll.map((r) => (
                  <tr key={r.id}>
                    <td>{r.code}</td>
                    <td>{r.compte_bancaire_label}</td>
                    <td>
                      {formatDate(r.date_debut, i18n.language)} → {formatDate(r.date_fin, i18n.language)}
                    </td>
                    <td className="num">{formatNumber(r.total_debit)}</td>
                    <td className="num">{formatNumber(r.total_credit)}</td>
                    <td>
                      <Badge tone={r.statut === "valide" ? "ok" : "warn"}>{t(`comptabilite.releve_statut.${r.statut}`)}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SectionCard>
      )}

      {pay.length > 0 && (
        <SectionCard title={`${t("comptabilite.paiements")} · ${pay.length}`}>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>{t("comptabilite.col.code")}</th>
                  <th>{t("comptabilite.col.date")}</th>
                  <th>{t("comptabilite.col.direction")}</th>
                  <th>{t("comptabilite.col.mode")}</th>
                  <th>{t("comptabilite.col.party")}</th>
                  <th className="num">{t("comptabilite.col.amount")}</th>
                  <th>{t("comptabilite.col.entry")}</th>
                  <th>{t("comptabilite.col.status")}</th>
                </tr>
              </thead>
              <tbody>
                {pay.map((p) => (
                  <tr key={p.id}>
                    <td>{p.code}</td>
                    <td>{formatDate(p.date, i18n.language)}</td>
                    <td>{t(`comptabilite.sens_${p.sens}`)}</td>
                    <td>{t(`comptabilite.mode_${p.mode}`)}</td>
                    <td>
                      {p.tiers_name ?? "—"}
                      {p.imputation_618 ? " · 618" : ""}
                    </td>
                    <td className="num">
                      {p.has_amount_access && p.montant !== null ? `${formatNumber(p.montant)} F` : "••••••"}
                    </td>
                    <td>{p.move_number ?? "—"}</td>
                    <td>
                      <Badge tone={p.statut === "valide" ? "ok" : p.statut === "annule" ? "err" : "warn"}>
                        {t(`comptabilite.paiement_statut.${p.statut}`)}
                      </Badge>
                      {p.statut === "brouillon" && (
                        <ActionBar
                          actions={[
                            { label: t("actions.comptabiliser"), path: `/api/comptabilite/paiements/${p.id}/comptabiliser/`, confirm: t("comptabilite.act.confirmComptabiliser") },
                            { label: t("comptabilite.act.annuler"), path: `/api/comptabilite/paiements/${p.id}/annuler/`, tone: "danger" },
                          ]}
                        />
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SectionCard>
      )}

      <LettrageSection />

      {tvaAll.length > 0 ? (
        <>
          <h3 className="section-heading">
            {t("comptabilite.tva")} · {tvaAll.length}
          </h3>
          <div className="card-list">
            {tvaAll.map((d) => <TvaCard key={d.id} d={d} />)}
          </div>
        </>
      ) : null}

      {controlesAll.length > 0 ? (
        <>
          <h3 className="section-heading">
            {t("comptabilite.controles")} · {controlesAll.length}
          </h3>
          <div className="card-list">
            {controlesAll.map((c) => <ControleCard key={c.id} c={c} />)}
          </div>
        </>
      ) : null}
    </>
  );
}