import { useQuery } from "@tanstack/react-query";
import { motion } from "motion/react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { formatDate, formatNumber } from "../lib/format";
import { motionTokens } from "../theme/tokens";
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

function EngagementCard({ e }: { e: Engagement }) {
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
        {e.code} <span className="muted">· {e.compte_depense_code ?? "—"}</span>
      </div>
      <div className="meta">{e.objet}</div>
      <div className="meta">
        {formatNumber(e.montant)} F · {t("comptabilite.totalDepenses")} {formatNumber(e.total_paye)} F
        {e.fournisseur_name ? ` · ${e.fournisseur_name}` : ""}
      </div>
    </motion.div>
  );
}

function PaymentCard({ p }: { p: Paiement }) {
  const { t } = useTranslation();
  const badge =
    p.statut === "valide" ? "ok" : p.statut === "annule" ? "err" : "warn";
  return (
    <div className="card kpi" key={p.id}>
      <span className="kpi-label">
        {p.code} · {t(`comptabilite.sens_${p.sens}`)} · {t(`comptabilite.mode_${p.mode}`)}{" "}
        <span className={`badge ${badge}`}>{t(`comptabilite.paiement_statut.${p.statut}`)}</span>
      </span>
      <span className="kpi-value">
        {p.has_amount_access && p.montant !== null ? `${formatNumber(p.montant)} F` : "••••••"}
      </span>
      <span className="meta muted">
        {formatDate(p.date, "fr")}
        {p.tiers_name ? ` · ${p.tiers_name}` : ""}
        {p.imputation_618 ? ` · ${t("comptabilite.tva")} 618` : ""}
        {p.move_number ? ` · ${t("comptabilite.ecriture")} ${p.move_number}` : ""}
      </span>
    </div>
  );
}

function TvaCard({ d }: { d: DeclarationTva }) {
  const { t } = useTranslation();
  const badge = d.statut === "deposee" ? "ok" : "warn";
  return (
    <div className="card kpi" key={d.id}>
      <span className="kpi-label">
        {d.code} · {formatDate(d.mois, "fr")} · {d.taux_tva_code}{" "}
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
        {c.date_prevue ? ` · ${formatDate(c.date_prevue, "fr")}` : ""}
      </span>
    </div>
  );
}

export function ComptabilitePage() {
  const { t } = useTranslation();

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
    return <p className="muted">{t("common.loading")}</p>;

  if (paiements.isError || engagements.isError || !tva.data || !controles.data)
    return (
      <p>
        {t("common.error")}{" "}
        <button
          className="btn ghost"
          onClick={() => {
            void banques.refetch();
            void paiements.refetch();
            void engagements.refetch();
            void tva.refetch();
            void controles.refetch();
            void releves.refetch();
          }}
        >
          {t("common.retry")}
        </button>
      </p>
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
      <h2>{t("comptabilite.title")}</h2>

      <div className="kpis">
        <div className="card kpi">
          <span className="kpi-label">{t("comptabilite.banques")}</span>
          <span className="kpi-value">{banquesAll.length}</span>
          <span className="meta muted">512 · {t("comptabilite.compte")}</span>
        </div>
        <div className="card kpi">
          <span className="kpi-label">{t("comptabilite.engagements")}</span>
          <span className="kpi-value">{enCours}</span>
          <span className="meta muted">{t("comptabilite.engagementsEnCours")}</span>
        </div>
        <div className="card kpi">
          <span className="kpi-label">{t("comptabilite.paiements")}</span>
          <span className="kpi-value">{valides.length}</span>
          <span className="meta muted">{t("comptabilite.paiementsValides")}</span>
        </div>
        <div className="card kpi">
          <span className="kpi-label">{t("comptabilite.tva")}</span>
          <span className="kpi-value">{formatNumber(tvaDue)} F</span>
          <span className="meta muted">{t("comptabilite.tvaDue")}</span>
        </div>
      </div>

      <div className="board" style={{ overflowX: "auto" }}>
        {ENG_ORDER.map((st) => (
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
              <span>{t(`comptabilite.engagement_statut.${st}`)}</span>
              <span className={`badge ${ENG_BADGE[st]}`}>{groups[st].length}</span>
            </div>
            {groups[st].length === 0 ? (
              <p className="muted" style={{ padding: "0.5rem 0.25rem" }}>
                {t("common.empty")}
              </p>
            ) : (
              groups[st].map((e) => <EngagementCard key={e.id} e={e} />)
            )}
          </motion.div>
        ))}
      </div>

      <p className="muted" style={{ marginTop: "0.5rem" }}>
        {t("comptabilite.pendingNote")}
      </p>

      {banquesAll.length > 0 ? (
        <>
          <h3 className="muted" style={{ marginTop: "2rem" }}>
            {t("comptabilite.banques")} · {banquesAll.length}
          </h3>
          <div className="kpis" style={{ flexWrap: "wrap" }}>
            {banquesAll.map((b) => <BankCard key={b.id} b={b} />)}
          </div>
        </>
      ) : null}

      {relevesAll.length > 0 ? (
        <>
          <h3 className="muted" style={{ marginTop: "2rem" }}>
            {t("comptabilite.releves")} · {relevesAll.length}
          </h3>
          <div className="kpis" style={{ flexWrap: "wrap" }}>
            {relevesAll.map((r) => (
              <div className="card kpi" key={r.id}>
                <span className="kpi-label">
                  {r.code} · {r.compte_bancaire_label}{" "}
                  <span className={`badge ${r.statut === "valide" ? "ok" : "warn"}`}>
                    {t(`comptabilite.releve_statut.${r.statut}`)}
                  </span>
                </span>
                <span className="meta muted">
                  {formatDate(r.date_debut, "fr")} → {formatDate(r.date_fin, "fr")}
                </span>
                <span className="meta muted">
                  D {formatNumber(r.total_debit)} · C {formatNumber(r.total_credit)} F
                </span>
              </div>
            ))}
          </div>
        </>
      ) : null}

      {pay.length > 0 ? (
        <>
          <h3 className="muted" style={{ marginTop: "2rem" }}>
            {t("comptabilite.paiements")} · {pay.length}
          </h3>
          <div className="kpis" style={{ flexWrap: "wrap" }}>
            {pay.map((p) => <PaymentCard key={p.id} p={p} />)}
          </div>
        </>
      ) : null}

      {tvaAll.length > 0 ? (
        <>
          <h3 className="muted" style={{ marginTop: "2rem" }}>
            {t("comptabilite.tva")} · {tvaAll.length}
          </h3>
          <div className="kpis" style={{ flexWrap: "wrap" }}>
            {tvaAll.map((d) => <TvaCard key={d.id} d={d} />)}
          </div>
        </>
      ) : null}

      {controlesAll.length > 0 ? (
        <>
          <h3 className="muted" style={{ marginTop: "2rem" }}>
            {t("comptabilite.controles")} · {controlesAll.length}
          </h3>
          <div className="kpis" style={{ flexWrap: "wrap" }}>
            {controlesAll.map((c) => <ControleCard key={c.id} c={c} />)}
          </div>
        </>
      ) : null}
    </>
  );
}