import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate, formatMoney, formatNumber } from "../../lib/format";
import "./comptabilite.css";
import { describeError } from "../../lib/offlineQueue";
import { SectionActions } from "../sections/SectionActions";
import { ActionBar, Badge, DataTable, DatePicker, QuickForm, SectionCard } from "../ui";
import type { Column } from "../ui";
import { actionsColumn } from "../ui/DataTable";

interface Colonne {
  key: string;
  label: string;
  montant: boolean;
}
type Cellule = string | number | boolean | null | undefined;
interface Tableau {
  titre: string;
  colonnes: Colonne[];
  lignes: Record<string, Cellule>[];
}
interface Etat {
  titre: string;
  sous_titre?: string;
  provisoire: boolean;
  avertissement?: string;
  equilibre?: boolean;
  tableaux: Tableau[];
}
interface Semaine {
  semaine: string;
  numero: number;
  prevu_encaissements: string;
  prevu_decaissements: string;
  realise_encaissements: string | null;
  realise_decaissements: string | null;
  solde_fin_prevu: string;
  solde_fin_reel: string | null;
  alerte: boolean;
}
interface PlanTresorerie {
  semaines: number;
  seuil: string;
  solde_initial: string;
  alertes: string[];
  provisoire: boolean;
  rows: Semaine[];
}
interface AutoFacture {
  id: string;
  code: string;
  fournisseur_name: string;
  date: string;
  objet: string;
  montant_ht: string | null;
  montant_tva: string | null;
  compte_charge_code: string;
  statut: "brouillon" | "emise";
  move_number: string | null;
}
interface LocationsGr {
  a_comptabiliser: { id: string; code: string; equipement: string; affaire: string | null; date_retour: string | null; montant: string | null }[];
  ecritures: { numero: string; date: string; location: string; libelle: string; montant: string | null }[];
}
interface Gabarit {
  id: number;
  code: string;
  label: string;
  parametres: Record<string, unknown>;
  est_provisoire: boolean;
}
interface Ref {
  id: string | number;
  code: string;
  name?: string;
  label?: string;
  account_class?: number;
}

const ETATS = [
  "balance",
  "grand-livre",
  "bilan",
  "compte-resultat",
  "balance-agee-clients",
  "balance-agee-fournisseurs",
  "liasse",
  "etat-2460",
  "plan-comptable",
  "conservation",
] as const;
type EtatCode = (typeof ETATS)[number];

const fcfa = (v: string | null | undefined) => formatMoney(v);

function urlEtat(code: EtatCode, p: { from: string; to: string; exercice: string; compte: string }) {
  const q = new URLSearchParams();
  if (code.startsWith("balance-agee")) {
    q.set("nature", code.endsWith("clients") ? "clients" : "fournisseurs");
    if (p.to) q.set("date_to", p.to);
    return `/api/comptabilite/etats/balance-agee/?${q}`;
  }
  if (code === "liasse" || code === "etat-2460") q.set("exercice", p.exercice);
  if (p.from && code !== "bilan") q.set("date_from", p.from);
  if (p.to) q.set("date_to", p.to);
  if (code === "grand-livre" && p.compte) q.set("compte", p.compte);
  return `/api/comptabilite/etats/${code}/?${q}`;
}

type LigneEtat = Record<string, Cellule> & { id: number };
type LigneGr =
  | { id: string; kind: "a"; ref: string; code: string; equipement: string; affaire: string | null; date: string | null; montant: string | null }
  | { id: string; kind: "e"; numero: string; location: string; libelle: string; date: string; montant: string | null };

/** Paramètres d'un gabarit lisibles : la note en clair, puis « Seuil : 0 · Comptes : 632, 622 » (jamais de JSON brut). */
function parametresLisibles(p: Record<string, unknown>, t: (k: string, o?: Record<string, unknown>) => string) {
  const valeur = (v: unknown): string =>
    Array.isArray(v) ? v.map(valeur).join(", ") : v !== null && typeof v === "object" ? Object.values(v as object).map(valeur).join(", ") : String(v ?? "—").replace(/_/g, " ");
  const autres = Object.entries(p)
    .filter(([k]) => k !== "note")
    .map(([k, v]) => `${t(`revueR3.gabarit.${k}`, { defaultValue: k.charAt(0).toUpperCase() + k.slice(1).replace(/_/g, " ") })} : ${valeur(v)}`);
  return (
    <>
      {typeof p.note === "string" ? p.note : null}
      {autres.length > 0 ? <span className="cell-sub">{autres.join(" · ")}</span> : null}
    </>
  );
}

