import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate, formatNumber } from "../../lib/format";
import { describeError } from "../../lib/offlineQueue";
import { ActionBar, Badge, QuickForm, SectionCard } from "../ui";

interface Plan {
  id: string;
  code: string;
  depot_label: string | null;
}
interface Depot {
  id: string;
  code: string;
  label: string;
}
interface Realise {
  id: string;
  code: string;
  date: string;
  statut: string;
  lignes: number;
  comptees: number;
}
interface PlanAnnuel {
  articles: number;
  passages_prevus: string[];
  capacite: number;
  cycles_prevus: string | null;
  cycles_cibles: string;
  conforme: boolean;
  articles_par_passage: number;
  articles_par_passage_conseille: number | null;
  realises: Realise[];
  articles_comptes: number;
  couverture_pct: string | null;
}
interface InventaireCourt {
  id: string;
  code: string;
  depot_label: string | null;
  date: string;
  statut: string;
}
interface LigneEcart {
  id: string;
  article: string;
  article_label: string;
  lot: string | null;
  comptee: boolean;
  quantite_systeme: string;
  quantite_reelle: string;
  ecart: string;
  ecart_pct: string | null;
  hors_tolerance: boolean;
  valeur_ecart: string | null;
}
interface Ecarts {
  lignes: LigneEcart[];
  valeur_nette: string | null;
  valeur_absolue: string | null;
  seuil_validation: string;
  validation_requise: boolean;
  validee: boolean;
  peut_valider: boolean;
}
interface EtatRow extends LigneEcart {
  inventaire: string;
  date: string;
}
interface Etat {
  rows: EtatRow[];
  valeur_nette: string | null;
  hors_tolerance: number;
}

const num = (v: string | null | undefined) => (v === null || v === undefined ? "—" : formatNumber(Number(v)));
const fcfa = (v: string | null) => (v === null ? "—" : `${formatNumber(Number(v))} FCFA`);

