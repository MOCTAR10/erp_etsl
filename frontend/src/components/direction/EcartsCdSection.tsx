import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate, formatNumber } from "../../lib/format";
import { describeError } from "../../lib/offlineQueue";
import { ActionBar, Badge, SectionCard } from "../ui";

interface SemaineCf {
  semaine: number;
  debut: string;
  fin: string;
  encaissements: string;
  decaissements: string;
  flux_net: string;
  solde_fin: string;
}
interface SeuilBudget {
  budget: string;
  libelle: string;
  montant: string;
  realise: string;
  taux_pct: string;
  niveau: "alerte" | "atteint" | "depasse" | null;
}
interface Pilotage {
  cashflow: { ouverture: string; semaines: SemaineCf[]; solde_final: string; semaines_tension: number[] };
  pipe_budget: {
    annee: number;
    budget_produits: string;
    realise: string;
    pipe_pondere: { signe: string; en_cours: string; prospect: string; total: string };
    atterrissage: string;
    reste_a_couvrir: string;
    couverture_pct: string | null;
  };
  seuils_budget: SeuilBudget[];
  retention: { cubes: number; scelles: Record<string, number>; retention_financier_ans: string; retention_operationnel_ans: string };
  blocage_avant_cloture: boolean;
  voit_non_cloture: boolean;
  periodes_cloturees: string[];
  parametres_provisoires: boolean;
}
interface Scelle {
  id: string;
  mart: string;
  type_donnees: string;
  nb_lignes: number;
  sha256: string;
  conserve_jusqu_au: string;
  integre: boolean;
  created_at: string;
}
interface AlerteCal {
  type: string;
  code: string;
  libelle: string;
  date_echeance: string;
  jours: number;
  bande: string;
}
interface IndicateursCommerciaux {
  prix_moyen: string | null;
  offres_gagnees: number;
  taux_transformation_pct: string | null;
  score_moyen: string | null;
  clients_sous_seuil: number;
  clients_70_plus: number;
}
interface ItpCnd {
  itp?: { plans: number; plans_approuves: number; points: number; points_arret_en_attente: number; points_leves: number; points_non_conformes: number; taux_levee: number };
  cnd?: { controles: number; en_cours: number; par_methode: Record<string, number>; conformes: number; sous_reserve: number; non_conformes: number; taux_rejet: number };
}

const fcfa = (v: string | null | undefined) => (v === null || v === undefined ? "—" : `${formatNumber(Number(v))} F`);
const pct = (v: number) => `${formatNumber(Math.round(v * 1000) / 10)} %`;
const TONE: Record<string, "warn" | "err" | "ok"> = { alerte: "warn", atteint: "warn", depasse: "err" };

/** Boutons d'export Excel / PDF (téléchargement authentifié, journalisé côté serveur). */
function Exports({ path, nom, label }: { path: string; nom: string; label: string }) {
  const { t } = useTranslation();
  const [error, setError] = useState<string | null>(null);
  const sep = path.includes("?") ? "&" : "?";
  const dl = (fmt: "xlsx" | "pdf") =>
    api.download(`${path}${sep}export=${fmt}`, `${nom}.${fmt}`).then(() => setError(null), (e) => setError(describeError(e)));
  return (
    <span className="export-group">
      <strong>{label}</strong>{" "}
      <button type="button" className="btn ghost" onClick={() => void dl("xlsx")}>{t("ecarts_cd.excel")}</button>{" "}
      <button type="button" className="btn ghost" onClick={() => void dl("pdf")}>{t("ecarts_cd.pdf")}</button>
      {error && <span className="action-error" role="alert"> {error}</span>}
    </span>
  );
}