/** Cellule d'état : montants complets (unité FCFA rappelée une fois sous le titre, B02), lignes de total en gras. */
function cellule(col: Colonne, l: LigneEtat) {
  const v = l[col.key];
  const total = Boolean(l.total || l.total_ligne || l.entete);
  // Montant nul laissé en blanc (usage des balances) : seuls les mouvements ressortent ; les totaux restent affichés.
  const vide = v === null || v === undefined || v === "" || (col.montant && Number(v) === 0 && !total);
  const texte = vide ? "" : col.montant ? formatNumber(Number(v)) : String(v);
  return l.total || l.total_ligne || l.entete ? <strong>{texte}</strong> : texte;
}

/** Écarts M10 : états SYSCOHADA exportables, trésorerie 13 semaines, autofacturation, 618 GR, gabarits fiscaux. */
export function EcartsM10Section() {
  const { t } = useTranslation();
  const annee = String(new Date().getFullYear());
  const [code, setCode] = useState<EtatCode>("balance");
  const [from, setFrom] = useState(`${annee}-01-01`);
  const [to, setTo] = useState("");
  const [exercice, setExercice] = useState(annee);
  const [compte, setCompte] = useState("");
  const [exportError, setExportError] = useState<string | null>(null);
  const url = urlEtat(code, { from, to, exercice, compte });
  const etat = useQuery({ queryKey: ["m10", "etat", url], queryFn: () => api.get<Etat>(url), retry: 0 });
  const treso = useQuery({ queryKey: ["m10", "tresorerie"], queryFn: () => api.get<PlanTresorerie>("/api/comptabilite/etats/tresorerie/"), retry: 0 });
  const autof = useQuery({ queryKey: ["m10", "autofactures"], queryFn: () => api.listAll<AutoFacture>("/api/comptabilite/autofactures/"), retry: 0 });
  const gr = useQuery({ queryKey: ["m10", "locations-gr"], queryFn: () => api.get<LocationsGr>("/api/comptabilite/locations-gr/"), retry: 0 });
  const fournisseurs = useQuery({ queryKey: ["m10", "partners"], queryFn: () => api.listAll<Ref>("/api/referentiels/partners/"), retry: 0 }).data ?? [];
  const comptes = useQuery({ queryKey: ["m10", "accounts"], queryFn: () => api.listAll<Ref>("/api/referentiels/accounts/"), retry: 0 }).data ?? [];
  const taux = useQuery({ queryKey: ["m10", "taux"], queryFn: () => api.listAll<Ref & { taux: string }>("/api/comptabilite/taux-tva/"), retry: 0 }).data ?? [];

  const exporter = (fmt: "xlsx" | "pdf") => {
    setExportError(null);
    api.download(`${url}&export=${fmt}`, `${code}.${fmt}`).catch((e) => setExportError(describeError(e)));
  };
  const provisoire = (
    <Badge tone="warn" title={t("ecarts_m10.provisoire")}>
      {t("revueR3.provisoire")}
    </Badge>
  );

  const colsTreso: Column<Semaine & { id: string }>[] = [
    { key: "semaine", header: t("ecarts_m10.treso.semaine"), render: (r) => `S${r.numero} · ${formatDate(r.semaine)}`, sortValue: (r) => r.numero },
    { key: "prevuEnc", header: t("ecarts_m10.treso.prevuEnc"), num: true, render: (r) => (Number(r.prevu_encaissements) ? fcfa(r.prevu_encaissements) : "—") },
    { key: "prevuDec", header: t("ecarts_m10.treso.prevuDec"), num: true, render: (r) => (Number(r.prevu_decaissements) ? fcfa(r.prevu_decaissements) : "—") },
    { key: "reelEnc", header: t("ecarts_m10.treso.reelEnc"), num: true, render: (r) => fcfa(r.realise_encaissements) },
    { key: "reelDec", header: t("ecarts_m10.treso.reelDec"), num: true, render: (r) => fcfa(r.realise_decaissements) },
    {
      key: "soldePrevu",
      header: t("ecarts_m10.treso.soldePrevu"),
      num: true,
      render: (r) => (
        <>
          {fcfa(r.solde_fin_prevu)} {r.alerte && <Badge tone="err">{t("tableaux.comptabilite.sousSeuil")}</Badge>}
        </>
      ),
    },
    { key: "soldeReel", header: t("ecarts_m10.treso.soldeReel"), num: true, render: (r) => fcfa(r.solde_fin_reel) },
  ];

  const colsAutof: Column<AutoFacture>[] = [
    { key: "code", header: t("ecarts_m10.autof.code"), render: (a) => a.code, sortValue: (a) => a.code },
    { key: "fournisseur", header: t("ecarts_m10.autof.fournisseur"), render: (a) => a.fournisseur_name, sortValue: (a) => a.fournisseur_name },
    {
      key: "objet",
      header: t("ecarts_m10.autof.objet"),
      render: (a) => (
        <>
          {a.objet} <span className="muted">· {a.compte_charge_code}</span>
        </>
      ),
    },
    { key: "ht", header: t("ecarts_m10.autof.ht"), num: true, render: (a) => fcfa(a.montant_ht), sortValue: (a) => Number(a.montant_ht ?? 0) },
    { key: "tva", header: t("ecarts_m10.autof.tva"), num: true, render: (a) => fcfa(a.montant_tva) },
    {
      key: "ecriture",
      header: t("ecarts_m10.autof.ecriture"),
      render: (a) => (
        <>
          {a.move_number ?? "—"}
          {a.statut === "brouillon" && (
            <ActionBar actions={[{ label: t("ecarts_m10.autof.emettre"), path: `/api/comptabilite/autofactures/${a.id}/emettre/`, confirm: t("ecarts_m10.autof.confirmEmettre") }]} />
          )}
        </>
      ),
    },
  ];

  const lignesGr: LigneGr[] = [
    ...(gr.data?.a_comptabiliser ?? []).map(
      (l): LigneGr => ({ id: `a-${l.id}`, kind: "a", ref: l.id, code: l.code, equipement: l.equipement, affaire: l.affaire, date: l.date_retour, montant: l.montant }),
    ),
    ...(gr.data?.ecritures ?? []).map(
      (x): LigneGr => ({ id: `e-${x.numero}`, kind: "e", numero: x.numero, location: x.location, libelle: x.libelle, date: x.date, montant: x.montant }),
    ),
  ];
  const colsGr: Column<LigneGr>[] = [
    { key: "location", header: t("ecarts_m10.gr.location"), render: (l) => (l.kind === "a" ? l.code : l.location) },
    { key: "equipement", header: t("ecarts_m10.gr.equipement"), render: (l) => (l.kind === "a" ? l.equipement : l.libelle) },
    { key: "affaire", header: t("ecarts_m10.gr.affaire"), render: (l) => (l.kind === "a" ? (l.affaire ?? "—") : "—") },
    { key: "retour", header: t("ecarts_m10.gr.retour"), render: (l) => formatDate(l.date) },
    { key: "montant", header: t("ecarts_m10.gr.montant"), num: true, render: (l) => fcfa(l.montant) },
    {
      key: "ecriture",
      header: t("ecarts_m10.autof.ecriture"),
      render: (l) => (l.kind === "e" ? <Badge tone="ok">{l.numero}</Badge> : "—"),
    },
    actionsColumn<LigneGr>(t("ui.actions"), (l) =>
      l.kind === "a"
        ? [{ label: t("ecarts_m10.gr.comptabiliser"), path: `/api/comptabilite/locations-gr/${l.ref}/comptabiliser/`, confirm: t("ecarts_m10.gr.confirm"), tone: "ghost" }]
        : [],
    ),
  ];


  return (
    <>
      <SectionCard title={t("ecarts_m10.etats.title")} subtitle={t("ecarts_m10.etats.subtitle")}>
        <div className="r3-toolbar">
          <label className="field">
            <span>{t("ecarts_m10.etats.etat")}</span>
            <select value={code} onChange={(e) => setCode(e.target.value as EtatCode)} aria-label={t("ecarts_m10.etats.etat")}>
              {ETATS.map((c) => (
                <option key={c} value={c}>
                  {t(`ecarts_m10.etats.codes.${c}`)}
                </option>
              ))}
            </select>
          </label>
          {code === "liasse" || code === "etat-2460" ? (
            <label className="field">
              <span>{t("ecarts_m10.etats.exercice")}</span>
              <input type="number" value={exercice} onChange={(e) => setExercice(e.target.value)} />
            </label>
          ) : (
            <>
              <div className="field">
                <label htmlFor="m10-du">{t("ecarts_m10.etats.du")}</label>
                <DatePicker id="m10-du" value={from} onChange={setFrom} />
              </div>
              <div className="field">
                <label htmlFor="m10-au">{t("ecarts_m10.etats.au")}</label>
                <DatePicker id="m10-au" value={to} onChange={setTo} />
              </div>
            </>
          )}
          {code === "grand-livre" && (
            <label className="field">
              <span>{t("ecarts_m10.etats.compte")}</span>
              <input value={compte} inputMode="numeric" onChange={(e) => setCompte(e.target.value.replace(/\D/g, ""))} />
            </label>
          )}
          <button type="button" className="btn" onClick={() => exporter("xlsx")}>
            {t("ecarts_m10.etats.xlsx")}
          </button>
          <button type="button" className="btn" onClick={() => exporter("pdf")}>
            {t("ecarts_m10.etats.pdf")}
          </button>
          {code === "liasse" && (
            <ActionBar actions={[{ label: t("ecarts_m10.etats.archiver"), path: "/api/comptabilite/etats/archiver-liasse/", body: { exercice }, confirm: t("ecarts_m10.etats.confirmArchiver") }]} />
          )}
        </div>
        {exportError && <p className="error">{exportError}</p>}
        {etat.isError && <p className="muted">{describeError(etat.error)}</p>}
        {etat.data && (
          <>
            <p className="muted">
              {etat.data.sous_titre}{" "}
              {etat.data.equilibre === false && <Badge tone="err">{t("ecarts_m10.etats.desequilibre")}</Badge>}
              {etat.data.provisoire && provisoire}
            </p>
            {etat.data.provisoire && etat.data.avertissement && <p className="muted">{etat.data.avertissement}</p>}
            {etat.data.tableaux.map((tab) => (
              <div className="etat-bloc" key={tab.titre} data-testid={`etat-${code}`}>
                <h4>{tab.titre}</h4>
                {tab.colonnes.some((c) => c.montant) && <p className="muted etat-unite">{t("vague3C2.compta.montantsFcfa")}</p>}
                <DataTable
                  caption={tab.titre}
                  density="compact"
                  columns={tab.colonnes.map<Column<LigneEtat>>((c) => ({
                    key: c.key,
                    header: t(`ecarts_m10.col.${c.key}`, { defaultValue: c.label }),
                    num: c.montant,
                    width: c.key === "libelle" ? 200 : undefined,
                    render: (l) => cellule(c, l),
                  }))}
                  rows={tab.lignes.map((l, i) => ({ ...l, id: i }))}
                />
              </div>
            ))}
          </>
        )}
      </SectionCard>

      <SectionCard
        title={t("ecarts_m10.treso.title")}
        subtitle={t("ecarts_m10.treso.subtitle")}
        actions={
          <SectionActions>
          <QuickForm
            title={t("ecarts_m10.treso.ajouter")}
            endpoint="/api/comptabilite/previsions-tresorerie/"
            fields={[
              { name: "date_prevue", label: t("ecarts_m10.treso.date"), type: "date", required: true },
              { name: "sens", label: t("ecarts_m10.treso.sens"), type: "select", required: true, options: ["entree", "sortie"].map((v) => ({ value: v, label: t(`ecarts_m10.treso.sens_${v}`) })) },
              {
                name: "categorie",
                label: t("ecarts_m10.treso.categorie"),
                type: "select",
                options: ["clients", "fournisseurs", "salaires", "fiscal", "financement", "intragroupe", "autre"].map((v) => ({ value: v, label: t(`ecarts_m10.treso.cat.${v}`) })),
              },
              { name: "libelle", label: t("ecarts_m10.treso.libelle"), required: true },
              { name: "montant", label: t("ecarts_m10.treso.montant"), type: "number", min: 0, required: true },
            ]}
          />
          </SectionActions>
        }
      >
        {treso.data && (
          <>
            <p className="muted">
              {t("ecarts_m10.treso.resume", { n: treso.data.semaines, solde: fcfa(treso.data.solde_initial), seuil: fcfa(treso.data.seuil) })}{" "}
              {treso.data.alertes.length > 0 ? <Badge tone="err">{t("ecarts_m10.treso.alerte", { n: treso.data.alertes.length })}</Badge> : <Badge tone="ok">{t("ecarts_m10.treso.ok")}</Badge>}{" "}
              {treso.data.provisoire && provisoire}
            </p>
            <div data-testid="tresorerie-13">
              <DataTable
                caption={t("ecarts_m10.treso.title")}
                density="compact"
                columns={colsTreso}
                rows={treso.data.rows.map((r) => ({ ...r, id: r.semaine }))}
              />
            </div>
          </>
        )}
      </SectionCard>

      <SectionCard
        title={t("ecarts_m10.autof.title")}
        subtitle={t("ecarts_m10.autof.subtitle")}
        actions={
          <SectionActions>
          <QuickForm
            title={t("ecarts_m10.autof.ajouter")}
            endpoint="/api/comptabilite/autofactures/"
            fields={[
              { name: "fournisseur", label: t("ecarts_m10.autof.fournisseur"), type: "select", required: true, options: fournisseurs.map((p) => ({ value: String(p.id), label: `${p.code} · ${p.name ?? ""}` })) },
              { name: "date", label: t("ecarts_m10.autof.date"), type: "date", required: true },
              { name: "objet", label: t("ecarts_m10.autof.objet"), required: true },
              { name: "montant_ht", label: t("ecarts_m10.autof.ht"), type: "number", min: 0, required: true },
              { name: "taux_tva", label: t("ecarts_m10.autof.taux"), type: "select", required: true, options: taux.map((x) => ({ value: String(x.id), label: `${x.code} · ${x.taux} %` })) },
              {
                name: "compte_charge",
                label: t("ecarts_m10.autof.compte"),
                type: "select",
                required: true,
                options: comptes.filter((c) => c.account_class === 6 || c.account_class === 2).map((c) => ({ value: String(c.id), label: `${c.code} · ${c.label ?? ""}` })),
              },
            ]}
          />
          </SectionActions>
        }
      >
        <div data-testid="autofactures">
          <DataTable caption={t("ecarts_m10.autof.title")} columns={colsAutof} rows={autof.data ?? []} emptyLabel={t("tableaux.comptabilite.aucuneAutofacture")} />
        </div>
        <p className="muted">{t("ecarts_m10.autof.note")}</p>
      </SectionCard>

      <SectionCard title={t("ecarts_m10.gr.title")} subtitle={t("ecarts_m10.gr.subtitle")}>
        <div data-testid="locations-gr-618">
          <DataTable caption={t("ecarts_m10.gr.title")} columns={colsGr} rows={lignesGr} emptyLabel={t("tableaux.comptabilite.aucuneLocation")} />
        </div>
      </SectionCard>
    </>
  );
}

