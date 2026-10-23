import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate, formatDateTime, formatMoney, formatNumber } from "../../lib/format";
import { ActionBar, Badge, DataTable, SectionCard } from "../ui";
import type { Column } from "../ui";

/* Lot de suivi inter-modules : M3 → M11 (marge à terminaison), M10 → M11 (balance âgée), M3 → M5 (réservations),
   M1 → M10 (retenue de garantie), import du grand livre / gabarit SAGE, M4 → M3 (flux machines, compteurs, BL). */

const fcfa = (v: string | null | undefined) => (v === null || v === undefined ? "—" : formatMoney(v));
const pct = (v: string | null | undefined) => (v === null || v === undefined ? "—" : `${formatNumber(Number(v))} %`);
/** Valeur de tri numérique d'une décimale DRF (`null` en fin de liste). */
const num = (v: string | null | undefined) => (v === null || v === undefined || v === "" ? null : Number(v));

// --------------------------------------------------------------------------------------------- M3 → M11
interface MargeRow {
  id: string;
  affaire_code: string;
  affaire_label: string;
  avancement_pct: string | null;
  chiffre_affaires: string | null;
  couts_engages: string | null;
  cout_a_terminaison: string | null;
  marge_a_terminaison: string | null;
  marge_pct: string | null;
  publie_le: string | null;
  alerte: boolean;
}

export function MargesTerminaisonSection() {
  const { t } = useTranslation();
  const q = useQuery({
    queryKey: ["suivi", "marges"],
    queryFn: () => api.get<{ rows: MargeRow[]; en_attente: number }>("/api/controle-gestion/marges-terminaison/"),
    retry: 0,
  });
  const rows = q.data?.rows ?? [];
  const cols: Column<MargeRow>[] = [
    { key: "affaire", header: t("ecarts_suivi.affaire"), render: (r) => `${r.affaire_code} · ${r.affaire_label}`, sortValue: (r) => r.affaire_code },
    { key: "avancement", header: t("ecarts_suivi.marges.avancement"), num: true, render: (r) => pct(r.avancement_pct), sortValue: (r) => num(r.avancement_pct) },
    { key: "ca", header: t("ecarts_suivi.marges.ca"), num: true, render: (r) => fcfa(r.chiffre_affaires), sortValue: (r) => num(r.chiffre_affaires) },
    { key: "engage", header: t("ecarts_suivi.marges.engage"), num: true, render: (r) => fcfa(r.couts_engages), sortValue: (r) => num(r.couts_engages) },
    { key: "cat", header: t("ecarts_suivi.marges.cat"), num: true, render: (r) => fcfa(r.cout_a_terminaison), sortValue: (r) => num(r.cout_a_terminaison) },
    {
      key: "marge",
      header: t("ecarts_suivi.marges.marge"),
      num: true,
      sortValue: (r) => num(r.marge_a_terminaison),
      render: (r) => (
        <>
          {fcfa(r.marge_a_terminaison)} {r.marge_pct !== null && <span className="muted">({pct(r.marge_pct)})</span>}{" "}
          {r.alerte && <Badge tone="err">{t("ecarts_suivi.marges.negative")}</Badge>}
        </>
      ),
    },
    { key: "publie", header: t("ecarts_suivi.marges.publie"), render: (r) => (r.publie_le ? formatDateTime(r.publie_le) : "—"), sortValue: (r) => r.publie_le },
  ];
  return (
    <SectionCard title={t("ecarts_suivi.marges.title")}>
      <p className="muted">{t("ecarts_suivi.marges.note")}</p>
      <ActionBar
        actions={[
          { label: t("ecarts_suivi.marges.integrer", { n: q.data?.en_attente ?? 0 }), path: "/api/controle-gestion/marges-terminaison/integrer/", tone: "ghost" as const },
        ]}
      />
      <div data-testid="marges-terminaison">
        <DataTable columns={cols} rows={rows} caption={t("ecarts_suivi.marges.title")} loading={q.isLoading} emptyLabel={t("ecarts_suivi.marges.vide")} />
      </div>
    </SectionCard>
  );
}

