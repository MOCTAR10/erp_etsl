import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate, formatDateTime, formatNumber } from "../../lib/format";
import { ActionBar, Badge, SectionCard } from "../ui";

/* Lot de suivi inter-modules : M3 → M11 (marge à terminaison), M10 → M11 (balance âgée), M3 → M5 (réservations),
   M1 → M10 (retenue de garantie), import du grand livre / gabarit SAGE, M4 → M3 (flux machines, compteurs, BL). */

const fcfa = (v: string | null | undefined) => (v === null || v === undefined ? "—" : `${formatNumber(Number(v))} F`);
const pct = (v: string | null | undefined) => (v === null || v === undefined ? "—" : `${formatNumber(Number(v))} %`);

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
  return (
    <SectionCard title={t("ecarts_suivi.marges.title")}>
      <p className="muted">{t("ecarts_suivi.marges.note")}</p>
      <ActionBar
        actions={[
          { label: t("ecarts_suivi.marges.integrer", { n: q.data?.en_attente ?? 0 }), path: "/api/controle-gestion/marges-terminaison/integrer/", tone: "ghost" as const },
        ]}
      />
      <div className="table-wrap">
        <table className="table" data-testid="marges-terminaison">
          <thead>
            <tr>
              <th>{t("ecarts_suivi.affaire")}</th>
              <th>{t("ecarts_suivi.marges.avancement")}</th>
              <th>{t("ecarts_suivi.marges.ca")}</th>
              <th>{t("ecarts_suivi.marges.engage")}</th>
              <th>{t("ecarts_suivi.marges.cat")}</th>
              <th>{t("ecarts_suivi.marges.marge")}</th>
              <th>{t("ecarts_suivi.marges.publie")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={7} className="muted">
                  {t("ecarts_suivi.marges.vide")}
                </td>
              </tr>
            )}
            {rows.map((r) => (
              <tr key={r.id}>
                <td>
                  {r.affaire_code} · {r.affaire_label}
                </td>
                <td>{pct(r.avancement_pct)}</td>
                <td>{fcfa(r.chiffre_affaires)}</td>
                <td>{fcfa(r.couts_engages)}</td>
                <td>{fcfa(r.cout_a_terminaison)}</td>
                <td>
                  {fcfa(r.marge_a_terminaison)} {r.marge_pct !== null && `(${pct(r.marge_pct)})`}{" "}
                  {r.alerte && <Badge tone="err">{t("ecarts_suivi.marges.negative")}</Badge>}
                </td>
                <td>{r.publie_le ? formatDateTime(r.publie_le) : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
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

function TableEtat({ etat }: { etat: Etat }) {
  return (
    <>
      <h4>{etat.titre}</h4>
      <p className="muted">{etat.sous_titre}</p>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              {etat.colonnes.map((c) => (
                <th key={c.key}>{c.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {etat.lignes.map((l, i) => (
              <tr key={i} style={l.total_ligne ? { fontWeight: 600 } : undefined}>
                {etat.colonnes.map((c) => (
                  <td key={c.key}>{c.montant ? fcfa(l[c.key] as string | null) : String(l[c.key] ?? "")}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
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
  return (
    <SectionCard title={t("ecarts_suivi.resa.title")}>
      <p className="muted">
        {t("ecarts_suivi.resa.note")} {dispo.data && <Badge tone="warn">{dispo.data.bloquante ? t("ecarts_suivi.resa.bloquante") : t("ecarts_suivi.resa.alerte")}</Badge>}
      </p>
      <table className="table" data-testid="disponibilites-stock">
        <thead>
          <tr>
            <th>{t("ecarts_suivi.resa.article")}</th>
            <th>{t("ecarts_suivi.resa.physique")}</th>
            <th>{t("ecarts_suivi.resa.reserve")}</th>
            <th>{t("ecarts_suivi.resa.disponible")}</th>
          </tr>
        </thead>
        <tbody>
          {(dispo.data?.rows ?? []).map((d) => (
            <tr key={d.article}>
              <td>
                {d.code} · {d.label}
              </td>
              <td>{formatNumber(Number(d.physique))}</td>
              <td>{formatNumber(Number(d.reserve))}</td>
              <td>{formatNumber(Number(d.disponible))}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="table-wrap">
        <table className="table" data-testid="reservations-stock">
          <thead>
            <tr>
              <th>{t("ecarts_suivi.resa.article")}</th>
              <th>{t("ecarts_suivi.resa.of")}</th>
              <th>{t("ecarts_suivi.resa.quantite")}</th>
              <th>{t("ecarts_suivi.resa.statut")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {resas.map((r) => (
              <tr key={r.id}>
                <td>
                  {r.article_code} · {r.article_label}
                </td>
                <td>{r.ordre_code ?? "—"}</td>
                <td>
                  {formatNumber(Number(r.quantite))} ({t("ecarts_suivi.resa.reste")} {formatNumber(Number(r.reste))})
                </td>
                <td>
                  <Badge tone={r.statut === "active" ? "warn" : r.statut === "consommee" ? "ok" : "brand"}>{r.statut_label}</Badge>{" "}
                  <span className="muted">{r.motif}</span>
                </td>
                <td>
                  {r.statut === "active" && (
                    <ActionBar
                      actions={[
                        { label: t("ecarts_suivi.resa.liberer"), path: `/api/stocks/reservations/${r.id}/liberer/`, tone: "ghost" as const, prompt: { name: "motif", label: t("ecarts_suivi.motif") } },
                      ]}
                    />
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
  return (
    <SectionCard title={t("ecarts_suivi.rg.title")}>
      <p className="muted">{t("ecarts_suivi.rg.note", { compte: q.data?.compte ?? "4117" })}</p>
      {q.data?.provisoire && (
        <p className="action-error" role="note">
          {t("ecarts_suivi.provisoire")}
        </p>
      )}
      <div className="table-wrap">
        <table className="table" data-testid="retenues-garantie">
          <thead>
            <tr>
              <th>{t("ecarts_suivi.affaire")}</th>
              <th>{t("ecarts_suivi.rg.factures")}</th>
              <th>{t("ecarts_suivi.rg.retenue")}</th>
              <th>{t("ecarts_suivi.rg.liberee")}</th>
              <th>{t("ecarts_suivi.rg.solde")}</th>
              <th>{t("ecarts_suivi.rg.echeance")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {(q.data?.rows ?? []).map((r) => (
              <tr key={r.affaire}>
                <td>
                  {r.affaire_code} · {r.affaire_label}
                </td>
                <td>{r.factures}</td>
                <td>{fcfa(r.retenue)}</td>
                <td>{fcfa(r.liberee)}</td>
                <td>{fcfa(r.solde)}</td>
                <td>
                  {r.date_liberation ? formatDate(r.date_liberation) : "—"} {r.echue && <Badge tone="ok">{t("ecarts_suivi.rg.echue")}</Badge>}
                </td>
                <td>
                  {(r.solde === null || Number(r.solde) > 0) && (
                    <ActionBar
                      actions={[
                        r.echue
                          ? { label: t("ecarts_suivi.rg.liberer"), path: `/api/comptabilite/retenues-garantie/${r.affaire}/liberer/`, confirm: t("ecarts_suivi.rg.confirmer") }
                          : { label: t("ecarts_suivi.rg.libererAnticipe"), path: `/api/comptabilite/retenues-garantie/${r.affaire}/liberer/`, tone: "ghost" as const, prompt: { name: "motif", label: t("ecarts_suivi.motif") } },
                      ]}
                    />
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
      <table className="table" data-testid="lots-import">
        <thead>
          <tr>
            <th>{t("ecarts_suivi.import.fichier")}</th>
            <th>{t("ecarts_suivi.import.connecteur")}</th>
            <th>{t("ecarts_suivi.resa.statut")}</th>
            <th>{t("ecarts_suivi.import.lignes")}</th>
          </tr>
        </thead>
        <tbody>
          {lots.map((b) => (
            <tr key={b.id}>
              <td>
                {b.filename} <span className="muted">{formatDateTime(b.created_at)}</span>
              </td>
              <td>{b.connector_label}</td>
              <td>
                <Badge tone={b.status === "success" ? "ok" : b.status === "failed" ? "err" : "warn"}>{b.status_label}</Badge> <span className="muted">{b.error_message}</span>
              </td>
              <td>
                {b.created_rows} / {b.total_rows} {b.error_rows > 0 && <Badge tone="err">{t("ecarts_suivi.import.erreurs", { n: b.error_rows })}</Badge>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
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
  return (
    <SectionCard title={t("ecarts_suivi.flux.title")}>
      <p className="muted">{t("ecarts_suivi.flux.note")}</p>
      {rows.length === 0 && <p className="muted">{t("ecarts_suivi.flux.vide")}</p>}
      {rows.map((b) => (
        <div key={b.affaire ?? "aucune"} data-testid="flux-m4-affaire">
          <h4>
            {b.affaire ?? "—"} · {b.titre} <span className="muted">— {t("ecarts_suivi.flux.consoGr")} {formatNumber(Number(b.consommation_gr))}</span>
          </h4>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>{t("ecarts_suivi.flux.machine")}</th>
                  <th>{t("ecarts_suivi.flux.source")}</th>
                  <th>{t("ecarts_suivi.resa.of")}</th>
                  <th>{t("ecarts_suivi.flux.periode")}</th>
                  <th>{t("ecarts_suivi.flux.compteur")}</th>
                </tr>
              </thead>
              <tbody>
                {b.machines.map((m, i) => (
                  <tr key={`${m.equipement}-${i}`}>
                    <td>
                      {m.equipement} · {m.label}
                    </td>
                    <td>
                      <Badge tone={m.source === "gr" ? "warn" : "brand"}>{m.source === "gr" ? `GR ${m.location ?? ""}` : t("ecarts_suivi.flux.parc")}</Badge>
                    </td>
                    <td>{m.of ?? "—"}</td>
                    <td>
                      {m.debut ? formatDate(m.debut) : "—"} → {m.fin ? formatDate(m.fin) : "…"}
                    </td>
                    <td>{formatNumber(Number(m.compteur))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
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