/** Écarts M5 (lot m5m8) : plan d'inventaire annuel, écran de comptage, régularisation MAD, état des écarts. */
export function InventaireAnnuelSection() {
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const [planId, setPlanId] = useState("");
  const [annee, setAnnee] = useState(String(new Date().getFullYear()));
  const [invId, setInvId] = useState("");
  const [saisie, setSaisie] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  const plans = useQuery({ queryKey: ["m5m8", "plans"], queryFn: () => api.listAll<Plan>("/api/stocks/plans-inventaire/"), retry: 0 }).data ?? [];
  const depots = useQuery({ queryKey: ["m5m8", "depots"], queryFn: () => api.listAll<Depot>("/api/stocks/depots/?active=1"), retry: 0 }).data ?? [];
  const plan = planId || plans[0]?.id || "";
  const annuel = useQuery({
    queryKey: ["m5m8", "plan-annuel", plan, annee],
    queryFn: () => api.get<PlanAnnuel>(`/api/stocks/plans-inventaire/${plan}/plan-annuel/?annee=${annee}`),
    enabled: !!plan && /^\d{4}$/.test(annee),
    retry: 0,
  });
  const etat = useQuery({
    queryKey: ["m5m8", "etat", plan, annee],
    queryFn: () => api.get<Etat>(`/api/stocks/plans-inventaire/${plan}/etat-ecarts/?annee=${annee}`),
    enabled: !!plan && /^\d{4}$/.test(annee),
    retry: 0,
  });
  const brouillons = useQuery({ queryKey: ["m5m8", "inv", "brouillon"], queryFn: () => api.listAll<InventaireCourt>("/api/stocks/inventaires/?statut=brouillon"), retry: 0 }).data ?? [];
  const enCours = useQuery({ queryKey: ["m5m8", "inv", "en_cours"], queryFn: () => api.listAll<InventaireCourt>("/api/stocks/inventaires/?statut=en_cours"), retry: 0 }).data ?? [];
  const ouverts = [...enCours, ...brouillons];
  const inv = invId || ouverts[0]?.id || "";
  const ecarts = useQuery({
    queryKey: ["m5m8", "ecarts", inv],
    queryFn: () => api.get<Ecarts>(`/api/stocks/inventaires/${inv}/ecarts/`),
    enabled: !!inv,
    retry: 0,
  });
  const compter = useMutation({
    mutationFn: () =>
      api.post(`/api/stocks/inventaires/${inv}/compter/`, {
        lignes: Object.entries(saisie).map(([id, quantite_reelle]) => ({ id, quantite_reelle })),
      }),
    onSuccess: () => {
      setSaisie({});
      setError(null);
      void qc.invalidateQueries();
    },
    onError: (e) => setError(describeError(e)),
  });
  const exporter = (fmt: "xlsx" | "pdf") =>
    api.download(`/api/stocks/plans-inventaire/${plan}/etat-ecarts/?annee=${annee}&export=${fmt}`, `ecarts-inventaire-${annee}.${fmt}`).catch((e) => setError(describeError(e)));

  const a = annuel.data;
  const e = ecarts.data;
  return (
    <SectionCard title={t("ecarts_m5m8.stocks.title")}>
      <div data-testid="inventaire-annuel">
        <p className="muted">
          <Badge tone="warn">{t("ecarts_m5m8.provisoire")}</Badge> {t("ecarts_m5m8.stocks.provisoireNote")}
        </p>
        {error && <p className="action-error" role="alert">{error}</p>}
        <div className="action-bar-buttons">
          <QuickForm
            title={t("ecarts_m5m8.stocks.nouveauPlan")}
            endpoint="/api/stocks/plans-inventaire/"
            fields={[
              { name: "depot", label: t("ecarts_m5m8.stocks.depot"), type: "select", required: true, options: depots.map((d) => ({ value: d.id, label: `${d.code} · ${d.label}` })) },
              { name: "periodicite_jours", label: t("ecarts_m5m8.stocks.periodicite"), type: "number", min: 1, required: true, defaultValue: "30" },
              { name: "articles_par_passage", label: t("ecarts_m5m8.stocks.tranche"), type: "number", min: 1, required: true, defaultValue: "10" },
              { name: "prochaine_date", label: t("ecarts_m5m8.stocks.prochain"), type: "date", required: true },
            ]}
          />
          <label>
            {t("ecarts_m5m8.stocks.plan")}{" "}
            <select value={plan} onChange={(ev) => setPlanId(ev.target.value)}>
              {plans.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.code} · {p.depot_label}
                </option>
              ))}
            </select>
          </label>
          <label>
            {t("ecarts_m5m8.annee")} <input type="number" min={2000} max={2100} value={annee} onChange={(ev) => setAnnee(ev.target.value)} style={{ width: "6rem" }} />
          </label>
        </div>

        {a && (
          <table className="table" data-testid="plan-annuel">
            <caption className="sr-only">{t("ecarts_m5m8.stocks.planAnnuel")}</caption>
            <tbody>
              <tr><th>{t("ecarts_m5m8.stocks.articles")}</th><td>{a.articles}</td></tr>
              <tr><th>{t("ecarts_m5m8.stocks.passages")}</th><td>{a.passages_prevus.length} · {a.passages_prevus.map((d) => formatDate(d, i18n.language)).join(", ")}</td></tr>
              <tr><th>{t("ecarts_m5m8.stocks.capacite")}</th><td>{a.capacite} ({a.articles_par_passage} × {a.passages_prevus.length})</td></tr>
              <tr>
                <th>{t("ecarts_m5m8.stocks.cycles")}</th>
                <td>
                  {num(a.cycles_prevus)} / {num(a.cycles_cibles)}{" "}
                  <Badge tone={a.conforme ? "ok" : "err"}>{a.conforme ? t("ecarts_m5m8.stocks.conforme") : t("ecarts_m5m8.stocks.insuffisant")}</Badge>
                  {!a.conforme && a.articles_par_passage_conseille !== null && (
                    <span className="muted"> {t("ecarts_m5m8.stocks.conseille", { n: a.articles_par_passage_conseille })}</span>
                  )}
                </td>
              </tr>
              <tr><th>{t("ecarts_m5m8.stocks.couverture")}</th><td>{a.articles_comptes} / {a.articles} ({a.couverture_pct === null ? "—" : `${num(a.couverture_pct)} %`})</td></tr>
              <tr>
                <th>{t("ecarts_m5m8.stocks.realises")}</th>
                <td>{a.realises.length === 0 ? "—" : a.realises.map((r) => `${r.code} (${formatDate(r.date, i18n.language)}, ${r.comptees}/${r.lignes}, ${t(`stocks.inv_status.${r.statut}`)})`).join(" · ")}</td>
              </tr>
            </tbody>
          </table>
        )}

        <h4>{t("ecarts_m5m8.stocks.comptage")}</h4>
        {ouverts.length === 0 ? (
          <p className="muted">{t("ecarts_m5m8.stocks.aucunInventaire")}</p>
        ) : (
          <>
            <label>
              {t("ecarts_m5m8.stocks.inventaire")}{" "}
              <select value={inv} onChange={(ev) => { setInvId(ev.target.value); setSaisie({}); }}>
                {ouverts.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.code} · {o.depot_label} · {formatDate(o.date, i18n.language)}
                  </option>
                ))}
              </select>
            </label>
            {e && (
              <>
                <table className="table" data-testid="comptage-inventaire">
                  <thead>
                    <tr>
                      <th>{t("ecarts_m5m8.stocks.article")}</th>
                      <th>{t("ecarts_m5m8.stocks.lot")}</th>
                      <th className="num">{t("ecarts_m5m8.stocks.qteSysteme")}</th>
                      <th className="num">{t("ecarts_m5m8.stocks.qteReelle")}</th>
                      <th className="num">{t("ecarts_m5m8.stocks.ecart")}</th>
                      <th className="num">{t("ecarts_m5m8.stocks.valeur")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {e.lignes.map((l) => (
                      <tr key={l.id}>
                        <td>{l.article} · {l.article_label}</td>
                        <td>{l.lot ?? "—"}</td>
                        <td className="num">{num(l.quantite_systeme)}</td>
                        <td className="num">
                          <input
                            type="number"
                            min={0}
                            step="0.01"
                            aria-label={`${t("ecarts_m5m8.stocks.qteReelle")} ${l.article}`}
                            value={saisie[l.id] ?? (l.comptee ? l.quantite_reelle : "")}
                            onChange={(ev) => setSaisie({ ...saisie, [l.id]: ev.target.value })}
                            style={{ width: "7rem" }}
                          />
                        </td>
                        <td className="num">
                          {l.comptee ? num(l.ecart) : "—"}
                          {l.comptee && l.ecart_pct !== null ? ` (${num(l.ecart_pct)} %)` : ""}{" "}
                          {l.comptee && l.hors_tolerance && <Badge tone="warn">{t("ecarts_m5m8.stocks.horsTolerance")}</Badge>}
                        </td>
                        <td className="num">{l.comptee ? fcfa(l.valeur_ecart) : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p>
                  {t("ecarts_m5m8.stocks.valeurAbsolue")} : {fcfa(e.valeur_absolue)} · {t("ecarts_m5m8.stocks.seuil")} : {fcfa(e.seuil_validation)}{" "}
                  {e.validation_requise && (
                    <Badge tone={e.validee ? "ok" : "err"}>{e.validee ? t("ecarts_m5m8.stocks.madValidee") : t("ecarts_m5m8.stocks.madRequise")}</Badge>
                  )}
                </p>
                <div className="action-bar-buttons">
                  <button type="button" className="btn primary" disabled={Object.keys(saisie).length === 0 || compter.isPending} onClick={() => compter.mutate()}>
                    {t("ecarts_m5m8.stocks.enregistrer")}
                  </button>
                  <ActionBar
                    actions={[
                      ...(e.validation_requise && !e.validee && e.peut_valider
                        ? [{ label: t("ecarts_m5m8.stocks.validerMad"), path: `/api/stocks/inventaires/${inv}/valider-ecarts/`, confirm: t("ecarts_m5m8.stocks.validerMadConfirm") }]
                        : []),
                      { label: t("ecarts_m5m8.stocks.cloturer"), path: `/api/stocks/inventaires/${inv}/cloturer/`, confirm: t("stocks.form.confirmCloture") },
                    ]}
                  />
                </div>
              </>
            )}
          </>
        )}

        <h4>{t("ecarts_m5m8.stocks.etat")}</h4>
        {plan && (
          <div className="action-bar-buttons">
            <button type="button" className="btn ghost" onClick={() => void exporter("xlsx")}>{t("ecarts_m5m8.exportXlsx")}</button>
            <button type="button" className="btn ghost" onClick={() => void exporter("pdf")}>{t("ecarts_m5m8.exportPdf")}</button>
          </div>
        )}
        {etat.data && (
          <>
            <p className="muted">
              {t("ecarts_m5m8.stocks.etatResume", { n: etat.data.rows.length, h: etat.data.hors_tolerance })} · {fcfa(etat.data.valeur_nette)}
            </p>
            {etat.data.rows.length > 0 && (
              <table className="table" data-testid="etat-ecarts">
                <thead>
                  <tr>
                    <th>{t("ecarts_m5m8.stocks.inventaire")}</th>
                    <th>{t("ecarts_m5m8.stocks.article")}</th>
                    <th className="num">{t("ecarts_m5m8.stocks.ecart")}</th>
                    <th className="num">{t("ecarts_m5m8.stocks.valeur")}</th>
                  </tr>
                </thead>
                <tbody>
                  {etat.data.rows.map((r) => (
                    <tr key={`${r.inventaire}-${r.id}`}>
                      <td>{r.inventaire} · {formatDate(r.date, i18n.language)}</td>
                      <td>{r.article} · {r.article_label}</td>
                      <td className="num">
                        {num(r.ecart)} {r.hors_tolerance && <Badge tone="warn">{t("ecarts_m5m8.stocks.horsTolerance")}</Badge>}
                      </td>
                      <td className="num">{fcfa(r.valeur_ecart)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </>
        )}
      </div>
    </SectionCard>
  );
}