// --------------------------------------------------------------------------------------------- M10 → M11
interface Colonne {
  key: string;
  label: string;
  montant: boolean;
}
interface Etat {
  titre: string;
  sous_titre: string;
  provisoire: boolean;
  avertissement: string;
  colonnes: Colonne[];
  lignes: Record<string, string | boolean | null>[];
}

type LigneEtat = { id: number; valeurs: Record<string, string | boolean | null> };

function TableEtat({ etat }: { etat: Etat }) {
  const rows: LigneEtat[] = etat.lignes.map((valeurs, i) => ({ id: i, valeurs }));
  const cols: Column<LigneEtat>[] = etat.colonnes.map((c) => ({
    key: c.key,
    header: c.label,
    num: c.montant,
    render: (l) => {
      const v = c.montant ? fcfa(l.valeurs[c.key] as string | null) : String(l.valeurs[c.key] ?? "");
      return l.valeurs.total_ligne ? <strong>{v}</strong> : v;
    },
  }));
  return (
    <>
      <h4>{etat.titre}</h4>
      <p className="muted">{etat.sous_titre}</p>
      <DataTable columns={cols} rows={rows} caption={etat.titre} />
    </>
  );
}

export function BalanceAgeeGestionSection() {
  const { t } = useTranslation();
  const q = useQuery({
    queryKey: ["suivi", "balance-agee"],
    queryFn: () => api.get<{ clients: Etat; fournisseurs: Etat }>("/api/controle-gestion/balance-agee/"),
    retry: 0,
  });
  return (
    <SectionCard title={t("ecarts_suivi.balance.title")}>
      <p className="muted">{t("ecarts_suivi.balance.note")}</p>
      {q.data?.clients.provisoire && (
        <p className="action-error" role="note">
          {q.data.clients.avertissement}
        </p>
      )}
      {q.data && <TableEtat etat={q.data.clients} />}
      {q.data && <TableEtat etat={q.data.fournisseurs} />}
    </SectionCard>
  );
}

// --------------------------------------------------------------------------------------------- M3 → M5
interface Reservation {
  id: string;
  article_code: string;
  article_label: string;
  ordre_code: string | null;
  quantite: string;
  quantite_consommee: string;
  reste: string;
  statut: string;
  statut_label: string;
  motif: string;
  created_at: string;
}
interface Dispo {
  article: string;
  code: string;
  label: string;
  physique: string;
  reserve: string;
  disponible: string;
}

