import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate, formatNumber } from "../../lib/format";
import { describeError } from "../../lib/offlineQueue";
import type { AlertesStock, ArticleStockConfig, AuditValorisation, CertificatMatiere, LotMatiere, ParametreStock, TraceabiliteEntry } from "../../types";
import { ActionBar, Badge, QuickForm, SectionCard } from "../ui";

const OUI_NON = (t: (k: string) => string) => [
  { value: "true", label: t("m5e.oui") },
  { value: "false", label: t("m5e.non") },
];

/** Alertes stock (CDC M5 §7.4) : seuil minimal, péremption, fournisseur non agréé ; délais paramétrables. */
export function AlertesStockSection() {
  const { t } = useTranslation();
  const q = useQuery({ queryKey: ["stocks-alertes"], queryFn: () => api.get<AlertesStock>("/api/stocks/mouvements/alertes/"), retry: 0 });
  if (q.isError || !q.data) return null;
  return (
    <SectionCard title={`${t("m5e.alertes.title")} · ${q.data.rows.length}`}>
      <div data-testid="alertes-stock">
        <p className="muted">{t("m5e.alertes.hint", { jours: q.data.peremption_jours })}</p>
        {q.data.rows.length === 0 ? (
          <p className="muted">{t("m5e.alertes.aucune")}</p>
        ) : (
          <table className="table">
            <caption className="sr-only">{t("m5e.alertes.title")}</caption>
            <tbody>
              {q.data.rows.map((a, i) => (
                <tr key={`${a.type}-${a.article}-${a.lot ?? i}`}>
                  <td><Badge tone={a.type === "stock_mini" ? "warn" : "err"}>{t(`m5e.alertes.${a.type}`)}</Badge></td>
                  <td>{a.article} <span className="muted">· {a.libelle}</span></td>
                  <td>{a.lot ?? "—"}</td>
                  <td>{a.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </SectionCard>
  );
}

/** Paramètres M5 modifiables par ETSL, provisoires tant qu'ils ne sont pas confirmés par la direction. */
export function ParametresStockSection() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [edit, setEdit] = useState<{ id: string; valeur: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const q = useQuery({ queryKey: ["stocks-parametres"], queryFn: () => api.listAll<ParametreStock>("/api/stocks/parametres/"), retry: 0 });
  const refresh = () => {
    setError(null);
    void qc.invalidateQueries({ queryKey: ["stocks-parametres"] });
    void qc.invalidateQueries({ queryKey: ["stocks-alertes"] });
  };
  const modifier = useMutation({
    mutationFn: (v: { id: string; valeur: string }) => api.patch(`/api/stocks/parametres/${v.id}/`, { valeur: v.valeur }),
    onSuccess: () => {
      setEdit(null);
      refresh();
    },
    onError: (e) => setError(describeError(e)),
  });
  const confirmer = useMutation({
    mutationFn: (id: string) => api.post(`/api/stocks/parametres/${id}/confirmer/`),
    onSuccess: refresh,
    onError: (e) => setError(describeError(e)),
  });
  if (q.isError || !q.data) return null;
  const provisoires = q.data.filter((p) => p.est_provisoire).length;
  return (
    <SectionCard title={t("m5e.params.title")}>
      <div data-testid="parametres-stocks">
        {provisoires > 0 && (
          <p className="action-error" role="note" data-testid="alerte-provisoire-stocks">{t("m5e.params.warn", { count: provisoires })}</p>
        )}
        {error && <p className="action-error" role="alert">{error}</p>}
        <table className="table">
          <caption className="sr-only">{t("m5e.params.title")}</caption>
          <tbody>
            {q.data.map((p) => (
              <tr key={p.id}>
                <td>{p.label}</td>
                <td className="num">
                  {edit?.id === p.id ? (
                    <input type="number" min={0} step="1" aria-label={p.label} value={edit.valeur} onChange={(e) => setEdit({ id: p.id, valeur: e.target.value })} />
                  ) : (
                    `${formatNumber(Number(p.valeur))} ${p.unite}`
                  )}
                </td>
                <td><Badge tone={p.est_provisoire ? "warn" : "ok"}>{p.est_provisoire ? t("m5e.params.provisoire") : t("m5e.params.confirme")}</Badge></td>
                <td>
                  {edit?.id === p.id ? (
                    <>
                      <button type="button" className="btn" onClick={() => modifier.mutate(edit)}>{t("m5e.params.valider")}</button>{" "}
                      <button type="button" className="btn ghost" onClick={() => setEdit(null)}>{t("m5e.params.annuler")}</button>
                    </>
                  ) : (
                    <>
                      <button type="button" className="btn ghost" onClick={() => setEdit({ id: p.id, valeur: p.valeur })}>{t("m5e.params.modifier")}</button>{" "}
                      {p.est_provisoire && (
                        <button type="button" className="btn ghost" onClick={() => window.confirm(t("m5e.params.confirmConfirmer")) && confirmer.mutate(p.id)}>
                          {t("m5e.params.confirmer")}
                        </button>
                      )}
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </SectionCard>
  );
}

/** Paramétrage par article (CDC M5 §7.4 / §7.8) : seuil minimal, lot obligatoire, certificat MTC / CoC exigé. */
export function ConfigArticlesSection({ articles }: { articles: { id: string; code: string; label: string }[] }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const q = useQuery({ queryKey: ["stocks-configs"], queryFn: () => api.listAll<ArticleStockConfig>("/api/stocks/configs/"), retry: 0 });
  const modifier = useMutation({
    mutationFn: (v: { id: string; body: Partial<ArticleStockConfig> }) => api.patch(`/api/stocks/configs/${v.id}/`, v.body),
    onSuccess: () => {
      setError(null);
      void qc.invalidateQueries({ queryKey: ["stocks-configs"] });
      void qc.invalidateQueries({ queryKey: ["stocks-alertes"] });
    },
    onError: (e) => setError(describeError(e)),
  });
  if (q.isError) return null;
  const rows = q.data ?? [];
  const configures = new Set(rows.map((r) => r.article));
  return (
    <SectionCard title={`${t("m5e.config.title")} · ${rows.length}`}>
      <div data-testid="config-articles">
        <QuickForm
          title={t("m5e.config.nouveau")}
          endpoint="/api/stocks/configs/"
          transform={(v) => ({ ...v, lot_obligatoire: v.lot_obligatoire === "true", certificat_requis: v.certificat_requis === "true" })}
          fields={[
            {
              name: "article", label: t("stocks.col.article"), type: "select", required: true,
              options: articles.filter((a) => !configures.has(a.id)).map((a) => ({ value: a.id, label: `${a.code} · ${a.label}` })),
            },
            { name: "seuil_minimal", label: t("m5e.config.seuil"), type: "number", min: 0, step: "0.01" },
            { name: "lot_obligatoire", label: t("m5e.config.lotObligatoire"), type: "select", required: true, defaultValue: "false", options: OUI_NON(t) },
            { name: "certificat_requis", label: t("m5e.config.certificatRequis"), type: "select", required: true, defaultValue: "false", options: OUI_NON(t) },
          ]}
        />
        {error && <p className="action-error" role="alert">{error}</p>}
        {rows.length > 0 && (
          <table className="table">
            <caption className="sr-only">{t("m5e.config.title")}</caption>
            <thead>
              <tr>
                <th>{t("stocks.col.article")}</th>
                <th className="num">{t("m5e.config.seuil")}</th>
                <th>{t("m5e.config.lotObligatoire")}</th>
                <th>{t("m5e.config.certificatRequis")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.id}>
                  <td>{c.article_code} <span className="muted">· {c.article_label}</span></td>
                  <td className="num">{formatNumber(Number(c.seuil_minimal))}</td>
                  <td>{c.lot_obligatoire ? t("m5e.oui") : t("m5e.non")}</td>
                  <td>{c.certificat_requis ? t("m5e.oui") : t("m5e.non")}</td>
                  <td>
                    <button
                      type="button"
                      className="btn ghost"
                      onClick={() => {
                        const v = window.prompt(t("m5e.config.nouveauSeuil"), c.seuil_minimal);
                        if (v !== null) modifier.mutate({ id: c.id, body: { seuil_minimal: v } });
                      }}
                    >
                      {t("m5e.config.modifierSeuil")}
                    </button>{" "}
                    <button type="button" className="btn ghost" onClick={() => modifier.mutate({ id: c.id, body: { lot_obligatoire: !c.lot_obligatoire } })}>
                      {c.lot_obligatoire ? t("m5e.config.lotFacultatif") : t("m5e.config.exigerLot")}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </SectionCard>
  );
}

/** Traçabilité amont / aval d'un lot (CDC M5 §7.4) : réception → transferts → consommations sur OF / affaire. */
export function TracabiliteSection({ lots }: { lots: LotMatiere[] }) {
  const { t } = useTranslation();
  const [lot, setLot] = useState("");
  const q = useQuery({
    queryKey: ["stocks-tracabilite", lot],
    queryFn: () => api.get<TraceabiliteEntry[]>(`/api/stocks/mouvements/tracabilite/?lot=${lot}`),
    enabled: Boolean(lot),
    retry: 0,
  });
  return (
    <SectionCard title={t("m5e.trace.title")}>
      <div data-testid="tracabilite-lot">
        <label>
          {t("m5e.trace.lot")}{" "}
          <select aria-label={t("m5e.trace.lot")} value={lot} onChange={(e) => setLot(e.target.value)}>
            <option value="">{t("m5e.trace.choisir")}</option>
            {lots.map((l) => (
              <option key={l.id} value={l.id}>{l.code} · {l.numero_lot}{l.numero_coulee ? ` · ${l.numero_coulee}` : ""}</option>
            ))}
          </select>
        </label>
        {q.data && q.data.length === 0 && <p className="muted">{t("m5e.trace.aucun")}</p>}
        {q.data && q.data.length > 0 && (
          <ol className="trace-chaine">
            {q.data.map((m) => (
              <li key={m.code}>
                <time dateTime={m.date}>{formatDate(m.date)}</time> · <strong>{m.code}</strong> · {m.type_label} · {formatNumber(Number(m.quantite))}
                {" · "}{m.source ?? "—"} → {m.destination ?? "—"}
                {m.ordre ? ` · OF ${m.ordre}` : ""}
                {m.reference ? ` · ${m.reference}` : ""}
              </li>
            ))}
          </ol>
        )}
      </div>
    </SectionCard>
  );
}

/** Actions qualité d'un lot : mise en quarantaine motivée / levée (QA-QC et hiérarchie). */
export function lotActions(lot: LotMatiere, t: (k: string) => string) {
  const base = `/api/stocks/lots/${lot.id}`;
  if (lot.statut === "bloque")
    return [{ label: t("m5e.lot.lever"), path: `${base}/lever-quarantaine/`, tone: "ghost" as const, confirm: t("m5e.lot.confirmLever") }];
  if (lot.statut === "epuise") return [];
  return [{ label: t("m5e.lot.bloquer"), path: `${base}/bloquer/`, tone: "danger" as const, prompt: { name: "motif", label: t("m5e.lot.motif") } }];
}

/** Validation QA-QC et numérisation (GED) d'un certificat MTC / CoC. */
export function CertificatActions({ cert }: { cert: CertificatMatiere }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const joindre = useMutation({
    mutationFn: (fichier: File) => api.upload(`/api/stocks/certificats/${cert.id}/joindre/`, fichier),
    onSuccess: () => {
      setError(null);
      void qc.invalidateQueries();
    },
    onError: (e) => setError(describeError(e)),
  });
  return (
    <>
      {!cert.date_validation && (
        <ActionBar
          actions={[{
            label: t("m5e.cert.valider"), path: `/api/stocks/certificats/${cert.id}/valider/`,
            prompt: { name: "conforme", label: t("m5e.cert.resultat"), options: [{ value: "true", label: t("stocks.certConforme") }, { value: "false", label: t("stocks.certNonConforme") }] },
          }]}
        />
      )}
      {!cert.document && (
        <label className="btn ghost">
          {t("m5e.cert.joindre")}
          <input type="file" accept="application/pdf,image/*" className="sr-only" onChange={(e) => e.target.files?.[0] && joindre.mutate(e.target.files[0])} />
        </label>
      )}
      {error && <p className="action-error" role="alert">{error}</p>}
    </>
  );
}

/** Audit rétrospectif (CDC M5 §7.5) : rejoue les sorties d'un article dans un dépôt avec la méthode applicable
 * (FIFO / PEPS, CUMP, prix standard) et compare au coût enregistré. Coûts masqués hors cercle des montants. */
export function AuditValorisationSection({ depots, articles }: { depots: { id: string; code: string; label: string }[]; articles: { id: string; code: string; label: string }[] }) {
  const { t } = useTranslation();
  const [depot, setDepot] = useState("");
  const [article, setArticle] = useState("");
  const q = useQuery({
    queryKey: ["stocks-audit", depot, article],
    queryFn: () => api.get<AuditValorisation>(`/api/stocks/quants/audit-valorisation/?depot=${depot}&article=${article}`),
    enabled: Boolean(depot && article),
    retry: 0,
  });
  const montant = (v: string | null) => (v === null ? "••••••" : formatNumber(Number(v)));
  return (
    <SectionCard title={t("m5e.audit.title")}>
      <div data-testid="audit-valorisation">
        <p className="muted">{t("m5e.audit.hint")}</p>
        <label>
          {t("m5e.audit.depot")}{" "}
          <select aria-label={t("m5e.audit.depot")} value={depot} onChange={(e) => setDepot(e.target.value)}>
            <option value="">—</option>
            {depots.map((d) => <option key={d.id} value={d.id}>{d.code} · {d.label}</option>)}
          </select>
        </label>{" "}
        <label>
          {t("m5e.audit.article")}{" "}
          <select aria-label={t("m5e.audit.article")} value={article} onChange={(e) => setArticle(e.target.value)}>
            <option value="">—</option>
            {articles.map((a) => <option key={a.id} value={a.id}>{a.code} · {a.label}</option>)}
          </select>
        </label>
        {q.data && (
          <>
            <p role="status">{t("m5e.audit.resultat", { methode: t(`m5e.depot.methodes.${q.data.methode}`), n: q.data.ecarts })}</p>
            {q.data.lignes.length > 0 && (
              <table className="table">
                <caption className="sr-only">{t("m5e.audit.title")}</caption>
                <thead>
                  <tr>
                    <th>{t("m5e.audit.mouvement")}</th>
                    <th className="num">{t("stocks.col.qty")}</th>
                    <th className="num">{t("m5e.audit.enregistre")}</th>
                    <th className="num">{t("m5e.audit.recalcule")}</th>
                    <th className="num">{t("m5e.audit.ecart")}</th>
                  </tr>
                </thead>
                <tbody>
                  {q.data.lignes.map((l) => (
                    <tr key={l.mouvement}>
                      <td>{l.mouvement} <span className="muted">· {formatDate(l.date)}</span></td>
                      <td className="num">{formatNumber(Number(l.quantite))}</td>
                      <td className="num">{montant(l.cout_enregistre)}</td>
                      <td className="num">{montant(l.cout_recalcule)}</td>
                      <td className="num">{montant(l.ecart)}</td>
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
