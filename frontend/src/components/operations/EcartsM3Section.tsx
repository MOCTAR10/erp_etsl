import { useQuery } from "@tanstack/react-query";
import { FileDown } from "lucide-react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate, formatMoney, formatNumber } from "../../lib/format";
import { ActionBar, Badge, Kpi, QuickForm, SectionCard } from "../ui";

interface Parametre {
  id: string;
  code: string;
  label: string;
  valeur: string;
  unite: string;
  est_provisoire: boolean;
  confirme_par_nom: string | null;
}
interface Of {
  id: string;
  code: string;
  label: string;
  status: string;
  status_label: string;
  scope: string;
  planned_start: string | null;
  planned_end: string | null;
  motif_replanification: string;
}
interface Besoin {
  id: string;
  ordre_code: string;
  article_code: string;
  article_label: string;
  quantite: string;
  statut: string;
  statut_label: string;
  disponible: string | null;
  demande_achat_code: string | null;
}
interface Fiche {
  id: string;
  code: string;
  ordre_code: string;
  outillage: string;
  statut: string;
  statut_label: string;
  valide_par_nom: string | null;
}
interface Rapport {
  id: string;
  code: string;
  ordre_code: string;
  type_label: string;
  date: string;
  quantite_realisee: string;
  quantite_rebut: string;
  avancement: number | null;
  statut: string;
  statut_label: string;
}
interface FicheControle {
  id: string;
  code: string;
  ordre_code: string;
  date: string;
  objet: string;
  conforme: boolean;
  controle_par_nom: string | null;
}
interface Transfert {
  id: string;
  code: string;
  type_label: string;
  ordre_code: string;
  destination: string;
  lignes: { designation: string; quantite: string }[];
  statut: string;
  statut_label: string;
  reserves: string;
}
interface AttachementRow {
  id: string;
  code: string;
  ordre_code: string;
  situation_code: string | null;
  date: string;
  designation: string;
  unite: string;
  quantite: string;
  montant: string | null;
  statut: string;
  statut_label: string;
  signataire_client: string;
}
interface Situation {
  id: string;
  code: string;
  label: string;
  status: string;
  status_label: string;
  amount: string | null;
  montant_attachements: string | null;
  recue_le: string | null;
  recue_signataire: string;
}
interface Pointage {
  id: string;
  code: string;
  ordre_code: string;
  worker_name_filled: string | null;
  date: string;
  hours: string;
  hours_type_label: string;
  nature_mo_label: string;
  status: string;
  status_label: string;
}
interface AffaireSuivi {
  affaire: string;
  affaire_code: string;
  affaire_label: string;
  avancement_pct: string | null;
  chiffre_affaires: string | null;
  couts_engages: string | null;
  cout_a_terminaison: string | null;
  marge_a_terminaison: string | null;
  marge_pct: string | null;
}
interface OfSuivi {
  ordre: string;
  code: string;
  label: string;
  affaire: string | null;
  avancement_pct: string | null;
}
interface Suivi {
  methode: number;
  ordres: OfSuivi[];
  affaires: AffaireSuivi[];
}
interface Indicateurs {
  productivite_pct: string | null;
  taux_rebut_pct: string | null;
  heures_directes: string;
  heures_indirectes: string;
  of_en_retard: number;
  ruptures_ouvertes: number;
}
interface ChargeJour {
  date: string;
  scope: string;
  resource: string;
  planned_hours: string;
  capacity: string | null;
  overload: boolean;
}
interface Escalade {
  id: string;
  scope: string;
  resource: string;
  semaine: string;
  surcharge_pct: string;
}
interface Registre {
  id: string;
  titre: string;
  reference: string;
  type: string | null;
  objet: string;
  lie_le: string;
}
interface Dossier {
  id: string;
  ordre_code: string;
  sha256: string;
  retention_years: number;
  created_at: string;
}
interface Option {
  id: string;
  code: string;
  label?: string;
  title?: string;
  nom_complet?: string;
}