export function ReservationsStockSection() {
  const { t } = useTranslation();
  const dispo = useQuery({
    queryKey: ["suivi", "dispo"],
    queryFn: () => api.get<{ rows: Dispo[]; bloquante: boolean }>("/api/stocks/reservations/disponibilites/"),
    retry: 0,
  });
  const resas = useQuery({
    queryKey: ["suivi", "reservations"],
    queryFn: () => api.listAll<Reservation>("/api/stocks/reservations/", { maxPages: 2 }),
    retry: 0,
  }).data ?? [];
  const dispoRows = (dispo.data?.rows ?? []).map((d) => ({ ...d, id: d.article }));
  const dispoCols: Column<Dispo & { id: string }>[] = [
    { key: "article", header: t("ecarts_suivi.resa.article"), render: (d) => `${d.code} · ${d.label}`, sortValue: (d) => d.code },
    { key: "physique", header: t("ecarts_suivi.resa.physique"), num: true, render: (d) => formatNumber(Number(d.physique)), sortValue: (d) => num(d.physique) },
    { key: "reserve", header: t("ecarts_suivi.resa.reserve"), num: true, render: (d) => formatNumber(Number(d.reserve)), sortValue: (d) => num(d.reserve) },
    { key: "disponible", header: t("ecarts_suivi.resa.disponible"), num: true, render: (d) => formatNumber(Number(d.disponible)), sortValue: (d) => num(d.disponible) },
  ];
  const resaCols: Column<Reservation>[] = [
    { key: "article", header: t("ecarts_suivi.resa.article"), render: (r) => `${r.article_code} · ${r.article_label}`, sortValue: (r) => r.article_code },
    { key: "of", header: t("ecarts_suivi.resa.of"), render: (r) => r.ordre_code ?? "—", sortValue: (r) => r.ordre_code },
    {
      key: "quantite",
      header: t("ecarts_suivi.resa.quantite"),
      num: true,
      sortValue: (r) => num(r.quantite),
      render: (r) => (
        <>
          {formatNumber(Number(r.quantite))}{" "}
          <span className="muted">
            ({t("ecarts_suivi.resa.reste")} {formatNumber(Number(r.reste))})
          </span>
        </>
      ),
    },
    {
      key: "statut",
      header: t("ecarts_suivi.resa.statut"),
      sortValue: (r) => r.statut_label,
      render: (r) => (
        <>
          <Badge tone={r.statut === "active" ? "warn" : r.statut === "consommee" ? "ok" : "brand"}>{r.statut_label}</Badge> <span className="muted">{r.motif}</span>
        </>
      ),
    },
    {
      key: "actions",
      header: <span className="sr-only">{t("ui.actions")}</span>,
      render: (r) =>
        r.statut === "active" ? (
          <ActionBar
            actions={[
              { label: t("ecarts_suivi.resa.liberer"), path: `/api/stocks/reservations/${r.id}/liberer/`, tone: "ghost" as const, prompt: { name: "motif", label: t("ecarts_suivi.motif") } },
            ]}
          />
        ) : null,
    },
  ];
  return (
    <SectionCard title={t("ecarts_suivi.resa.title")}>
      <p className="muted">
        {t("ecarts_suivi.resa.note")} {dispo.data && <Badge tone="warn">{dispo.data.bloquante ? t("ecarts_suivi.resa.bloquante") : t("ecarts_suivi.resa.alerte")}</Badge>}
      </p>
      <div data-testid="disponibilites-stock">
        <DataTable columns={dispoCols} rows={dispoRows} caption={t("ecarts_suivi.resa.disponible")} loading={dispo.isLoading} />
      </div>
      <div data-testid="reservations-stock">
        <DataTable columns={resaCols} rows={resas} caption={t("ecarts_suivi.resa.title")} />
      </div>
    </SectionCard>
  );
}

// --------------------------------------------------------------------------------------------- M1 → M10
interface RetenueRow {
  affaire: string;
  affaire_code: string;
  affaire_label: string;
  factures: number;
  retenue: string | null;
  liberee: string | null;
  solde: string | null;
  date_liberation: string | null;
  echue: boolean;
}

