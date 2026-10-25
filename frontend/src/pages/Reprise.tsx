import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronRight, History } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { Badge, DataTable, DatePicker, EmptyState, FileField, PageHeader, SectionCard } from "../components/ui";
import type { BadgeTone, Column } from "../components/ui";
import { formatDateTime, formatMoney, formatNumber } from "../lib/format";
import { describeError } from "../lib/offlineQueue";
import { ParamsPanel } from "../components/parametres/ParamsPanel";
import { ParamValueTable } from "../components/parametres/ParamValueTable";

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
/** Retire les chemins d'API cités dans les notes de gabarit (« (/api/integrations/import/) »). */
const sansChemin = (texte: string) => texte.replace(/\s*\(\/api\/[^)]*\)/g, "");
/** Libellé court d'un contrôle : avant « = », « : » ou « ( » (« Balance d'ouverture = balance SAGE » → « Balance d'ouverture »). */
const court = (libelle: string) => libelle.split(/\s[=:(]/)[0].trim();
/** Texte serveur lisible : montants « 579411230.00 » au format français, codes « agent_maitrise » en clair. */
const lisible = (texte: string) =>
  texte
    .replace(/-?\d+\.\d{2}\b/g, (n) => formatNumber(Number(n), { decimals: Number(n) % 1 ? 2 : 0 }))
    .replace(/\b([a-z]+)_([a-z_]+)\b/g, (m) => m.replace(/_/g, " "));

const SOURCES = ["c1", "c2", "c3", "c4", "c5", "c6", "c7", "c8", "c9"];
const tri = (v: string | null) => (v === null || v === "" ? null : Number(v));
type ColonneLigne = ColonneGabarit & { id: string };
type ControleLigne = Controle & { id: string };
type TiersLigne = NonNullable<Controle["tiers"]>[number] & { id: string };

/** Reprise de données : gabarits CSV / XML / ZIP GED, exécution à blanc puis réelle, rapport d'anomalies,
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

  const colsAnomalies: Column<Ligne>[] = [
    { key: "numero", header: t("ecarts_import.ligne"), num: true, render: (l) => formatNumber(l.numero), sortValue: (l) => l.numero },
    { key: "erreur", header: t("ecarts_import.anomalie"), render: (l) => l.erreur },
  ];
  const colsGabarit: Column<ColonneLigne>[] = [
    {
      key: "nom",
      header: t("ecarts_import.charger.colonne"),
      render: (c) => (
        <>
          <code>{c.nom}</code> {gabarit?.sensibles.includes(c.nom) && <Badge tone="warn">{t("ecarts_import.charger.sensible")}</Badge>}
        </>
      ),
    },
    { key: "obligatoire", header: t("ecarts_import.charger.obligatoire"), render: (c) => (c.obligatoire ? t("ecarts_import.oui") : "") },
    { key: "aide", header: t("ecarts_import.charger.aide"), render: (c) => c.aide },
    { key: "exemple", header: t("ecarts_import.charger.exemple"), render: (c) => c.exemple },
  ];
  const colsLots: Column<Lot>[] = [
    {
      key: "le",
      header: t("ecarts_import.historique.le"),
      sortValue: (l) => l.cree_le,
      render: (l) => (
        <>
          {formatDateTime(l.cree_le)}
          {l.cree_par_email ? <div className="muted">{l.cree_par_email}</div> : null}
        </>
      ),
    },
    { key: "gabarit", header: t("ecarts_import.charger.gabarit"), render: (l) => l.gabarit_label, sortValue: (l) => l.gabarit_label },
    {
      key: "fichier",
      header: t("ecarts_import.charger.fichier"),
      render: (l) => (
        <span title={l.empreinte}>
          {l.fichier} <span className="muted">({l.format.toUpperCase()})</span>
        </span>
      ),
    },
    { key: "mode", header: t("ecarts_import.historique.mode"), render: (l) => l.mode_label },
    { key: "statut", header: t("ecarts_import.historique.statut"), render: (l) => <Badge tone={TON_LOT[l.statut]}>{l.statut_label}</Badge> },
    {
      key: "resultat",
      header: t("ecarts_import.historique.resultat"),
      render: (l) => (
        <>
          {t("ecarts_import.compteurs", { lignes: l.lignes, creees: l.creees, maj: l.mises_a_jour, doublons: l.doublons, erreurs: l.erreurs })} ·{" "}
          {formatNumber(Number(l.taux_erreur))} %
        </>
      ),
    },
    {
      key: "actions",
      header: <span className="sr-only">{t("ui.actions")}</span>,
      render: (l) =>
        l.lignes > 0 ? (
          <button type="button" className="btn ghost sm" onClick={() => rapport(l)}>
            {t("ecarts_import.rapport")}
          </button>
        ) : null,
    },
  ];

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
                    {g.libelle}
                  </option>
                ))}
              </select>
            </label>
            <div className="field">
              <label htmlFor="reprise-fichier">{t("ecarts_import.charger.fichier")}</label>
              <FileField
                id="reprise-fichier"
                accept={accept}
                buttonLabel={t("revueR1.reprise.choisir")}
                placeholder={t("revueR1.reprise.aucunFichier")}
                onChange={setFichier}
              />
            </div>
            {gabarit?.options.map((o) =>
              o === "date" ? (
                <div className="field" key={o}>
                  <label htmlFor={`reprise-opt-${o}`}>{t(`ecarts_import.charger.options.${o}`)}</label>
                  <DatePicker id={`reprise-opt-${o}`} value={options[o] ?? ""} onChange={(v) => setOptions({ ...options, [o]: v })} />
                </div>
              ) : (
                <label className="field" key={o}>
                  <span>{t(`ecarts_import.charger.options.${o}`)}</span>
                  <input type="number" value={options[o] ?? ""} onChange={(e) => setOptions({ ...options, [o]: e.target.value })} />
                </label>
              ),
            )}
            {/* Case alignée sur la ligne des champs (A-35). */}
            <label className="field reprise-check">
              <span className="reprise-check-row">
                <input type="checkbox" checked={force} onChange={(e) => setForce(e.target.checked)} /> {t("ecarts_import.charger.force")}
              </span>
            </label>
          </div>
          {gabarit && (
            <p className="muted">
              {t("premiumPilotage.reprise.libelle", { label: t("ecarts_import.charger.cle") })}
              <strong>{gabarit.cle}</strong> · {t("premiumPilotage.reprise.libelle", { label: t("ecarts_import.charger.formats") })}
              {gabarit.formats.join(", ").toUpperCase()}
              {gabarit.note ? ` · ${sansChemin(gabarit.note)}` : ""}
            </p>
          )}
          <div className="action-bar-buttons">
            <button type="button" className="btn ghost" disabled={!gabarit} onClick={() => telecharger("csv")}>
              {t("ecarts_import.charger.modeleCsv")}
            </button>
            <button type="button" className="btn ghost" disabled={!gabarit} onClick={() => telecharger("xml")}>
              {t("ecarts_import.charger.modeleXml")}
            </button>
            <button type="button" className="btn ghost" disabled={!fichier || !gabarit || charger.isPending} onClick={() => charger.mutate("blanc")}>
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
                <DataTable columns={colsAnomalies} rows={anomalies.data!.slice(0, 50)} caption={t("ecarts_import.anomalies")} />
              )}
            </div>
          )}
          {gabarit && (
            <details className="reprise-details">
              <summary>
                <ChevronRight size={16} aria-hidden="true" className="reprise-chevron" />
                {t("ecarts_import.charger.colonnes", { n: gabarit.colonnes.length })}
              </summary>
              <DataTable columns={colsGabarit} rows={gabarit.colonnes.map((c) => ({ ...c, id: c.nom }))} caption={t("ecarts_import.charger.colonnes", { n: gabarit.colonnes.length })} />
            </details>
          )}
        </div>
      </SectionCard>

      <SectionCard title={t("ecarts_import.historique.titre")}>
        {(lots.data ?? []).length === 0 ? (
          <EmptyState icon={History} label={t("ecarts_import.historique.vide")} hint={t("revueR1.reprise.historiqueAide")} compact />
        ) : (
          <div data-testid="reprise-historique">
            <DataTable columns={colsLots} rows={lots.data!} caption={t("ecarts_import.historique.titre")} />
          </div>
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
  // Libellé de chaque contrôle (« C1 · Balance d'ouverture ») pour les champs de saisie de la source.
  const libelles: Record<string, string> = Object.fromEntries(q.data.controles.map((c) => [c.code.toLowerCase(), c.libelle]));
  const cols: Column<ControleLigne>[] = [
    {
      key: "controle",
      header: t("ecarts_import.rappro.controle"),
      render: (c) => (
        <>
          <strong>{c.code}</strong> {lisible(c.libelle)}
          <div className="muted">{c.valideur}</div>
        </>
      ),
    },
    { key: "erp", header: t("ecarts_import.rappro.erp"), num: true, render: (c) => formatNumber(Number(c.valeur_erp)) },
    { key: "source", header: t("ecarts_import.rappro.sourceCol"), num: true, render: (c) => (c.valeur_source === null ? "—" : formatNumber(Number(c.valeur_source))) },
    { key: "ecart", header: t("ecarts_import.rappro.ecart"), num: true, render: (c) => (c.ecart === null ? "—" : formatNumber(Number(c.ecart))), sortValue: (c) => tri(c.ecart) },
    {
      key: "statut",
      header: t("ecarts_import.historique.statut"),
      render: (c) => <Badge tone={TON_CONTROLE[c.statut]}>{t(`ecarts_import.rappro.statuts.${c.statut}`)}</Badge>,
    },
    { key: "detail", header: t("ecarts_import.rappro.detail"), render: (c) => lisible(c.detail) },
  ];
  return (
    <SectionCard title={t("ecarts_import.rappro.titre")}>
      <div data-testid="reprise-rapprochements">
        <p className="muted">{t("ecarts_import.rappro.aide")}</p>
        <div className="quick-form-grid">
          {SOURCES.map((s) => (
            <label className="field" key={s}>
              <span title={libelles[s]}>{libelles[s] ? `${s.toUpperCase()} · ${court(libelles[s])}` : t("ecarts_import.rappro.source", { code: s.toUpperCase() })}</span>
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
          <button type="button" className="btn primary" onClick={() => setAppliquees(sources)}>
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
        <DataTable columns={cols} rows={q.data.controles.map((c) => ({ ...c, id: c.code }))} caption={t("ecarts_import.rappro.titre")} />
        <C2ParTiers tiers={q.data.controles.find((c) => c.code === "C2")?.tiers ?? []} />
      </div>
    </SectionCard>
  );
}

function C2ParTiers({ tiers }: { tiers: NonNullable<Controle["tiers"]> }) {
  const { t } = useTranslation();
  if (tiers.length === 0) return null;
  // Soldes de comptes de tiers (401 / 411) : montants en FCFA.
  const cols: Column<TiersLigne>[] = [
    {
      key: "tiers",
      header: t("ecarts_a9.tiers"),
      render: (l) => (
        <>
          <strong>{l.code}</strong> {l.nom}
        </>
      ),
    },
    { key: "erp", header: t("ecarts_import.rappro.erp"), num: true, render: (l) => formatMoney(l.erp) },
    { key: "source", header: t("ecarts_import.rappro.sourceCol"), num: true, render: (l) => (l.source === null ? "—" : formatMoney(l.source)) },
    {
      key: "ecart",
      header: t("ecarts_import.rappro.ecart"),
      num: true,
      sortValue: (l) => tri(l.ecart),
      render: (l) => (l.ecart === null ? "—" : Number(l.ecart) === 0 ? <Badge tone="ok">{formatMoney(0)}</Badge> : <Badge tone="err">{formatMoney(l.ecart)}</Badge>),
    },
  ];
  return (
    <div data-testid="reprise-c2-tiers">
      <h4>{t("ecarts_a9.c2Titre")}</h4>
      <DataTable columns={cols} rows={tiers.map((l) => ({ ...l, id: l.code }))} caption={t("ecarts_a9.c2Titre")} />
    </div>
  );
}

function ParametresRepriseSection() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const q = useQuery({ queryKey: ["reprise", "parametres"], queryFn: () => api.listAll<Parametre>(`${BASE}/parametres/`), retry: 0 });
  const refresh = () => {
    setError(null);
    void qc.invalidateQueries({ queryKey: ["reprise", "parametres"] });
  };
  const modifier = useMutation({
    mutationFn: (v: { id: string; valeur: string }) => api.patch(`${BASE}/parametres/${v.id}/`, { valeur: v.valeur }),
    onSuccess: refresh,
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
        <ParamsPanel module="integrations" count={provisoires} total={q.data.length}>
          {error && (
            <p className="action-error" role="alert">
              {error}
            </p>
          )}
          <ParamValueTable
            rows={q.data}
            caption={t("ecarts_import.params.titre")}
            valeur={(p) => `${formatNumber(Number(p.valeur), { decimals: Number.isInteger(Number(p.valeur)) ? 0 : 1 })}${p.unite ? ` ${p.unite}` : ""}`}
            onSave={(id, valeur) => modifier.mutateAsync({ id, valeur })}
            onConfirm={(id) => confirmer.mutate(id)}
            confirmMessage={t("ecarts_import.params.confirmConfirmer")}
            pending={modifier.isPending || confirmer.isPending}
            step="0.5"
          />
        </ParamsPanel>
      </div>
    </SectionCard>
  );
}
