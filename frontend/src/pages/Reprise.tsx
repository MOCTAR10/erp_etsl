import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { Badge, EmptyState, PageHeader, SectionCard } from "../components/ui";
import type { BadgeTone } from "../components/ui";
import { formatDateTime, formatNumber } from "../lib/format";
import { describeError } from "../lib/offlineQueue";

interface ColonneGabarit {
  nom: string;
  obligatoire: boolean;
  aide: string;
  exemple: string;
}
interface Gabarit {
  code: string;
  libelle: string;
  objet: string;
  cle: string;
  formats: string[];
  options: string[];
  note: string;
  sensibles: string[];
  colonnes: ColonneGabarit[];
}
interface Lot {
  id: string;
  gabarit: string;
  gabarit_label: string;
  mode: "blanc" | "reel";
  mode_label: string;
  format: string;
  statut: "valide" | "succes" | "partiel" | "rejete" | "echec";
  statut_label: string;
  fichier: string;
  empreinte: string;
  lignes: number;
  creees: number;
  mises_a_jour: number;
  doublons: number;
  erreurs: number;
  taux_erreur: string;
  seuil_erreur: string;
  message: string;
  cree_par_email: string | null;
  cree_le: string;
  rejeu?: boolean;
}
interface Ligne {
  id: string;
  numero: number;
  statut: string;
  statut_label: string;
  cle: string;
  erreur: string;
}
interface Controle {
  code: string;
  libelle: string;
  valideur: string;
  valeur_erp: string;
  valeur_source: string | null;
  ecart: string | null;
  statut: "conforme" | "ecart" | "a_saisir" | "a_controler";
  detail: string;
  /** C2 (lot a9) : solde 401 + 411 par tiers, comparé à la balance âgée du système source. */
  tiers?: { code: string; nom: string; erp: string; source: string | null; ecart: string | null }[];
}
interface Parametre {
  id: string;
  code: string;
  label: string;
  valeur: string;
  unite: string;
  est_provisoire: boolean;
}

const BASE = "/api/integrations/migration";
const TON_LOT: Record<Lot["statut"], BadgeTone> = { valide: "ok", succes: "ok", partiel: "warn", rejete: "err", echec: "err" };
const TON_CONTROLE: Record<Controle["statut"], BadgeTone> = { conforme: "ok", ecart: "err", a_saisir: "warn", a_controler: "neutral" };
const SOURCES = ["c1", "c2", "c3", "c4", "c5", "c6", "c7", "c8", "c9"];

/** Reprise de données (CDC §10) : gabarits CSV / XML / ZIP GED, exécution à blanc puis réelle, rapport d'anomalies,
 * historique des lots, rapprochements C1-C10 pour le PV de migration, paramètres provisoires. */
