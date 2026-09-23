import { useQuery } from "@tanstack/react-query";
import { motion } from "motion/react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { formatNumber } from "../lib/format";
import { motionTokens } from "../theme/tokens";
import type {
  AlertesResult,
  Assurance,
  BandeEcheance,
  Caution,
  Contentieux,
  Convention,
  Courrier,
  DossierGlobalRental,
  JuridiqueStats,
  Paginated,
  Reunion,
  StatutAssurance,
  StatutCaution,
  StatutConvention,
} from "../types";

const BANDE_BADGE: Record<BandeEcheance, "ok" | "warn" | "err"> = {
  j90: "ok",
  j60: "warn",
  j30: "warn",
  expiree: "err",
};
const BANDES: BandeEcheance[] = ["expiree", "j30", "j60", "j90"];

function ConventionCard({ c }: { c: Convention }) {
  const { t } = useTranslation();
  const badge =
    c.statut === "signe"
      ? c.a_renouveler
        ? "warn"
        : "ok"
      : c.statut === "cloture" || c.statut === "resilie"
        ? "err"
        : "warn";
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: motionTokens.distance.xs, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: motionTokens.duration.base, ease: motionTokens.ease.out }}
      className="task-card"
    >
      <div className="title">
        {c.code} <span className="muted">· {c.type_label}</span>
      </div>
      <div className="meta">{c.titre}</div>
      <div className="meta">
        {c.has_amount_access && c.montant !== null ? `${formatNumber(c.montant)} F` : "••••••"} ·{" "}
        {c.partenaire_name ?? "—"}
      </div>
      <div className="meta">
        <span className={`badge ${badge}`}>{t(`juridique.statut_convention.${c.statut}`)}</span>{" "}
        {c.date_fin ? (
          <span className="muted">
            {c.date_fin} · {c.days_left !== null ? `${c.days_left} ${t("juridique.jours")}` : "—"}
          </span>
        ) : null}
      </div>
    </motion.div>
  );
}

function CautionCard({ c }: { c: Caution }) {
  const { t } = useTranslation();
  const badge: Record<StatutCaution, "ok" | "warn" | "err"> = {
    en_cours: "ok",
    levee: "warn",
    appelee: "err",
    expiree: "err",
  };
  return (
    <div className="card kpi" key={c.id}>
      <span className="kpi-label">
        {c.code} · {c.type_label} <span className={`badge ${badge[c.statut]}`}>{t(`juridique.statut_caution.${c.statut}`)}</span>
      </span>
      <span className="kpi-value">
        {c.has_amount_access && c.montant !== null ? formatNumber(c.montant) : "••••••"} F
      </span>
      <span className="meta muted">
        {c.beneficiaire} · {c.date_echeance} · {c.days_left !== null ? `${c.days_left} ${t("juridique.jours")}` : "—"}
      </span>
    </div>
  );
}

function AssuranceCard({ a }: { a: Assurance }) {
  const { t } = useTranslation();
  const badge: Record<StatutAssurance, "ok" | "warn" | "err"> = {
    active: "ok",
    a_renouveler: "warn",
    expiree: "err",
    resiliee: "err",
  };
  return (
    <div className="card kpi" key={a.id}>
      <span className="kpi-label">
        {a.code} · {a.type_label} · {a.numero_police}{" "}
        <span className={`badge ${badge[a.statut]}`}>{t(`juridique.statut_assurance.${a.statut}`)}</span>
      </span>
      <span className="kpi-value">
        {a.has_amount_access && a.prime_annuelle !== null ? formatNumber(a.prime_annuelle) : "••••••"} F
      </span>
      <span className="meta muted">
        {a.assureur_name ?? "—"} · {a.date_echeance} · {a.days_left !== null ? `${a.days_left} ${t("juridique.jours")}` : "—"}
      </span>
    </div>
  );
}