/** Écarts Couche D : exports, reporting ITP / CND, alertes calendaires (tous) ; trésorerie, budget, scellés (montants). */
export function EcartsCdSection() {
  const { t } = useTranslation();
  const pilotage = useQuery({ queryKey: ["cd", "pilotage"], queryFn: () => api.get<Pilotage>("/api/analytics/pilotage/"), retry: 0 });
  const scelles = useQuery({
    queryKey: ["cd", "scelles"],
    queryFn: () => api.listAll<Scelle>("/api/analytics/marts/scelles/"),
    retry: 0,
    enabled: pilotage.isSuccess,
  });
  const calendrier = useQuery({
    queryKey: ["cd", "calendrier"],
    queryFn: () => api.get<{ items: AlerteCal[]; paliers: number[] }>("/api/analytics/alertes-calendaires/"),
    retry: 0,
  });
  const qualite = useQuery({ queryKey: ["cd", "itp-cnd"], queryFn: () => api.get<ItpCnd>("/api/analytics/petrolier/"), retry: 0 });
  const dashboard = useQuery({
    queryKey: ["cd", "commercial"],
    queryFn: () => api.get<{ commercial: { indicateurs?: IndicateursCommerciaux } }>("/api/analytics/dashboard/"),
    retry: 0,
  });
  const ic = dashboard.data?.commercial.indicateurs;
  const p = pilotage.data;
  const q = qualite.data;

  return (
    <>
      <SectionCard title={t("ecarts_cd.exports.title")}>
        <div className="action-bar-buttons" data-testid="exports-direction">
          <Exports path="/api/analytics/dashboard/" nom="tableau_direction" label={t("ecarts_cd.exports.direction")} />
          <Exports path="/api/analytics/petrolier/" nom="reporting_petrolier" label={t("ecarts_cd.exports.petrolier")} />
          {p && <Exports path="/api/analytics/cubes/?axes=periode,affaire" nom="cube_bi" label={t("ecarts_cd.exports.cube")} />}
          {p && <Exports path="/api/analytics/pilotage/" nom="pilotage_direction" label={t("ecarts_cd.exports.pilotage")} />}
        </div>
      </SectionCard>

      {ic && (
        <SectionCard title={t("ecarts_cd.commercial.title")}>
          <table className="table" data-testid="indicateurs-commerciaux">
            <tbody>
              <tr><td>{t("ecarts_cd.commercial.prixMoyen")}</td><td>{fcfa(ic.prix_moyen)} ({t("ecarts_cd.commercial.gagnees", { n: ic.offres_gagnees })}) <Badge tone="warn">{t("ecarts_cd.provisoire")}</Badge></td></tr>
              <tr><td>{t("ecarts_cd.commercial.transformation")}</td><td>{ic.taux_transformation_pct === null ? "—" : `${ic.taux_transformation_pct} %`}</td></tr>
              <tr><td>{t("ecarts_cd.commercial.score")}</td><td>{ic.score_moyen ?? "—"} · {t("ecarts_cd.commercial.sousSeuil", { n: ic.clients_sous_seuil })} · {t("ecarts_cd.commercial.plus70", { n: ic.clients_70_plus })}</td></tr>
            </tbody>
          </table>
        </SectionCard>
      )}

      {q?.itp && q.cnd && (
        <SectionCard title={t("ecarts_cd.itpCnd.title")}>
          <table className="table" data-testid="petrolier-itp-cnd">
            <tbody>
              <tr><td>{t("ecarts_cd.itpCnd.plans")}</td><td>{q.itp.plans} ({t("ecarts_cd.itpCnd.approuves", { n: q.itp.plans_approuves })})</td></tr>
              <tr><td>{t("ecarts_cd.itpCnd.points")}</td><td>{q.itp.points_leves} / {q.itp.points} · {pct(q.itp.taux_levee)}</td></tr>
              <tr><td>{t("ecarts_cd.itpCnd.arretsAttente")}</td><td>{q.itp.points_arret_en_attente}</td></tr>
              <tr><td>{t("ecarts_cd.itpCnd.pointsNc")}</td><td>{q.itp.points_non_conformes}</td></tr>
              <tr><td>{t("ecarts_cd.itpCnd.cnd")}</td><td>{q.cnd.controles} ({t("ecarts_cd.itpCnd.enCours", { n: q.cnd.en_cours })}) · {Object.entries(q.cnd.par_methode).map(([m, n]) => `${m} ${n}`).join(" · ") || "—"}</td></tr>
              <tr><td>{t("ecarts_cd.itpCnd.resultats")}</td><td>{q.cnd.conformes} / {q.cnd.sous_reserve} / {q.cnd.non_conformes}</td></tr>
              <tr><td>{t("ecarts_cd.itpCnd.rejet")}</td><td>{pct(q.cnd.taux_rejet)}</td></tr>
            </tbody>
          </table>
        </SectionCard>
      )}

      <SectionCard title={t("ecarts_cd.calendrier.title")}>
        <p className="muted">
          {t("ecarts_cd.calendrier.hint", { paliers: (calendrier.data?.paliers ?? []).map((n) => `J-${n}`).join(" / ") })}{" "}
          <Badge tone="warn">{t("ecarts_cd.provisoire")}</Badge>
        </p>
        <table className="table" data-testid="alertes-calendaires">
          <tbody>
            {(calendrier.data?.items ?? []).map((a, i) => (
              <tr key={`${a.type}-${a.code}-${i}`}>
                <td>{t(`ecarts_cd.calendrier.types.${a.type}`)}</td>
                <td>{a.code} · {a.libelle}</td>
                <td>{formatDate(a.date_echeance)}</td>
                <td><Badge tone={a.jours < 0 ? "err" : a.jours <= 30 ? "warn" : "ok"}>{a.jours < 0 ? t("ecarts_cd.calendrier.retard", { n: -a.jours }) : `J-${a.jours}`}</Badge></td>
              </tr>
            ))}
            {calendrier.data?.items.length === 0 && <tr><td className="muted">{t("ecarts_cd.calendrier.aucune")}</td></tr>}
          </tbody>
        </table>
      </SectionCard>

      {p && (
        <SectionCard title={t("ecarts_cd.pilotage.title")}>
          <div data-testid="pilotage-direction">
            {p.parametres_provisoires && (
              <p className="action-error" role="note" data-testid="alerte-provisoire-cd">{t("ecarts_cd.bandeau")}</p>
            )}
            <p className="muted" data-testid="publication-cloture">
              {p.blocage_avant_cloture ? t("ecarts_cd.publication.bloque") : t("ecarts_cd.publication.libre")}{" "}
              {p.voit_non_cloture && p.blocage_avant_cloture && <Badge tone="warn">{t("ecarts_cd.publication.producteur")}</Badge>}{" "}
              {t("ecarts_cd.publication.clotures", { liste: p.periodes_cloturees.join(", ") || "—" })}
            </p>

            <h4 className="subtitle">{t("ecarts_cd.cashflow.title")}</h4>
            <p className="muted">{t("ecarts_cd.cashflow.hint", { ouverture: fcfa(p.cashflow.ouverture) })}</p>
            <table className="table" data-testid="cashflow-13s">
              <thead>
                <tr>
                  <th>{t("ecarts_cd.cashflow.semaine")}</th>
                  <th>{t("ecarts_cd.cashflow.encaissements")}</th>
                  <th>{t("ecarts_cd.cashflow.decaissements")}</th>
                  <th>{t("ecarts_cd.cashflow.flux")}</th>
                  <th>{t("ecarts_cd.cashflow.solde")}</th>
                </tr>
              </thead>
              <tbody>
                {p.cashflow.semaines.map((s) => (
                  <tr key={s.semaine}>
                    <td>S{s.semaine} · {formatDate(s.debut)}</td>
                    <td>{fcfa(s.encaissements)}</td>
                    <td>{fcfa(s.decaissements)}</td>
                    <td>{fcfa(s.flux_net)}</td>
                    <td>{fcfa(s.solde_fin)} {Number(s.solde_fin) < 0 && <Badge tone="err">{t("ecarts_cd.cashflow.tension")}</Badge>}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            <h4 className="subtitle">{t("ecarts_cd.pipe.title", { annee: p.pipe_budget.annee })}</h4>
            <table className="table" data-testid="pipe-budget">
              <tbody>
                <tr><td>{t("ecarts_cd.pipe.budget")}</td><td>{fcfa(p.pipe_budget.budget_produits)}</td></tr>
                <tr><td>{t("ecarts_cd.pipe.realise")}</td><td>{fcfa(p.pipe_budget.realise)}</td></tr>
                <tr><td>{t("ecarts_cd.pipe.pipe")}</td><td>{fcfa(p.pipe_budget.pipe_pondere.total)} ({fcfa(p.pipe_budget.pipe_pondere.signe)} · {fcfa(p.pipe_budget.pipe_pondere.en_cours)} · {fcfa(p.pipe_budget.pipe_pondere.prospect)})</td></tr>
                <tr><td>{t("ecarts_cd.pipe.atterrissage")}</td><td>{fcfa(p.pipe_budget.atterrissage)}</td></tr>
                <tr><td>{t("ecarts_cd.pipe.reste")}</td><td>{fcfa(p.pipe_budget.reste_a_couvrir)}</td></tr>
                <tr><td>{t("ecarts_cd.pipe.couverture")}</td><td>{p.pipe_budget.couverture_pct === null ? "—" : `${p.pipe_budget.couverture_pct} %`}</td></tr>
              </tbody>
            </table>

            <h4 className="subtitle">{t("ecarts_cd.seuils.title")}</h4>
            <ActionBar actions={[{ label: t("ecarts_cd.seuils.controler"), path: "/api/analytics/pilotage/controler-seuils/", tone: "ghost" }]} />
            <table className="table" data-testid="seuils-budget">
              <tbody>
                {p.seuils_budget.map((s) => (
                  <tr key={s.budget}>
                    <td>{s.budget} · {s.libelle}</td>
                    <td>{fcfa(s.realise)} / {fcfa(s.montant)}</td>
                    <td>{s.taux_pct} %</td>
                    <td>{s.niveau ? <Badge tone={TONE[s.niveau]}>{t(`ecarts_cd.seuils.${s.niveau}`)}</Badge> : "—"}</td>
                  </tr>
                ))}
                {p.seuils_budget.length === 0 && <tr><td className="muted">{t("ecarts_cd.seuils.aucun")}</td></tr>}
              </tbody>
            </table>

            <h4 className="subtitle">{t("ecarts_cd.scelles.title")}</h4>
            <p className="muted">
              {t("ecarts_cd.scelles.hint", { fin: p.retention.retention_financier_ans, op: p.retention.retention_operationnel_ans })}
            </p>
            <ActionBar
              actions={[
                { label: t("ecarts_cd.scelles.sceller"), path: "/api/analytics/marts/scelles/sceller/" },
                { label: t("ecarts_cd.scelles.purger"), path: "/api/analytics/marts/scelles/purger/", tone: "ghost", confirm: t("ecarts_cd.scelles.confirmPurge") },
              ]}
            />
            <table className="table" data-testid="scelles-marts">
              <tbody>
                {(scelles.data ?? []).map((s) => (
                  <tr key={s.id}>
                    <td>{s.mart}</td>
                    <td>{t(`ecarts_cd.scelles.${s.type_donnees}`)} · {s.nb_lignes}</td>
                    <td title={s.sha256}>{s.sha256.slice(0, 12)}…</td>
                    <td>{t("ecarts_cd.scelles.conserve", { date: formatDate(s.conserve_jusqu_au) })}</td>
                    <td><Badge tone={s.integre ? "ok" : "err"}>{s.integre ? t("ecarts_cd.scelles.integre") : t("ecarts_cd.scelles.altere")}</Badge></td>
                  </tr>
                ))}
                {scelles.data?.length === 0 && <tr><td className="muted">{t("ecarts_cd.scelles.aucun")}</td></tr>}
              </tbody>
            </table>
          </div>
        </SectionCard>
      )}
    </>
  );
}