const fcfa = (v: string | null) => formatMoney(v);
const pct = (v: string | null) => (v === null ? "—" : `${formatNumber(Number(v))} %`);
const q = <T,>(key: string, path: string) => ({ queryKey: ["ecarts-m3", key], queryFn: () => api.listAll<T>(path), retry: 0 });

function Pdf({ path, name, label }: { path: string; name: string; label: string }) {
  return (
    <button type="button" className="btn ghost" onClick={() => void api.download(path, name).catch(() => undefined)}>
      <FileDown size={14} aria-hidden="true" /> {label}
    </button>
  );
}

/** Écarts M3 (lot 2) : paramètres provisoires, préparation, rapports, transferts, attachements, suivi, reporting, registre. */
export function EcartsM3Section() {
  const { t } = useTranslation();
  const k = (s: string) => t(`ecarts_m3.${s}`);
  const parametres = useQuery(q<Parametre>("parametres", "/api/operations/parametres/")).data ?? [];
  const ordres = useQuery(q<Of>("ordres", "/api/operations/ordres/")).data ?? [];
  const besoins = useQuery(q<Besoin>("besoins", "/api/operations/besoins-matiere/")).data ?? [];
  const fiches = useQuery(q<Fiche>("fiches", "/api/operations/fiches-preparation/")).data ?? [];
  const rapports = useQuery(q<Rapport>("rapports", "/api/operations/rapports/")).data ?? [];
  const controles = useQuery(q<FicheControle>("controles", "/api/operations/fiches-controle/")).data ?? [];
  const transferts = useQuery(q<Transfert>("transferts", "/api/operations/transferts/")).data ?? [];
  const attachements = useQuery(q<AttachementRow>("attachements", "/api/operations/attachements/")).data ?? [];
  const situations = useQuery(q<Situation>("situations", "/api/operations/situations/")).data ?? [];
  const pointages = useQuery(q<Pointage>("pointages", "/api/operations/pointages/?page_size=100")).data ?? [];
  const escalades = useQuery(q<Escalade>("escalades", "/api/operations/escalades/")).data ?? [];
  const dossiers = useQuery(q<Dossier>("dossiers", "/api/operations/dossiers/")).data ?? [];
  const articles = useQuery(q<Option>("articles", "/api/referentiels/articles/")).data ?? [];
  const affaires = useQuery(q<Option>("affaires", "/api/commercial/affaires/")).data ?? [];
  const employes = useQuery(q<Option>("employes", "/api/rh-paie/employes/")).data ?? [];
  const suivi = useQuery({ queryKey: ["ecarts-m3", "suivi"], queryFn: () => api.get<Suivi>("/api/operations/ordres/suivi/"), retry: 0 }).data;
  const ind = useQuery({ queryKey: ["ecarts-m3", "indicateurs"], queryFn: () => api.get<Indicateurs>("/api/operations/ordres/indicateurs/"), retry: 0 }).data;
  const charge = useQuery({
    queryKey: ["ecarts-m3", "charge-jour"],
    queryFn: () => api.get<{ lignes: ChargeJour[] }>("/api/operations/ordres/charge-journaliere/?jours=14"),
    retry: 0,
  }).data;
  const registre = useQuery({ queryKey: ["ecarts-m3", "registre"], queryFn: () => api.get<Registre[]>("/api/operations/dossiers/registre/"), retry: 0 }).data ?? [];

  const ofOpts = ordres.filter((o) => o.status !== "annule").map((o) => ({ value: o.id, label: `${o.code} — ${o.label}` }));
  const ofActifs = ofOpts.filter((o) => !ordres.find((x) => x.id === o.value && x.status === "cloture"));
  const articleOpts = articles.map((a) => ({ value: a.id, label: `${a.code} — ${a.label ?? ""}` }));
  const affaireOpts = affaires.map((a) => ({ value: a.id, label: `${a.code} — ${a.title ?? ""}` }));
  const employeOpts = employes.map((e) => ({ value: e.id, label: `${e.code} — ${e.nom_complet ?? ""}` }));
  const situationOpts = situations
    .filter((s) => s.status === "brouillon" || s.status === "soumise")
    .map((s) => ({ value: s.id, label: `${s.code} — ${s.label}` }));
  const provisoires = parametres.filter((p) => p.est_provisoire).length;
  const lignesSurcharge = (charge?.lignes ?? []).filter((l) => Number(l.planned_hours) > 0);

  return (
    <>
      <SectionCard title={`${k("parametres.title")} · ${parametres.length}`}>
        {provisoires > 0 && (
          <p data-testid="m3-provisoire">
            <Badge tone="warn">{k("provisoire")}</Badge> {t("ecarts_m3.parametres.bandeau", { n: provisoires })}
          </p>
        )}
        <table className="table" data-testid="m3-parametres">
          <thead>
            <tr>
              <th>{k("parametres.libelle")}</th>
              <th>{k("parametres.valeur")}</th>
              <th>{k("parametres.statut")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {parametres.map((p) => (
              <tr key={p.id}>
                <td>
                  <span className="muted">{p.code}</span>
                  <br />
                  {p.label}
                </td>
                <td>
                  {formatNumber(Number(p.valeur))} {p.unite}
                </td>
                <td>{p.est_provisoire ? <Badge tone="warn">{k("provisoire")}</Badge> : <Badge tone="ok">{k("confirme")}</Badge>}</td>
                <td>
                  <ActionBar
                    actions={[
                      { label: k("parametres.modifier"), path: `/api/operations/parametres/${p.id}/modifier/`, tone: "ghost" as const, prompt: { name: "valeur", label: k("parametres.valeur") } },
                      ...(p.est_provisoire ? [{ label: k("parametres.confirmer"), path: `/api/operations/parametres/${p.id}/confirmer/`, confirm: k("parametres.confirmerQ") }] : []),
                    ]}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </SectionCard>

      <SectionCard title={k("preparation.title")}>
        <div className="action-bar-buttons">
          <QuickForm
            title={k("preparation.fiche")}
            endpoint="/api/operations/fiches-preparation/"
            fields={[
              { name: "ordre", label: k("of"), type: "select", options: ofActifs, required: true },
              { name: "outillage", label: k("preparation.outillage"), type: "textarea" },
              { name: "consignes", label: k("preparation.consignes"), type: "textarea" },
            ]}
          />
          <QuickForm
            title={k("preparation.besoin")}
            endpoint="/api/operations/besoins-matiere/"
            fields={[
              { name: "ordre", label: k("of"), type: "select", options: ofActifs, required: true },
              { name: "article", label: k("preparation.article"), type: "select", options: articleOpts, required: true },
              { name: "quantite", label: k("preparation.quantite"), type: "number", min: 0, step: "0.01", required: true },
            ]}
          />
        </div>
        <table className="table" data-testid="m3-fiches-preparation">
          <thead>
            <tr>
              <th>{k("code")}</th>
              <th>{k("of")}</th>
              <th>{k("preparation.outillage")}</th>
              <th>{k("statut")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {fiches.map((f) => (
              <tr key={f.id}>
                <td>{f.code}</td>
                <td>{f.ordre_code}</td>
                <td>{f.outillage || "—"}</td>
                <td>
                  <Badge tone={f.statut === "validee" ? "ok" : "warn"}>{f.statut_label}</Badge> {f.valide_par_nom ?? ""}
                </td>
                <td>
                  {f.statut === "brouillon" && <ActionBar actions={[{ label: k("preparation.valider"), path: `/api/operations/fiches-preparation/${f.id}/valider/` }]} />}
                  <Pdf path={`/api/operations/fiches-preparation/${f.id}/?export=pdf`} name={`${f.code}.pdf`} label={k("pdf")} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <table className="table" data-testid="m3-besoins">
          <thead>
            <tr>
              <th>{k("of")}</th>
              <th>{k("preparation.article")}</th>
              <th>{k("preparation.quantite")}</th>
              <th>{k("preparation.disponible")}</th>
              <th>{k("statut")}</th>
              <th>{k("preparation.da")}</th>
            </tr>
          </thead>
          <tbody>
            {besoins.map((b) => (
              <tr key={b.id}>
                <td>{b.ordre_code}</td>
                <td>
                  {b.article_code} · {b.article_label}
                </td>
                <td>{formatNumber(Number(b.quantite))}</td>
                <td>{b.disponible === null ? "—" : formatNumber(Number(b.disponible))}</td>
                <td>
                  <Badge tone={b.statut === "rupture" ? "err" : b.statut === "reserve" || b.statut === "servi" ? "ok" : "warn"}>{b.statut_label}</Badge>
                </td>
                <td>{b.demande_achat_code ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted">{k("preparation.note")}</p>
      </SectionCard>

      <SectionCard title={k("rapports.title")}>
        <div className="action-bar-buttons">
          <QuickForm
            title={k("rapports.ajouter")}
            endpoint="/api/operations/rapports/"
            fields={[
              { name: "ordre", label: k("of"), type: "select", options: ofActifs, required: true },
              {
                name: "type", label: k("rapports.type"), type: "select", required: true, defaultValue: "execution",
                options: [
                  { value: "execution", label: k("rapports.execution") },
                  { value: "avancement", label: k("rapports.avancement") },
                ],
              },
              { name: "date", label: k("date"), type: "date", required: true },
              { name: "quantite_realisee", label: k("rapports.realise"), type: "number", min: 0, step: "0.01" },
              { name: "quantite_rebut", label: k("rapports.rebut"), type: "number", min: 0, step: "0.01" },
              { name: "avancement", label: k("rapports.pct"), type: "number", min: 0 },
              { name: "observations", label: k("rapports.observations"), type: "textarea" },
            ]}
          />
          <QuickForm
            title={k("controle.ajouter")}
            endpoint="/api/operations/fiches-controle/"
            fields={[
              { name: "ordre", label: k("of"), type: "select", options: ofActifs, required: true },
              { name: "date", label: k("date"), type: "date", required: true },
              { name: "objet", label: k("controle.objet"), required: true },
              { name: "points", label: k("controle.points"), type: "textarea", required: true },
            ]}
            transform={(v) => ({
              ...v,
              points: (v.points ?? "")
                .split("\n")
                .map((l) => l.trim())
                .filter(Boolean)
                .map((l) => ({ libelle: l.replace(/^!\s*/, ""), conforme: !l.startsWith("!") })),
            })}
          />
        </div>
        <table className="table" data-testid="m3-rapports">
          <thead>
            <tr>
              <th>{k("code")}</th>
              <th>{k("of")}</th>
              <th>{k("rapports.type")}</th>
              <th>{k("date")}</th>
              <th>{k("rapports.realise")}</th>
              <th>{k("rapports.rebut")}</th>
              <th>{k("rapports.pct")}</th>
              <th>{k("statut")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rapports.map((r) => (
              <tr key={r.id}>
                <td>{r.code}</td>
                <td>{r.ordre_code}</td>
                <td>{r.type_label}</td>
                <td>{formatDate(r.date)}</td>
                <td>{formatNumber(Number(r.quantite_realisee))}</td>
                <td>{formatNumber(Number(r.quantite_rebut))}</td>
                <td>{r.avancement === null ? "—" : `${r.avancement} %`}</td>
                <td>
                  <Badge tone={r.statut === "valide" ? "ok" : "warn"}>{r.statut_label}</Badge>
                </td>
                <td>
                  {r.statut === "brouillon" && <ActionBar actions={[{ label: k("rapports.valider"), path: `/api/operations/rapports/${r.id}/valider/` }]} />}
                  <Pdf path={`/api/operations/rapports/${r.id}/?export=pdf`} name={`${r.code}.pdf`} label={k("pdf")} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <table className="table" data-testid="m3-fiches-controle">
          <thead>
            <tr>
              <th>{k("code")}</th>
              <th>{k("of")}</th>
              <th>{k("date")}</th>
              <th>{k("controle.objet")}</th>
              <th>{k("controle.resultat")}</th>
            </tr>
          </thead>
          <tbody>
            {controles.map((c) => (
              <tr key={c.id}>
                <td>{c.code}</td>
                <td>{c.ordre_code}</td>
                <td>{formatDate(c.date)}</td>
                <td>{c.objet}</td>
                <td>
                  <Badge tone={c.conforme ? "ok" : "err"}>{c.conforme ? k("controle.conforme") : k("controle.nonConforme")}</Badge> {c.controle_par_nom ?? ""}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted">{k("rapports.note")}</p>
      </SectionCard>

      <SectionCard title={k("transferts.title")}>
        <QuickForm
          title={k("transferts.ajouter")}
          endpoint="/api/operations/transferts/"
          fields={[
            {
              name: "type", label: k("transferts.type"), type: "select", required: true, defaultValue: "bl",
              options: [
                { value: "bl", label: k("transferts.bl") },
                { value: "transfert", label: k("transferts.fiche") },
              ],
            },
            { name: "ordre", label: k("of"), type: "select", options: ofActifs, required: true },
            { name: "destination", label: k("transferts.destination"), required: true },
            { name: "transporteur", label: k("transferts.transporteur") },
            { name: "lignes", label: k("transferts.lignes"), type: "textarea", required: true },
          ]}
          transform={(v) => ({
            ...v,
            lignes: (v.lignes ?? "")
              .split("\n")
              .map((l) => l.trim())
              .filter(Boolean)
              .map((l) => {
                const [designation, quantite] = l.split(";").map((x) => x.trim());
                return { designation, quantite: quantite || "1" };
              }),
          })}
        />
        <table className="table" data-testid="m3-transferts">
          <thead>
            <tr>
              <th>{k("code")}</th>
              <th>{k("of")}</th>
              <th>{k("transferts.destination")}</th>
              <th>{k("transferts.lignes")}</th>
              <th>{k("statut")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {transferts.map((b) => (
              <tr key={b.id}>
                <td>
                  {b.code} <span className="muted">{b.type_label}</span>
                </td>
                <td>{b.ordre_code}</td>
                <td>{b.destination}</td>
                <td>{b.lignes.map((l) => `${l.designation} × ${l.quantite}`).join(", ")}</td>
                <td>
                  <Badge tone={b.statut === "receptionne" ? "ok" : "warn"}>{b.statut_label}</Badge> {b.reserves}
                </td>
                <td>
                  {b.statut === "prepare" && <ActionBar actions={[{ label: k("transferts.expedier"), path: `/api/operations/transferts/${b.id}/expedier/` }]} />}
                  {b.statut === "expedie" && (
                    <ActionBar
                      actions={[{ label: k("transferts.receptionner"), path: `/api/operations/transferts/${b.id}/receptionner/`, prompt: { name: "reserves", label: k("transferts.reserves") } }]}
                    />
                  )}
                  <Pdf path={`/api/operations/transferts/${b.id}/?export=pdf`} name={`${b.code}.pdf`} label={k("pdf")} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </SectionCard>

      <SectionCard title={k("attachements.title")}>
        <div className="action-bar-buttons">
          <QuickForm
            title={k("attachements.ajouter")}
            endpoint="/api/operations/attachements/"
            fields={[
              { name: "ordre", label: k("of"), type: "select", options: ofActifs, required: true },
              { name: "situation", label: k("attachements.situation"), type: "select", options: situationOpts },
              { name: "date", label: k("date"), type: "date", required: true },
              { name: "designation", label: k("attachements.designation"), required: true },
              { name: "unite", label: k("attachements.unite"), defaultValue: "ml" },
              { name: "quantite", label: k("attachements.quantite"), type: "number", min: 0, step: "0.001", required: true },
              { name: "prix_unitaire", label: k("attachements.prix"), type: "number", min: 0 },
            ]}
          />
          <QuickForm
            title={k("attachements.repartition")}
            endpoint="/api/operations/repartitions/"
            fields={[
              { name: "ordre", label: k("of"), type: "select", options: ofActifs, required: true },
              { name: "affaire", label: k("affaire"), type: "select", options: affaireOpts, required: true },
              { name: "part_pct", label: k("attachements.part"), type: "number", min: 1, required: true },
            ]}
          />
        </div>
        <table className="table" data-testid="m3-attachements">
          <thead>
            <tr>
              <th>{k("code")}</th>
              <th>{k("of")}</th>
              <th>{k("attachements.designation")}</th>
              <th>{k("attachements.quantite")}</th>
              <th>{k("attachements.montant")}</th>
              <th>{k("statut")}</th>
            </tr>
          </thead>
          <tbody>
            {attachements.map((a) => (
              <tr key={a.id}>
                <td>
                  {a.code} {a.situation_code ? <span className="muted">· {a.situation_code}</span> : null}
                </td>
                <td>{a.ordre_code}</td>
                <td>{a.designation}</td>
                <td>
                  {formatNumber(Number(a.quantite))} {a.unite}
                </td>
                <td>{fcfa(a.montant)}</td>
                <td>
                  <Badge tone={a.statut === "signe" ? "ok" : "warn"}>{a.statut_label}</Badge> {a.signataire_client}
                  {a.statut === "brouillon" && (
                    <ActionBar
                      actions={[{ label: k("attachements.signer"), path: `/api/operations/attachements/${a.id}/signer/`, prompt: { name: "signataire_client", label: k("attachements.signataire") } }]}
                    />
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <table className="table" data-testid="m3-situations-recu">
          <thead>
            <tr>
              <th>{k("attachements.situation")}</th>
              <th>{k("attachements.montant")}</th>
              <th>{k("attachements.montantAtt")}</th>
              <th>{k("attachements.recu")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {situations.map((s) => (
              <tr key={s.id}>
                <td>
                  {s.code} · {s.label} <Badge tone={s.status === "facturee" || s.status === "validee" ? "ok" : "warn"}>{s.status_label}</Badge>
                </td>
                <td>{fcfa(s.amount)}</td>
                <td>{fcfa(s.montant_attachements)}</td>
                <td>{s.recue_le ? `${formatDate(s.recue_le)} · ${s.recue_signataire}` : "—"}</td>
                <td>
                  {(s.status === "brouillon" || s.status === "soumise") && (
                    <ActionBar actions={[{ label: k("attachements.valoriser"), path: `/api/operations/situations/${s.id}/valoriser-attachements/`, tone: "ghost" as const }]} />
                  )}
                  {(s.status === "validee" || s.status === "facturee") && !s.recue_le && (
                    <ActionBar
                      actions={[{ label: k("attachements.accuser"), path: `/api/operations/situations/${s.id}/accuser-reception/`, prompt: { name: "recue_signataire", label: k("attachements.signataire") } }]}
                    />
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </SectionCard>

      <SectionCard title={k("pointages.title")}>
        <QuickForm
          title={k("pointages.ajouter")}
          endpoint="/api/operations/pointages/"
          fields={[
            { name: "ordre", label: k("of"), type: "select", options: ofActifs, required: true },
            { name: "employe", label: k("pointages.salarie"), type: "select", options: employeOpts },
            { name: "worker_name", label: k("pointages.nomLibre") },
            { name: "date", label: k("date"), type: "date", required: true },
            { name: "hours", label: k("pointages.heures"), type: "number", min: 0, step: "0.25", required: true },
            {
              name: "hours_type", label: k("pointages.type"), type: "select", defaultValue: "normal",
              options: ["normal", "supplementaire", "nuit", "astreinte"].map((v) => ({ value: v, label: k(`pointages.types.${v}`) })),
            },
            {
              name: "nature_mo", label: k("pointages.nature"), type: "select", defaultValue: "directe",
              options: [
                { value: "directe", label: k("pointages.directe") },
                { value: "indirecte", label: k("pointages.indirecte") },
              ],
            },
          ]}
        />
        <table className="table" data-testid="m3-pointages">
          <thead>
            <tr>
              <th>{k("code")}</th>
              <th>{k("of")}</th>
              <th>{k("pointages.salarie")}</th>
              <th>{k("date")}</th>
              <th>{k("pointages.heures")}</th>
              <th>{k("pointages.nature")}</th>
              <th>{k("statut")}</th>
            </tr>
          </thead>
          <tbody>
            {pointages.slice(0, 50).map((p) => (
              <tr key={p.id}>
                <td>{p.code}</td>
                <td>{p.ordre_code}</td>
                <td>{p.worker_name_filled ?? "—"}</td>
                <td>{formatDate(p.date)}</td>
                <td>
                  {formatNumber(Number(p.hours))} h <span className="muted">{p.hours_type_label}</span>
                </td>
                <td>{p.nature_mo_label}</td>
                <td>
                  <Badge tone={p.status === "saisi" ? "warn" : "ok"}>{p.status_label}</Badge>
                  {p.status === "saisi" && <ActionBar actions={[{ label: k("pointages.valider"), path: `/api/operations/pointages/${p.id}/valider/` }]} />}
                  {p.status === "valide" && <ActionBar actions={[{ label: k("pointages.transferer"), path: `/api/operations/pointages/${p.id}/transferer-paie/` }]} />}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted">{k("pointages.note")}</p>
      </SectionCard>

      <SectionCard title={k("suivi.title")}>
        {ind && (
          <div className="kpi-grid">
            <Kpi label={k("suivi.productivite")} value={pct(ind.productivite_pct)} tone="brand" delay={0} />
            <Kpi label={k("suivi.rebut")} value={pct(ind.taux_rebut_pct)} tone="accent" delay={0.03} />
            <Kpi label={k("suivi.directe")} value={`${formatNumber(Number(ind.heures_directes))} h`} hint={`${formatNumber(Number(ind.heures_indirectes))} h ${k("suivi.indirecte")}`} tone="brand" delay={0.06} />
            <Kpi label={k("suivi.retards")} value={ind.of_en_retard} hint={`${ind.ruptures_ouvertes} ${k("suivi.ruptures")}`} tone="accent" delay={0.09} />
          </div>
        )}
        <div className="action-bar-buttons">
          <ActionBar actions={[{ label: k("suivi.publier"), path: "/api/operations/ordres/publier-marges/", confirm: k("suivi.publierQ") }]} />
          <Pdf path="/api/operations/ordres/rapport-periodique/?periode=hebdo&export=pdf" name="rapport-hebdo.pdf" label={k("suivi.hebdoPdf")} />
          <Pdf path="/api/operations/ordres/rapport-periodique/?periode=mensuel&export=pdf" name="rapport-mensuel.pdf" label={k("suivi.mensuelPdf")} />
          <Pdf path="/api/operations/ordres/rapport-periodique/?periode=mensuel&export=xlsx" name="rapport-mensuel.xlsx" label={k("suivi.mensuelXlsx")} />
        </div>
        <table className="table" data-testid="m3-marges">
          <thead>
            <tr>
              <th>{k("affaire")}</th>
              <th>{k("suivi.avancement")}</th>
              <th>{k("suivi.ca")}</th>
              <th>{k("suivi.engage")}</th>
              <th>{k("suivi.cat")}</th>
              <th>{k("suivi.marge")}</th>
            </tr>
          </thead>
          <tbody>
            {(suivi?.affaires ?? []).map((a) => (
              <tr key={a.affaire}>
                <td>
                  {a.affaire_code} · {a.affaire_label}
                </td>
                <td>{pct(a.avancement_pct)}</td>
                <td>{fcfa(a.chiffre_affaires)}</td>
                <td>{fcfa(a.couts_engages)}</td>
                <td>{fcfa(a.cout_a_terminaison)}</td>
                <td>
                  {fcfa(a.marge_a_terminaison)} {a.marge_pct !== null && <span className="muted">({pct(a.marge_pct)})</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted">{t("ecarts_m3.suivi.note", { m: suivi?.methode ?? 1 })}</p>
        <table className="table" data-testid="m3-of-impressions">
          <thead>
            <tr>
              <th>{k("of")}</th>
              <th>{k("statut")}</th>
              <th>{k("suivi.avancement")}</th>
              <th>{k("suivi.periode")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {ordres.slice(0, 50).map((o) => {
              const s = suivi?.ordres.find((x) => x.ordre === o.id);
              const actif = o.status === "prevu" || o.status === "lance" || o.status === "en_cours";
              return (
                <tr key={o.id}>
                  <td>
                    {o.code} · {o.label}
                  </td>
                  <td>{o.status_label}</td>
                  <td>{pct(s?.avancement_pct ?? null)}</td>
                  <td>
                    {o.planned_start ? formatDate(o.planned_start) : "—"} → {o.planned_end ? formatDate(o.planned_end) : "—"}
                    {o.motif_replanification ? <span className="muted"> · {o.motif_replanification}</span> : null}
                  </td>
                  <td>
                    {actif && (
                      <ActionBar
                        actions={[
                          { label: k("suivi.verifier"), path: `/api/operations/ordres/${o.id}/verifier-besoins/`, tone: "ghost" as const },
                          {
                            label: k("suivi.replanifier"), path: `/api/operations/ordres/${o.id}/replanifier/`, tone: "ghost" as const,
                            body: { motif: k("suivi.motifReplan") }, prompt: { name: "decalage_jours", label: k("suivi.decalage") },
                          },
                        ]}
                      />
                    )}
                    <Pdf path={`/api/operations/ordres/${o.id}/?export=pdf`} name={`${o.code}.pdf`} label={k("pdf")} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </SectionCard>

      <SectionCard title={k("charge.title")}>
        <ActionBar actions={[{ label: k("charge.escalader"), path: "/api/operations/ordres/escalader-surcharges/", confirm: k("charge.escaladerQ") }]} />
        <table className="table" data-testid="m3-charge-jour">
          <thead>
            <tr>
              <th>{k("date")}</th>
              <th>{k("charge.perimetre")}</th>
              <th>{k("charge.ressource")}</th>
              <th>{k("charge.planifie")}</th>
              <th>{k("charge.capacite")}</th>
            </tr>
          </thead>
          <tbody>
            {lignesSurcharge.map((l) => (
              <tr key={`${l.date}-${l.scope}-${l.resource}`}>
                <td>{formatDate(l.date)}</td>
                <td>{l.scope}</td>
                <td>{k(`charge.${l.resource}`)}</td>
                <td>
                  {formatNumber(Number(l.planned_hours))} h {l.overload && <Badge tone="err">{k("charge.surcharge")}</Badge>}
                </td>
                <td>{l.capacity === null ? "—" : `${formatNumber(Number(l.capacity))} h`}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {escalades.length > 0 && (
          <ul data-testid="m3-escalades">
            {escalades.map((e) => (
              <li key={e.id}>
                <Badge tone="warn">{k("charge.escalade")}</Badge> {e.scope} · {k(`charge.${e.resource}`)} · {formatDate(e.semaine)} : +{formatNumber(Number(e.surcharge_pct))} %
              </li>
            ))}
          </ul>
        )}
        <p className="muted">{k("charge.note")}</p>
      </SectionCard>

      <SectionCard title={k("registre.title")}>
        <table className="table" data-testid="m3-registre">
          <thead>
            <tr>
              <th>{k("registre.document")}</th>
              <th>{k("registre.type")}</th>
              <th>{k("registre.objet")}</th>
              <th>{k("date")}</th>
            </tr>
          </thead>
          <tbody>
            {registre.map((d) => (
              <tr key={d.id}>
                <td>
                  {d.titre} <span className="muted">{d.reference}</span>
                </td>
                <td>{d.type ?? "—"}</td>
                <td>{d.objet}</td>
                <td>{formatDate(d.lie_le)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <table className="table" data-testid="m3-dossiers">
          <thead>
            <tr>
              <th>{k("registre.dossier")}</th>
              <th>{k("registre.empreinte")}</th>
              <th>{k("registre.conservation")}</th>
              <th>{k("date")}</th>
            </tr>
          </thead>
          <tbody>
            {dossiers.map((d) => (
              <tr key={d.id}>
                <td>{d.ordre_code}</td>
                <td className="muted">{d.sha256.slice(0, 16)}…</td>
                <td>{t("ecarts_m3.registre.ans", { n: d.retention_years })}</td>
                <td>{formatDate(d.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </SectionCard>
    </>
  );
}
