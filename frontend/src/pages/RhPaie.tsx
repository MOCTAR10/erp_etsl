import { useQuery } from "@tanstack/react-query";
import { motion } from "motion/react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { formatDate, formatNumber } from "../lib/format";
import { motionTokens } from "../theme/tokens";
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

function CongeCard({ c }: { c: DemandeConge }) {
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
        {c.code} <span className="muted">· {t(`rhPaie.conges_types.${c.type}`)}</span>
      </div>
      <div className="meta">{c.employe_nom}</div>
      <div className="meta">
        {formatDate(c.date_debut, "fr")} → {formatDate(c.date_fin, "fr")} · {c.nb_jours} j
        {c.motif ? ` · ${c.motif}` : ""}
      </div>
    </motion.div>
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
    return <p className="muted">{t("common.loading")}</p>;
  if (stats.isError || conges.isError || !masse.data)
    return (
      <p>
        {t("common.error")}{" "}
        <button
          className="btn ghost"
          onClick={() => {
            void stats.refetch();
            void employes.refetch();
            void conges.refetch();
            void bulletins.refetch();
            void masse.refetch();
          }}
        >
          {t("common.retry")}
        </button>
      </p>
    );

  const s = stats.data;
  const employesAll = employes.data ?? [];
  const groups = conges.data;
  const bulletinsAll = bulletins.data ?? [];
  const m = masse.data;
  const enAttente = groups["demande"].length + groups["approuve"].length;

  return (
    <>
      <h2>{t("rhPaie.title")}</h2>

      <div className="kpis">
        <div className="card kpi">
          <span className="kpi-label">{t("rhPaie.effectif")}</span>
          <span className="kpi-value">{s.effectif}</span>
          <span className="meta muted">{t("rhPaie.enConge")} · {s.en_conge} · {t("rhPaie.contratsExpirants")} · {s.contrats_expirants_30}</span>
        </div>
        <div className="card kpi">
          <span className="kpi-label">{t("rhPaie.congesEnAttente")}</span>
          <span className="kpi-value">{enAttente || s.conges_en_attente}</span>
          <span className="meta muted">{t("rhPaie.qualsExpirees")} · {s.qualifications_expirees}</span>
        </div>
        <div className="card kpi">
          <span className="kpi-label">{t("rhPaie.bulletinsMois")}</span>
          <span className="kpi-value">{s.bulletins_mois}</span>
          <span className="meta muted">{m.mois} · {t("rhPaie.masseBrute")} {formatNumber(m.brut_total)} F</span>
        </div>
        <div className="card kpi">
          <span className="kpi-label">{t("rhPaie.masseNette")}</span>
          <span className="kpi-value">{formatNumber(m.net_total)} F</span>
          <span className="meta muted">{t("rhPaie.bulletins")} · {m.bulletins}</span>
        </div>
      </div>

      <div className="board" style={{ overflowX: "auto" }}>
        {CONGE_ORDER.map((st) => (
          <motion.div
            key={st}
            layout
            className="board-col"
            style={{ minWidth: 240 }}
            initial={{ opacity: 0, y: motionTokens.distance.sm }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: motionTokens.duration.base, ease: motionTokens.ease.out }}
          >
            <div className="board-col-head">
              <span>{t(`rhPaie.conges_statut.${st}`)}</span>
              <span className={`badge ${CONGE_BADGE[st]}`}>{groups[st].length}</span>
            </div>
            {groups[st].length === 0 ? (
              <p className="muted" style={{ padding: "0.5rem 0.25rem" }}>
                {t("common.empty")}
              </p>
            ) : (
              groups[st].map((c) => <CongeCard key={c.id} c={c} />)
            )}
          </motion.div>
        ))}
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