export function RetenuesGarantieSection() {
  const { t } = useTranslation();
  const q = useQuery({
    queryKey: ["suivi", "retenues"],
    queryFn: () => api.get<{ rows: RetenueRow[]; compte: string | null; provisoire: boolean }>("/api/comptabilite/retenues-garantie/"),
    retry: 0,
  });
  const rgRows = (q.data?.rows ?? []).map((r) => ({ ...r, id: r.affaire }));
  const rgCols: Column<RetenueRow & { id: string }>[] = [
    { key: "affaire", header: t("ecarts_suivi.affaire"), render: (r) => `${r.affaire_code} · ${r.affaire_label}`, sortValue: (r) => r.affaire_code },
    { key: "factures", header: t("ecarts_suivi.rg.factures"), num: true, render: (r) => formatNumber(r.factures), sortValue: (r) => r.factures },
    { key: "retenue", header: t("ecarts_suivi.rg.retenue"), num: true, render: (r) => fcfa(r.retenue), sortValue: (r) => num(r.retenue) },
    { key: "liberee", header: t("ecarts_suivi.rg.liberee"), num: true, render: (r) => fcfa(r.liberee), sortValue: (r) => num(r.liberee) },
    { key: "solde", header: t("ecarts_suivi.rg.solde"), num: true, render: (r) => fcfa(r.solde), sortValue: (r) => num(r.solde) },
    {
      key: "echeance",
      header: t("ecarts_suivi.rg.echeance"),
      sortValue: (r) => r.date_liberation,
      render: (r) => (
        <>
          {r.date_liberation ? formatDate(r.date_liberation) : "—"} {r.echue && <Badge tone="ok">{t("ecarts_suivi.rg.echue")}</Badge>}
        </>
      ),
    },
    {
      key: "actions",
      header: <span className="sr-only">{t("ui.actions")}</span>,
      render: (r) =>
        r.solde === null || Number(r.solde) > 0 ? (
          <ActionBar
            actions={[
              r.echue
                ? { label: t("ecarts_suivi.rg.liberer"), path: `/api/comptabilite/retenues-garantie/${r.affaire}/liberer/`, confirm: t("ecarts_suivi.rg.confirmer") }
                : {
                    label: t("ecarts_suivi.rg.libererAnticipe"),
                    path: `/api/comptabilite/retenues-garantie/${r.affaire}/liberer/`,
                    tone: "ghost" as const,
                    prompt: { name: "motif", label: t("ecarts_suivi.motif") },
                  },
            ]}
          />
        ) : null,
    },
  ];
  return (
    <SectionCard title={t("ecarts_suivi.rg.title")}>
      <p className="muted">{t("ecarts_suivi.rg.note", { compte: q.data?.compte ?? "4117" })}</p>
      {q.data?.provisoire && (
        <p className="action-error" role="note">
          {t("ecarts_suivi.provisoire")}
        </p>
      )}
      <div data-testid="retenues-garantie">
        <DataTable columns={rgCols} rows={rgRows} caption={t("ecarts_suivi.rg.title")} loading={q.isLoading} />
      </div>
    </SectionCard>
  );
}

// --------------------------------------------------------------------------------------------- import GL / SAGE
interface Gabarit {
  id: string;
  code: string;
  label: string;
  separateur: string;
  encodage: string;
  format_date: string;
  separateur_decimal: string;
  colonnes: Record<string, string>;
  est_provisoire: boolean;
}
interface Batch {
  id: string;
  connector_label: string;
  status: string;
  status_label: string;
  filename: string;
  total_rows: number;
  created_rows: number;
  error_rows: number;
  error_message: string;
  created_at: string;
}

function GabaritForm({ g }: { g: Gabarit }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [v, setV] = useState({ separateur: g.separateur, encodage: g.encodage, format_date: g.format_date, separateur_decimal: g.separateur_decimal, colonnes: JSON.stringify(g.colonnes, null, 1) });
  const [erreur, setErreur] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: () => {
      let colonnes: unknown;
      try {
        colonnes = JSON.parse(v.colonnes);
      } catch {
        throw new Error(t("ecarts_suivi.import.jsonInvalide"));
      }
      return api.patch(`/api/integrations/gabarits/${g.id}/`, { ...v, colonnes });
    },
    onSuccess: () => {
      setErreur(null);
      void qc.invalidateQueries({ queryKey: ["suivi", "gabarits"] });
    },
    onError: (e) => setErreur(e instanceof Error ? e.message : t("ecarts_suivi.erreur")),
  });
  const champ = (k: "separateur" | "encodage" | "format_date" | "separateur_decimal") => (
    <label className="field" key={k}>
      <span>{t(`ecarts_suivi.import.${k}`)}</span>
      <input value={v[k]} onChange={(e) => setV({ ...v, [k]: e.target.value })} />
    </label>
  );
  return (
    <div data-testid={`gabarit-${g.code}`}>
      <p>
        <strong>{g.code}</strong> · {g.label} <Badge tone={g.est_provisoire ? "warn" : "ok"}>{g.est_provisoire ? t("ecarts_suivi.provisoire") : t("ecarts_suivi.confirme")}</Badge>
      </p>
      <div className="action-bar-buttons">
        {champ("separateur")}
        {champ("encodage")}
        {champ("format_date")}
        {champ("separateur_decimal")}
      </div>
      <label className="field">
        <span>{t("ecarts_suivi.import.colonnes")}</span>
        <textarea rows={6} value={v.colonnes} onChange={(e) => setV({ ...v, colonnes: e.target.value })} />
      </label>
      {erreur && <p className="action-error">{erreur}</p>}
      <div className="action-bar-buttons">
        <button type="button" className="btn" onClick={() => save.mutate()} disabled={save.isPending}>
          {t("ecarts_suivi.enregistrer")}
        </button>
        {g.est_provisoire && <ActionBar actions={[{ label: t("ecarts_suivi.confirmer"), path: `/api/integrations/gabarits/${g.id}/confirmer/`, tone: "ghost" as const }]} />}
      </div>
    </div>
  );
}