/** Gabarits d'états fiscaux (paramétrage, B11) : rendus dans « Paramètres du module » de la Comptabilité. */
export function GabaritsEtatsSection() {
  const { t } = useTranslation();
  const gabarits = useQuery({ queryKey: ["m10", "gabarits"], queryFn: () => api.listAll<Gabarit>("/api/comptabilite/gabarits/"), retry: 0 });
  const provisoire = (
    <Badge tone="warn" title={t("ecarts_m10.provisoire")}>
      {t("revueR3.provisoire")}
    </Badge>
  );
  const colsGabarits: Column<Gabarit>[] = [
    {
      key: "gabarit",
      header: t("ecarts_m10.gabarits.gabarit"),
      render: (g) => g.label,
      width: 260,
    },
    { key: "parametres", header: t("ecarts_m10.gabarits.parametres"), render: (g) => parametresLisibles(g.parametres, t) },
    {
      key: "statut",
      header: t("revueR3.statut"),
      render: (g) => (g.est_provisoire ? provisoire : <Badge tone="ok">{t("ecarts_m10.confirme")}</Badge>),
    },
    actionsColumn<Gabarit>(t("ui.actions"), (g) => [
      ...(g.est_provisoire ? [{ label: t("ecarts_m10.gabarits.confirmer"), path: `/api/comptabilite/gabarits/${g.id}/confirmer/`, tone: "ghost" as const }] : []),
      { label: t("ecarts_m10.gabarits.modifier"), path: `/api/comptabilite/gabarits/${g.id}/modifier/`, tone: "ghost", prompt: { name: "parametres", label: t("ecarts_m10.gabarits.prompt") } },
    ]),
  ];

  return (
    <SectionCard title={t("ecarts_m10.gabarits.title")} subtitle={t("ecarts_m10.gabarits.subtitle")}>
      <div data-testid="gabarits-etats">
        <DataTable caption={t("ecarts_m10.gabarits.title")} columns={colsGabarits} rows={gabarits.data ?? []} />
      </div>
      <p className="muted">{t("ecarts_m10.gabarits.note")}</p>
    </SectionCard>
  );
}