export function JuridiquePage() {
  const { t } = useTranslation();

  const stats = useQuery({
    queryKey: ["juridique-stats"],
    queryFn: () => api.juridiqueStats(),
  });

  const alertes = useQuery({
    queryKey: ["juridique-alertes"],
    queryFn: () => api.alertesJuridique(),
  });

  const courriers = useQuery({
    queryKey: ["juridique-courriers"],
    queryFn: () => api.courriersJuridique("?page_size=50"),
    select: (page: Paginated<Courrier>) => page.results,
  });

  const conventions = useQuery({
    queryKey: ["juridique-conventions"],
    queryFn: () => api.conventionsJuridique("?page_size=100"),
    select: (page: Paginated<Convention>) => page.results,
  });

  const cautions = useQuery({
    queryKey: ["juridique-cautions"],
    queryFn: () => api.cautionsJuridique("?page_size=50"),
    select: (page: Paginated<Caution>) => page.results,
  });

  const assurances = useQuery({
    queryKey: ["juridique-assurances"],
    queryFn: () => api.assurancesJuridique("?page_size=50"),
    select: (page: Paginated<Assurance>) => page.results,
  });

  const contentieux = useQuery({
    queryKey: ["juridique-contentieux"],
    queryFn: () => api.contentieuxJuridique("?page_size=50"),
    select: (page: Paginated<Contentieux>) => page.results,
  });

  const reunions = useQuery({
    queryKey: ["juridique-reunions"],
    queryFn: () => api.reunionsJuridique("?page_size=50"),
    select: (page: Paginated<Reunion>) => page.results,
  });

  const dossiersGr = useQuery({
    queryKey: ["juridique-dossiers-gr"],
    queryFn: () => api.dossiersGrJuridique("?page_size=50"),
    select: (page: Paginated<DossierGlobalRental>) => page.results,
  });

  const loading =
    !stats.data || alertes.isLoading || conventions.isLoading || cautions.isLoading || assurances.isLoading;

  if (loading) return <p className="muted">{t("common.loading")}</p>;

  if (alertes.isError || conventions.isError)
    return (
      <p>
        {t("common.error")}{" "}
        <button
          className="btn ghost"
          onClick={() => {
            void stats.refetch();
            void alertes.refetch();
            void courriers.refetch();
            void conventions.refetch();
            void cautions.refetch();
            void assurances.refetch();
            void contentieux.refetch();
            void reunions.refetch();
            void dossiersGr.refetch();
          }}
        >
          {t("common.retry")}
        </button>
      </p>
    );

  const s = stats.data as JuridiqueStats;
  const a = alertes.data as AlertesResult;
  const convs = conventions.data ?? [];
  const cautionsList = cautions.data ?? [];
  const assurancesList = assurances.data ?? [];
  const courts = courriers.data ?? [];
  const litiges = contentieux.data ?? [];
  const reunionsList = reunions.data ?? [];
  const grs = dossiersGr.data ?? [];

  return (
    <>
      <h2>{t("juridique.title")}</h2>

      <div className="kpis">
        <div className="card kpi">
          <span className="kpi-label">{t("juridique.alertes")}</span>
          <span className="kpi-value">{a.total}</span>
          <span className="meta muted">
            <span className="badge err">{a.compteurs["expiree"]}</span> {t("juridique.echeanceExpi")}
            {" · "}
            <span className="badge warn">{a.compteurs["j30"]}</span> {t("juridique.echeanceJ30")}
            {" · "}
            <span className="badge warn">{a.compteurs["j60"]}</span> {t("juridique.echeanceJ60")}
            {" · "}
            <span className="badge ok">{a.compteurs["j90"]}</span> {t("juridique.echeanceJ90")}
          </span>
        </div>
        <div className="card kpi">
          <span className="kpi-label">{t("juridique.conventions")}</span>
          <span className="kpi-value">{s.conventions}</span>
          <span className="meta muted">{t("juridique.conventionsARenouveler")} {s.conventions_a_renouveler}</span>
        </div>
        <div className="card kpi">
          <span className="kpi-label">{t("juridique.contentieux")}</span>
          <span className="kpi-value">{s.contentieux_ouverts}</span>
          <span className="meta muted">{t("juridique.courriers")} {s.courriers}</span>
        </div>
        <div className="card kpi">
          <span className="kpi-label">{t("juridique.cautions")}</span>
          <span className="kpi-value">{s.cautions_en_cours}</span>
          <span className="meta muted">{t("juridique.assurances")} {s.assurances}</span>
        </div>
      </div>

      {a.total > 0 ? (
        <>
          <h3 className="muted" style={{ marginTop: "2rem" }}>
            {t("juridique.alertes")} · {a.total}
          </h3>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: "0.5rem" }}>
            {BANDES.flatMap((bande) =>
              [...a.conventions, ...a.cautions, ...a.assurances]
                .filter((el) => el.bande === bande)
                .map((el) => (
                  <div className="card kpi" key={`${el.type}-${el.code}`}>
                    <span className="kpi-label">
                      {t(`juridique.${el.type}`)} · {el.code}{" "}
                      <span className={`badge ${BANDE_BADGE[bande]}`}>{t(`juridique.bande.${bande}`)}</span>
                    </span>
                    <span className="kpi-value">{el.libelle}</span>
                    <span className="meta muted">
                      {el.date_echeance} · {el.jours} {t("juridique.jours")}
                    </span>
                  </div>
                ))
            )}
          </div>
        </>
      ) : null}

      {convs.length > 0 ? (
        <>
          <h3 className="muted" style={{ marginTop: "2rem" }}>
            {t("juridique.conventions")} · {convs.length}
          </h3>
          <div className="board" style={{ overflowX: "auto" }}>
            {(["signe", "en_signature", "brouillon", "cloture", "resilie"] as StatutConvention[]).map((st) => {
              const items = convs.filter((c) => c.statut === st);
              if (items.length === 0) return null;
              return (
                <motion.div key={st} layout className="board-col" style={{ minWidth: 280 }}>
                  <div className="board-col-head">
                    <span>{t(`juridique.statut_convention.${st}`)}</span>
                    <span className="badge warn">{items.length}</span>
                  </div>
                  {items.map((c) => (
                    <ConventionCard key={c.id} c={c} />
                  ))}
                </motion.div>
              );
            })}
          </div>
        </>
      ) : null}

      {cautionsList.length > 0 ? (
        <>
          <h3 className="muted" style={{ marginTop: "2rem" }}>
            {t("juridique.cautions")} · {cautionsList.length}
          </h3>
          <div className="kpis" style={{ flexWrap: "wrap" }}>
            {cautionsList.map((c) => (
              <CautionCard key={c.id} c={c} />
            ))}
          </div>
        </>
      ) : null}

      {assurancesList.length > 0 ? (
        <>
          <h3 className="muted" style={{ marginTop: "2rem" }}>
            {t("juridique.assurances")} · {assurancesList.length}
          </h3>
          <div className="kpis" style={{ flexWrap: "wrap" }}>
            {assurancesList.map((aPolicy) => (
              <AssuranceCard key={aPolicy.id} a={aPolicy} />
            ))}
          </div>
        </>
      ) : null}

      {litiges.length > 0 ? (
        <>
          <h3 className="muted" style={{ marginTop: "2rem" }}>
            {t("juridique.contentieux")} · {litiges.length}
          </h3>
          <table className="table">
            <thead>
              <tr>
                <th>Code</th>
                <th>{t("juridique.contentieuxType")}</th>
                <th>{t("juridique.cautionEchEntrant")}</th>
                <th>{t("juridique.statut_contentieux")}</th>
                <th>•</th>
              </tr>
            </thead>
            <tbody>
              {litiges.map((l) => (
                <tr key={l.id}>
                  <td>{l.code}</td>
                  <td>
                    {l.objet} <span className="muted">· {l.partie_adverse ?? "—"}</span>
                  </td>
                  <td>{l.phase_label}</td>
                  <td>
                    <span className="badge warn">{t(`juridique.statut_contentieux.${l.statut}`)}</span>
                  </td>
                  <td>{l.has_amount_access && l.montant_en_jeu !== null ? `${formatNumber(l.montant_en_jeu)} F` : "••••••"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      ) : null}

      {grs.length > 0 ? (
        <>
          <h3 className="muted" style={{ marginTop: "2rem" }}>
            GLOBAL RENTAL · {grs.length}
          </h3>
          <div className="kpis" style={{ flexWrap: "wrap" }}>
            {grs.map((g) => (
              <div className="card kpi" key={g.id}>
                <span className="kpi-label">
                  {g.code} · {g.signe_618 ? "618" : "—"} ·{" "}
                  <span className="badge warn">{t(`juridique.statut_gr.${g.statut}`)}</span>
                </span>
                <span className="kpi-value">
                  {g.has_amount_access && g.montant_estime !== null ? formatNumber(g.montant_estime) : "••••••"} F
                </span>
                <span className="meta muted">{g.objet} · {g.partenaire_gr_name}</span>
              </div>
            ))}
          </div>
        </>
      ) : null}

      {courts.length > 0 ? (
        <>
          <h3 className="muted" style={{ marginTop: "2rem" }}>
            {t("juridique.courriers")} · {courts.length}
          </h3>
          <table className="table">
            <thead>
              <tr>
                <th>Code</th>
                <th>{t("juridique.courier")}</th>
                <th>Tiers</th>
                <th>{t("juridique.statut_courrier")}</th>
              </tr>
            </thead>
            <tbody>
              {courts.map((c) => (
                <tr key={c.id}>
                  <td>{c.code}</td>
                  <td>{c.objet}</td>
                  <td>{c.tiers_name ?? "—"}</td>
                  <td>
                    <span className="badge ok">{t(`juridique.statut_courrier.${c.statut}`)}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      ) : null}

      {reunionsList.length > 0 ? (
        <>
          <h3 className="muted" style={{ marginTop: "2rem" }}>
            {t("juridique.reunions")} · {reunionsList.length}
          </h3>
          <div className="kpis" style={{ flexWrap: "wrap" }}>
            {reunionsList.map((r) => (
              <div className="card kpi" key={r.id}>
                <span className="kpi-label">
                  {r.code} · {r.type_label} ·{" "}
                  <span className={`badge ${r.statut === "tenue" ? "ok" : r.statut === "cloturee" ? "err" : "warn"}`}>
                    {t(`juridique.statut_reunion.${r.statut}`)}
                  </span>
                </span>
                <span className="kpi-value">{r.objet}</span>
                <span className="meta muted">
                  {r.date_reunion} · {r.nb_decisions} décisions
                </span>
              </div>
            ))}
          </div>
        </>
      ) : null}

      <p className="muted" style={{ marginTop: "0.5rem" }}>
        {t("juridique.pendingNote")}
      </p>
    </>
  );
}