export function ImportGrandLivreSection() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const gabarits = useQuery({ queryKey: ["suivi", "gabarits"], queryFn: () => api.listAll<Gabarit>("/api/integrations/gabarits/", { maxPages: 1 }), retry: 0 }).data ?? [];
  const lots = useQuery({ queryKey: ["suivi", "lots"], queryFn: () => api.get<{ results: Batch[] }>("/api/integrations/batches/?page_size=10"), retry: 0 }).data?.results ?? [];
  const [connecteur, setConnecteur] = useState("gl");
  const [fichier, setFichier] = useState<File | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const envoyer = useMutation({
    mutationFn: () => api.upload<Batch>("/api/integrations/import/", fichier as File, "file", connecteur === "sage" ? { connector: "sage", gabarit: "SAGE_GL" } : { connector: connecteur }),
    onSuccess: (b) => {
      setMessage(t("ecarts_suivi.import.resultat", { crees: b.created_rows, erreurs: b.error_rows, total: b.total_rows }));
      void qc.invalidateQueries({ queryKey: ["suivi", "lots"] });
    },
    onError: () => setMessage(t("ecarts_suivi.erreur")),
  });
  const lotCols: Column<Batch>[] = [
    {
      key: "fichier",
      header: t("ecarts_suivi.import.fichier"),
      sortValue: (b) => b.created_at,
      render: (b) => (
        <>
          {b.filename} <span className="muted">{formatDateTime(b.created_at)}</span>
        </>
      ),
    },
    { key: "connecteur", header: t("ecarts_suivi.import.connecteur"), render: (b) => b.connector_label },
    {
      key: "statut",
      header: t("ecarts_suivi.resa.statut"),
      render: (b) => (
        <>
          <Badge tone={b.status === "success" ? "ok" : b.status === "failed" ? "err" : "warn"}>{b.status_label}</Badge> <span className="muted">{b.error_message}</span>
        </>
      ),
    },
    {
      key: "lignes",
      header: t("ecarts_suivi.import.lignes"),
      num: true,
      render: (b) => (
        <>
          {formatNumber(b.created_rows)} / {formatNumber(b.total_rows)} {b.error_rows > 0 && <Badge tone="err">{t("ecarts_suivi.import.erreurs", { n: b.error_rows })}</Badge>}
        </>
      ),
    },
  ];
  return (
    <SectionCard title={t("ecarts_suivi.import.title")}>
      <p className="muted">{t("ecarts_suivi.import.note")}</p>
      <div className="action-bar-buttons">
        <label className="field">
          <span>{t("ecarts_suivi.import.connecteur")}</span>
          <select value={connecteur} onChange={(e) => setConnecteur(e.target.value)}>
            <option value="gl">{t("ecarts_suivi.import.gl")}</option>
            <option value="sage">{t("ecarts_suivi.import.sage")}</option>
          </select>
        </label>
        <label className="field">
          <span>{t("ecarts_suivi.import.fichier")}</span>
          <input type="file" accept=".csv,.txt,.xml" onChange={(e) => setFichier(e.target.files?.[0] ?? null)} />
        </label>
        <button type="button" className="btn primary" disabled={!fichier || envoyer.isPending} onClick={() => envoyer.mutate()}>
          {t("ecarts_suivi.import.importer")}
        </button>
      </div>
      {message && <p role="status">{message}</p>}
      <div data-testid="lots-import">
        <DataTable columns={lotCols} rows={lots} caption={t("ecarts_suivi.import.title")} />
      </div>
      <h4>{t("ecarts_suivi.import.gabarit")}</h4>
      {gabarits.map((g) => (
        <GabaritForm key={`${g.id}-${g.est_provisoire}`} g={g} />
      ))}
    </SectionCard>
  );
}

