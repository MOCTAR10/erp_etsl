import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate, formatMoney, formatNumber } from "../../lib/format";
import { describeError } from "../../lib/offlineQueue";
import { SectionActions } from "../sections/SectionActions";
import { ActionBar, Badge, DataTable, QuickForm, SectionCard } from "../ui";
import type { Column } from "../ui";

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

/** Quantité exacte : entière sans décimales, sinon deux décimales (jamais d'arrondi trompeur). */
const num = (v: string | null | undefined) => {
  if (v === null || v === undefined) return "—";
  return Number.isInteger(Number(v)) ? formatNumber(v) : formatNumber(v, { decimals: 2 });
};
const fcfa = (v: string | null) => formatMoney(v);

/** Écarts stocks : plan d'inventaire annuel, écran de comptage, régularisation MAD, état des écarts. */
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

  const lignesPlan: { id: string; label: string; valeur: ReactNode }[] = a
    ? [
        { id: "articles", label: t("ecarts_m5m8.stocks.articles"), valeur: formatNumber(a.articles) },
        {
          id: "passages",
          label: t("ecarts_m5m8.stocks.passages"),
          valeur: (
            <>
              {t("revueR2.stocks.passages", { count: a.passages_prevus.length })}
              <span className="cell-sub">
                {a.passages_prevus.map((d) => new Date(d).toLocaleDateString(i18n.language || "fr", { day: "2-digit", month: "2-digit" })).join(" · ")}
              </span>
            </>
          ),
        },
        { id: "capacite", label: t("ecarts_m5m8.stocks.capacite"), valeur: `${formatNumber(a.capacite)} (${a.articles_par_passage} × ${a.passages_prevus.length})` },
        {
          id: "cycles",
          label: t("ecarts_m5m8.stocks.cycles"),
          valeur: (
            <>
              {num(a.cycles_prevus)} / {num(a.cycles_cibles)}{" "}
              <Badge tone={a.conforme ? "ok" : "err"}>{a.conforme ? t("ecarts_m5m8.stocks.conforme") : t("ecarts_m5m8.stocks.insuffisant")}</Badge>
              {!a.conforme && a.articles_par_passage_conseille !== null && (
                <span className="muted"> {t("ecarts_m5m8.stocks.conseille", { n: a.articles_par_passage_conseille })}</span>
              )}
            </>
          ),
        },
        {
          id: "couverture",
          label: t("ecarts_m5m8.stocks.couverture"),
          valeur: `${a.articles_comptes} / ${a.articles} (${a.couverture_pct === null ? "—" : `${num(a.couverture_pct)} %`})`,
        },
        {
          id: "realises",
          label: t("ecarts_m5m8.stocks.realises"),
          valeur:
            a.realises.length === 0
              ? "—"
              : a.realises.map((r) => `${r.code} (${formatDate(r.date, i18n.language)}, ${r.comptees}/${r.lignes}, ${t(`stocks.inv_status.${r.statut}`)})`).join(" · "),
        },
      ]
    : [];
  const colsPlan: Column<(typeof lignesPlan)[number]>[] = [
    { key: "label", header: t("tableaux.stocks.indicateur"), width: 280, render: (r) => r.label },
    { key: "valeur", header: t("tableaux.stocks.valeur"), render: (r) => r.valeur },
  ];

  const colsComptage: Column<LigneEcart>[] = [
    {
      key: "article",
      header: t("ecarts_m5m8.stocks.article"),
      render: (l) => (
        <>
          <span className="cell-nowrap">{l.article}</span>
          <span className="cell-sub">{l.article_label}</span>
        </>
      ),
      sortValue: (l) => l.article,
    },
    { key: "lot", header: t("ecarts_m5m8.stocks.lot"), render: (l) => l.lot ?? "—" },
    { key: "qteSysteme", header: t("ecarts_m5m8.stocks.qteSysteme"), num: true, render: (l) => num(l.quantite_systeme) },
    {
      key: "qteReelle",
      header: t("ecarts_m5m8.stocks.qteReelle"),
      num: true,
      render: (l) => (
        <input
          type="number"
          className="control"
          min={0}
          step="0.01"
          aria-label={`${t("ecarts_m5m8.stocks.qteReelle")} ${l.article}`}
          value={saisie[l.id] ?? (l.comptee ? l.quantite_reelle : "")}
          onChange={(ev) => setSaisie({ ...saisie, [l.id]: ev.target.value })}
          style={{ width: "7rem", textAlign: "right" }}
        />
      ),
    },
    {
      key: "ecart",
      header: t("ecarts_m5m8.stocks.ecart"),
      num: true,
      render: (l) => (
        <>
          {l.comptee ? num(l.ecart) : "—"}
          {l.comptee && l.ecart_pct !== null ? ` (${num(l.ecart_pct)} %)` : ""}{" "}
          {l.comptee && l.hors_tolerance && <Badge tone="warn">{t("ecarts_m5m8.stocks.horsTolerance")}</Badge>}
        </>
      ),
    },
    { key: "valeur", header: t("ecarts_m5m8.stocks.valeur"), num: true, render: (l) => (l.comptee ? fcfa(l.valeur_ecart) : "—") },
  ];

  const colsEtat: Column<EtatRow>[] = [
    {
      key: "inventaire",
      header: t("ecarts_m5m8.stocks.inventaire"),
      render: (r) => (
        <>
          <span className="cell-nowrap">{r.inventaire}</span>
          <span className="cell-sub">{formatDate(r.date, i18n.language)}</span>
        </>
      ),
      sortValue: (r) => r.date,
    },
    {
      key: "article",
      header: t("ecarts_m5m8.stocks.article"),
      render: (r) => (
        <>
          <span className="cell-nowrap">{r.article}</span>
          <span className="cell-sub">{r.article_label}</span>
        </>
      ),
      sortValue: (r) => r.article,
    },
    {
      key: "ecart",
      header: t("ecarts_m5m8.stocks.ecart"),
      num: true,
      render: (r) => (
        <>
          {num(r.ecart)} {r.hors_tolerance && <Badge tone="warn">{t("ecarts_m5m8.stocks.horsTolerance")}</Badge>}
        </>
      ),
    },
    { key: "valeur", header: t("ecarts_m5m8.stocks.valeur"), num: true, render: (r) => fcfa(r.valeur_ecart), sortValue: (r) => Number(r.valeur_ecart ?? 0) },
  ];
  return (
    <SectionCard
      title={t("ecarts_m5m8.stocks.title")}
      actions={
        <SectionActions>
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
        </SectionActions>
      }
    >
      <div data-testid="inventaire-annuel">
        <p className="muted">
          <Badge tone="warn">{t("ecarts_m5m8.provisoire")}</Badge> {t("ecarts_m5m8.stocks.provisoireNote")}
        </p>
        {error && <p className="action-error" role="alert">{error}</p>}
        <div className="list-toolbar">
          <div className="field">
            <label htmlFor="inv-annuel-plan">{t("ecarts_m5m8.stocks.plan")}</label>
            <select id="inv-annuel-plan" className="control" value={plan} onChange={(ev) => setPlanId(ev.target.value)}>
              {plans.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.depot_label ?? p.code}
                </option>
              ))}
            </select>
          </div>
          <div className="field" style={{ flex: "0 0 120px" }}>
            <label htmlFor="inv-annuel-annee">{t("ecarts_m5m8.annee")}</label>
            <input id="inv-annuel-annee" className="control" type="number" min={2000} max={2100} value={annee} onChange={(ev) => setAnnee(ev.target.value)} />
          </div>
        </div>

        {a && (
          <div data-testid="plan-annuel">
            <DataTable caption={t("ecarts_m5m8.stocks.planAnnuel")} density="compact" columns={colsPlan} rows={lignesPlan} />
          </div>
        )}

        <h4>{t("ecarts_m5m8.stocks.comptage")}</h4>
        {ouverts.length === 0 ? (
          <p className="muted">{t("ecarts_m5m8.stocks.aucunInventaire")}</p>
        ) : (
          <>
            <div className="list-toolbar">
              <div className="field">
                <label htmlFor="inv-annuel-inventaire">{t("ecarts_m5m8.stocks.inventaire")}</label>
                <select id="inv-annuel-inventaire" className="control" value={inv} onChange={(ev) => { setInvId(ev.target.value); setSaisie({}); }}>
                  {ouverts.map((o) => (
                    <option key={o.id} value={o.id}>
                      {o.code} · {formatDate(o.date, i18n.language)}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            {e && (
              <>
                <div data-testid="comptage-inventaire">
                  <DataTable caption={t("ecarts_m5m8.stocks.comptage")} columns={colsComptage} rows={e.lignes} />
                </div>
                <p>
                  {t("ecarts_m5m8.stocks.valeurAbsolue")} : {fcfa(e.valeur_absolue)} · {t("ecarts_m5m8.stocks.seuil")} : {fcfa(e.seuil_validation)}{" "}
                  {e.validation_requise && (
                    <Badge tone={e.validee ? "ok" : "err"}>{e.validee ? t("ecarts_m5m8.stocks.madValidee") : t("ecarts_m5m8.stocks.madRequise")}</Badge>
                  )}
                </p>
                <div className="action-bar-buttons">
                  <button type="button" className="btn" disabled={Object.keys(saisie).length === 0 || compter.isPending} onClick={() => compter.mutate()}>
                    {t("ecarts_m5m8.stocks.enregistrer")}
                  </button>
                  <ActionBar
                    actions={[
                      ...(e.validation_requise && !e.validee && e.peut_valider
                        ? [{ label: t("ecarts_m5m8.stocks.validerMad"), path: `/api/stocks/inventaires/${inv}/valider-ecarts/`, confirm: t("ecarts_m5m8.stocks.validerMadConfirm") }]
                        : []),
                      { label: t("ecarts_m5m8.stocks.cloturer"), path: `/api/stocks/inventaires/${inv}/cloturer/`, tone: "ghost", confirm: t("stocks.form.confirmCloture") },
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
            <button type="button" className="btn ghost sm" onClick={() => void exporter("xlsx")}>{t("ecarts_m5m8.exportXlsx")}</button>
            <button type="button" className="btn ghost sm" onClick={() => void exporter("pdf")}>{t("ecarts_m5m8.exportPdf")}</button>
          </div>
        )}
        {etat.data && (
          <>
            <p className="muted">
              {t("ecarts_m5m8.stocks.etatResume", { n: etat.data.rows.length, h: etat.data.hors_tolerance })} · {fcfa(etat.data.valeur_nette)}
            </p>
            {etat.data.rows.length > 0 && (
              <div data-testid="etat-ecarts">
                <DataTable
                  caption={t("ecarts_m5m8.stocks.etat")}
                  columns={colsEtat}
                  rows={etat.data.rows.map((r) => ({ ...r, id: `${r.inventaire}-${r.id}` }))}
                />
              </div>
            )}
          </>
        )}
      </div>
    </SectionCard>
  );
}