export function ReprisePage() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const catalogue = useQuery({ queryKey: ["reprise", "catalogue"], queryFn: () => api.get<Gabarit[]>(`${BASE}/catalogue/`), retry: 0 });
  const lots = useQuery({ queryKey: ["reprise", "lots"], queryFn: () => api.listAll<Lot>(`${BASE}/lots/`), retry: 0, enabled: catalogue.isSuccess });
  const [code, setCode] = useState("");
  const [fichier, setFichier] = useState<File | null>(null);
  const [options, setOptions] = useState<Record<string, string>>({});
  const [force, setForce] = useState(false);
  const [resultat, setResultat] = useState<Lot | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);

  const gabarits = catalogue.data ?? [];
  const gabarit = gabarits.find((g) => g.code === code) ?? gabarits[0];
  const anomalies = useQuery({
    queryKey: ["reprise", "anomalies", resultat?.id],
    queryFn: () => api.get<Ligne[]>(`${BASE}/lots/${resultat!.id}/lignes/?erreurs=1`),
    enabled: !!resultat && resultat.erreurs > 0,
  });

  const charger = useMutation({
    mutationFn: (mode: "blanc" | "reel") =>
      api.upload<Lot>(`${BASE}/import/`, fichier!, "file", { gabarit: gabarit!.code, mode, force: force ? "true" : "", ...options }),
    onSuccess: (lot) => {
      setErreur(null);
      setResultat(lot);
      void qc.invalidateQueries({ queryKey: ["reprise"] });
    },
    onError: (e) => setErreur(describeError(e)),
  });

  if (catalogue.isError) {
    return (
      <>
        <PageHeader title={t("ecarts_import.titre")} />
        <EmptyState label={t("ecarts_import.interdit")} />
      </>
    );
  }

  const telecharger = (type: "csv" | "xml") =>
    void api.download(`${BASE}/modele/?gabarit=${gabarit!.code}&type=${type}`, `${gabarit!.code === "ged" ? "manifeste" : `modele_${gabarit!.code}`}.${type}`);
  const rapport = (lot: Lot) => void api.download(`${BASE}/lots/${lot.id}/rapport/`, `rapport_anomalies_${lot.gabarit}.csv`);
  const accept = gabarit?.formats.includes("zip") ? ".zip" : ".csv,.xml,.txt";

  return (
    <>
      <PageHeader title={t("ecarts_import.titre")} subtitle={t("ecarts_import.sousTitre")} />

      <SectionCard title={t("ecarts_import.charger.titre")}>
        <div data-testid="reprise-chargement">
          <div className="quick-form-grid">
            <label className="field">
              <span>{t("ecarts_import.charger.gabarit")}</span>
              <select
                value={gabarit?.code ?? ""}
                onChange={(e) => {
                  setCode(e.target.value);
                  setResultat(null);
                  setOptions({});
                }}
              >
                {gabarits.map((g) => (
                  <option key={g.code} value={g.code}>
                    {g.objet} · {g.libelle}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>{t("ecarts_import.charger.fichier")}</span>
              <input type="file" accept={accept} onChange={(e) => setFichier(e.target.files?.[0] ?? null)} />
            </label>
            {gabarit?.options.map((o) => (
              <label className="field" key={o}>
                <span>{t(`ecarts_import.charger.options.${o}`)}</span>
                <input
                  type={o === "date" ? "date" : "number"}
                  value={options[o] ?? ""}
                  onChange={(e) => setOptions({ ...options, [o]: e.target.value })}
                />
              </label>
            ))}
            <label className="field">
              <span>
                <input type="checkbox" checked={force} onChange={(e) => setForce(e.target.checked)} /> {t("ecarts_import.charger.force")}
              </span>
            </label>
          </div>
          {gabarit && (
            <p className="muted">
              {t("ecarts_import.charger.cle")} : <strong>{gabarit.cle}</strong> · {t("ecarts_import.charger.formats")} : {gabarit.formats.join(", ").toUpperCase()}
              {gabarit.note ? ` · ${gabarit.note}` : ""}
            </p>
          )}
          <div className="action-bar-buttons">
            <button type="button" className="btn ghost" disabled={!gabarit} onClick={() => telecharger("csv")}>
              {t("ecarts_import.charger.modeleCsv")}
            </button>
            <button type="button" className="btn ghost" disabled={!gabarit} onClick={() => telecharger("xml")}>
              {t("ecarts_import.charger.modeleXml")}
            </button>
            <button type="button" className="btn" disabled={!fichier || !gabarit || charger.isPending} onClick={() => charger.mutate("blanc")}>
              {t("ecarts_import.charger.blanc")}
            </button>
            <button
              type="button"
              className="btn primary"
              disabled={!fichier || !gabarit || charger.isPending}
              onClick={() => window.confirm(t("ecarts_import.charger.confirmReel")) && charger.mutate("reel")}
            >
              {t("ecarts_import.charger.reel")}
            </button>
          </div>
          {erreur && (
            <p className="action-error" role="alert">
              {erreur}
            </p>
          )}
          {resultat && (
            <div data-testid="reprise-resultat">
              <p>
                <Badge tone={TON_LOT[resultat.statut]}>{resultat.statut_label}</Badge> {resultat.rejeu ? <Badge tone="neutral">{t("ecarts_import.charger.rejeu")}</Badge> : null}{" "}
                {t("ecarts_import.compteurs", {
                  lignes: resultat.lignes,
                  creees: resultat.creees,
                  maj: resultat.mises_a_jour,
                  doublons: resultat.doublons,
                  erreurs: resultat.erreurs,
                })}{" "}
                · {t("ecarts_import.taux", { taux: formatNumber(Number(resultat.taux_erreur)), seuil: formatNumber(Number(resultat.seuil_erreur)) })}
              </p>
              {resultat.message && <p className="muted">{resultat.message}</p>}
              {resultat.lignes > 0 && (
                <button type="button" className="btn ghost" onClick={() => rapport(resultat)}>
                  {t("ecarts_import.rapport")}
                </button>
              )}
              {(anomalies.data ?? []).length > 0 && (
                <table className="table">
                  <caption className="sr-only">{t("ecarts_import.anomalies")}</caption>
                  <thead>
                    <tr>
                      <th>{t("ecarts_import.ligne")}</th>
                      <th>{t("ecarts_import.anomalie")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {anomalies.data!.slice(0, 50).map((l) => (
                      <tr key={l.id}>
                        <td className="num">{l.numero}</td>
                        <td>{l.erreur}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}
          {gabarit && (
            <details>
              <summary>{t("ecarts_import.charger.colonnes", { n: gabarit.colonnes.length })}</summary>
              <table className="table">
                <thead>
                  <tr>
                    <th>{t("ecarts_import.charger.colonne")}</th>
                    <th>{t("ecarts_import.charger.obligatoire")}</th>
                    <th>{t("ecarts_import.charger.aide")}</th>
                    <th>{t("ecarts_import.charger.exemple")}</th>
                  </tr>
                </thead>
                <tbody>
                  {gabarit.colonnes.map((c) => (
                    <tr key={c.nom}>
                      <td>
                        <code>{c.nom}</code> {gabarit.sensibles.includes(c.nom) && <Badge tone="warn">{t("ecarts_import.charger.sensible")}</Badge>}
                      </td>
                      <td>{c.obligatoire ? t("ecarts_import.oui") : ""}</td>
                      <td>{c.aide}</td>
                      <td>{c.exemple}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          )}
        </div>
      </SectionCard>

      <SectionCard title={t("ecarts_import.historique.titre")}>
        {(lots.data ?? []).length === 0 ? (
          <EmptyState label={t("ecarts_import.historique.vide")} />
        ) : (
          <table className="table" data-testid="reprise-historique">
            <thead>
              <tr>
                <th>{t("ecarts_import.historique.le")}</th>
                <th>{t("ecarts_import.charger.gabarit")}</th>
                <th>{t("ecarts_import.charger.fichier")}</th>
                <th>{t("ecarts_import.historique.mode")}</th>
                <th>{t("ecarts_import.historique.statut")}</th>
                <th>{t("ecarts_import.historique.resultat")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {lots.data!.map((l) => (
                <tr key={l.id}>
                  <td>
                    {formatDateTime(l.cree_le)}
                    <br />
                    <span className="muted">{l.cree_par_email ?? ""}</span>
                  </td>
                  <td>{l.gabarit_label}</td>
                  <td title={l.empreinte}>
                    {l.fichier} <span className="muted">({l.format.toUpperCase()})</span>
                  </td>
                  <td>{l.mode_label}</td>
                  <td>
                    <Badge tone={TON_LOT[l.statut]}>{l.statut_label}</Badge>
                  </td>
                  <td>
                    {t("ecarts_import.compteurs", { lignes: l.lignes, creees: l.creees, maj: l.mises_a_jour, doublons: l.doublons, erreurs: l.erreurs })} ·{" "}
                    {formatNumber(Number(l.taux_erreur))} %
                  </td>
                  <td>
                    {l.lignes > 0 && (
                      <button type="button" className="btn ghost" onClick={() => rapport(l)}>
                        {t("ecarts_import.rapport")}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </SectionCard>

      <RapprochementsSection />
      <ParametresRepriseSection />
    </>
  );
}

function RapprochementsSection() {
  const { t } = useTranslation();
  const [sources, setSources] = useState<Record<string, string>>({});
  const [appliquees, setAppliquees] = useState<Record<string, string>>({});
  const query = new URLSearchParams(Object.entries(appliquees).filter(([, v]) => v !== "").map(([k, v]) => [`source_${k}`, v])).toString();
  const q = useQuery({
    queryKey: ["reprise", "rapprochements", query],
    queryFn: () => api.get<{ controles: Controle[] }>(`${BASE}/rapprochements/${query ? `?${query}` : ""}`),
    retry: 0,
  });
  if (q.isError || !q.data) return null;
  return (
    <SectionCard title={t("ecarts_import.rappro.titre")}>
      <div data-testid="reprise-rapprochements">
        <p className="muted">{t("ecarts_import.rappro.aide")}</p>
        <div className="quick-form-grid">
          {SOURCES.map((s) => (
            <label className="field" key={s}>
              <span>{t("ecarts_import.rappro.source", { code: s.toUpperCase() })}</span>
              <input type="number" step="any" value={sources[s] ?? ""} onChange={(e) => setSources({ ...sources, [s]: e.target.value })} />
            </label>
          ))}
        </div>
        <label className="field">
          <span>{t("ecarts_a9.c2Tiers")}</span>
          <textarea
            rows={3}
            placeholder={"CLI-001;2360000\nFRS-001;-1180000"}
            value={sources.c2_tiers ?? ""}
            onChange={(e) => setSources({ ...sources, c2_tiers: e.target.value })}
          />
        </label>
        <p className="muted">{t("ecarts_a9.c2TiersAide")}</p>
        <div className="action-bar-buttons">
          <button type="button" className="btn" onClick={() => setAppliquees(sources)}>
            {t("ecarts_import.rappro.calculer")}
          </button>
          <button
            type="button"
            className="btn ghost"
            onClick={() => void api.download(`${BASE}/rapprochements/?${query}${query ? "&" : ""}export=csv`, "rapprochements_migration.csv")}
          >
            {t("ecarts_import.rappro.exporter")}
          </button>
        </div>
        <table className="table">
          <thead>
            <tr>
              <th>{t("ecarts_import.rappro.controle")}</th>
              <th>{t("ecarts_import.rappro.erp")}</th>
              <th>{t("ecarts_import.rappro.sourceCol")}</th>
              <th>{t("ecarts_import.rappro.ecart")}</th>
              <th>{t("ecarts_import.historique.statut")}</th>
              <th>{t("ecarts_import.rappro.detail")}</th>
            </tr>
          </thead>
          <tbody>
            {q.data.controles.map((c) => (
              <tr key={c.code}>
                <td>
                  <strong>{c.code}</strong> {c.libelle}
                  <br />
                  <span className="muted">{c.valideur}</span>
                </td>
                <td className="num">{formatNumber(Number(c.valeur_erp))}</td>
                <td className="num">{c.valeur_source === null ? "—" : formatNumber(Number(c.valeur_source))}</td>
                <td className="num">{c.ecart === null ? "—" : formatNumber(Number(c.ecart))}</td>
                <td>
                  <Badge tone={TON_CONTROLE[c.statut]}>{t(`ecarts_import.rappro.statuts.${c.statut}`)}</Badge>
                </td>
                <td>{c.detail}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <C2ParTiers tiers={q.data.controles.find((c) => c.code === "C2")?.tiers ?? []} />
      </div>
    </SectionCard>
  );
}

function C2ParTiers({ tiers }: { tiers: NonNullable<Controle["tiers"]> }) {
  const { t } = useTranslation();
  if (tiers.length === 0) return null;
  return (
    <table className="table" data-testid="reprise-c2-tiers">
      <caption>{t("ecarts_a9.c2Titre")}</caption>
      <thead>
        <tr>
          <th>{t("ecarts_a9.tiers")}</th>
          <th>{t("ecarts_import.rappro.erp")}</th>
          <th>{t("ecarts_import.rappro.sourceCol")}</th>
          <th>{t("ecarts_import.rappro.ecart")}</th>
        </tr>
      </thead>
      <tbody>
        {tiers.map((l) => (
          <tr key={l.code}>
            <td>
              <strong>{l.code}</strong> {l.nom}
            </td>
            <td className="num">{formatNumber(Number(l.erp))}</td>
            <td className="num">{l.source === null ? "—" : formatNumber(Number(l.source))}</td>
            <td className="num">
              {l.ecart === null ? "—" : Number(l.ecart) === 0 ? <Badge tone="ok">0</Badge> : <Badge tone="err">{formatNumber(Number(l.ecart))}</Badge>}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ParametresRepriseSection() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [edit, setEdit] = useState<{ id: string; valeur: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const q = useQuery({ queryKey: ["reprise", "parametres"], queryFn: () => api.listAll<Parametre>(`${BASE}/parametres/`), retry: 0 });
  const refresh = () => {
    setError(null);
    void qc.invalidateQueries({ queryKey: ["reprise", "parametres"] });
  };
  const modifier = useMutation({
    mutationFn: (v: { id: string; valeur: string }) => api.patch(`${BASE}/parametres/${v.id}/`, { valeur: v.valeur }),
    onSuccess: () => {
      setEdit(null);
      refresh();
    },
    onError: (e) => setError(describeError(e)),
  });
  const confirmer = useMutation({
    mutationFn: (id: string) => api.post(`${BASE}/parametres/${id}/confirmer/`),
    onSuccess: refresh,
    onError: (e) => setError(describeError(e)),
  });
  if (q.isError || !q.data) return null;
  const provisoires = q.data.filter((p) => p.est_provisoire).length;
  return (
    <SectionCard title={t("ecarts_import.params.titre")}>
      <div data-testid="parametres-reprise">
        {provisoires > 0 && (
          <p className="action-error" role="note">
            {t("ecarts_import.params.bandeau", { count: provisoires })}
          </p>
        )}
        {error && (
          <p className="action-error" role="alert">
            {error}
          </p>
        )}
        <table className="table">
          <caption className="sr-only">{t("ecarts_import.params.titre")}</caption>
          <tbody>
            {q.data.map((p) => (
              <tr key={p.id}>
                <td>{p.label}</td>
                <td className="num">
                  {edit?.id === p.id ? (
                    <input type="number" min={0} step="0.5" aria-label={p.label} value={edit.valeur} onChange={(e) => setEdit({ id: p.id, valeur: e.target.value })} />
                  ) : (
                    `${formatNumber(Number(p.valeur))} ${p.unite}`
                  )}
                </td>
                <td>
                  <Badge tone={p.est_provisoire ? "warn" : "ok"}>{p.est_provisoire ? t("ecarts_import.params.provisoire") : t("ecarts_import.params.confirme")}</Badge>
                </td>
                <td>
                  {edit?.id === p.id ? (
                    <>
                      <button type="button" className="btn" onClick={() => modifier.mutate(edit)}>
                        {t("ecarts_import.params.valider")}
                      </button>{" "}
                      <button type="button" className="btn ghost" onClick={() => setEdit(null)}>
                        {t("ecarts_import.params.annuler")}
                      </button>
                    </>
                  ) : (
                    <>
                      <button type="button" className="btn ghost" onClick={() => setEdit({ id: p.id, valeur: p.valeur })}>
                        {t("ecarts_import.params.modifier")}
                      </button>{" "}
                      {p.est_provisoire && (
                        <button type="button" className="btn ghost" onClick={() => window.confirm(t("ecarts_import.params.confirmConfirmer")) && confirmer.mutate(p.id)}>
                          {t("ecarts_import.params.confirmer")}
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