// --------------------------------------------------------------------------------------------- M4 → M3
interface Machine {
  equipement: string;
  label: string;
  of: string | null;
  debut: string | null;
  fin: string | null;
  source: string;
  location?: string;
  compteur: string;
}
interface Bl {
  code: string;
  reference_bl: string;
  date: string;
  ecart_pct: string;
  litige: boolean;
}
interface FluxBloc {
  affaire: string | null;
  titre: string;
  machines: Machine[];
  consommation_gr: string;
  bl: Bl[];
}

export function FluxM4Section() {
  const { t } = useTranslation();
  const rows = useQuery({ queryKey: ["suivi", "flux-m4"], queryFn: () => api.get<{ rows: FluxBloc[] }>("/api/operations/flux-m4/"), retry: 0 }).data?.rows ?? [];
  const machineCols: Column<Machine & { id: string }>[] = [
    { key: "machine", header: t("ecarts_suivi.flux.machine"), render: (m) => `${m.equipement} · ${m.label}`, sortValue: (m) => m.equipement },
    {
      key: "source",
      header: t("ecarts_suivi.flux.source"),
      render: (m) => <Badge tone={m.source === "gr" ? "warn" : "brand"}>{m.source === "gr" ? `GR ${m.location ?? ""}` : t("ecarts_suivi.flux.parc")}</Badge>,
    },
    { key: "of", header: t("ecarts_suivi.resa.of"), render: (m) => m.of ?? "—", sortValue: (m) => m.of },
    {
      key: "periode",
      header: t("ecarts_suivi.flux.periode"),
      sortValue: (m) => m.debut,
      render: (m) => `${m.debut ? formatDate(m.debut) : "—"} → ${m.fin ? formatDate(m.fin) : "…"}`,
    },
    { key: "compteur", header: t("ecarts_suivi.flux.compteur"), num: true, render: (m) => formatNumber(Number(m.compteur)), sortValue: (m) => num(m.compteur) },
  ];
  return (
    <SectionCard title={t("ecarts_suivi.flux.title")}>
      <p className="muted">{t("ecarts_suivi.flux.note")}</p>
      {rows.length === 0 && <p className="muted">{t("ecarts_suivi.flux.vide")}</p>}
      {rows.map((b) => (
        <div key={b.affaire ?? "aucune"} data-testid="flux-m4-affaire">
          <h4>
            {b.affaire ?? "—"} · {b.titre} <span className="muted">— {t("ecarts_suivi.flux.consoGr")} {formatNumber(Number(b.consommation_gr))}</span>
          </h4>
          <DataTable columns={machineCols} rows={b.machines.map((m, i) => ({ ...m, id: `${m.equipement}-${i}` }))} caption={`${b.affaire ?? "—"} · ${b.titre}`} />
          {b.bl.length > 0 && (
            <ul>
              {b.bl.map((l) => (
                <li key={l.code}>
                  {t("ecarts_suivi.flux.bl")} {l.reference_bl || l.code} · {formatDate(l.date)} · {t("ecarts_suivi.flux.ecart")} {pct(l.ecart_pct)}{" "}
                  {l.litige && <Badge tone="err">{t("ecarts_suivi.flux.litige")}</Badge>}
                </li>
              ))}
            </ul>
          )}
        </div>
      ))}
    </SectionCard>
  );
}
