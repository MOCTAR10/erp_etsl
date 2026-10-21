import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatNumber } from "../../lib/format";
import { describeError } from "../../lib/offlineQueue";
import { ActionBar, Badge, QuickForm, SectionCard } from "../ui";

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

const fcfa = (v: string | null | undefined) => (v === null || v === undefined || v === "" ? "—" : `${formatNumber(Number(v))} F`);

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

function Cell({ col, v }: { col: Colonne; v: Cellule }) {
  if (col.montant) return <td className="num">{v === null || v === undefined || v === "" ? "" : formatNumber(Number(v))}</td>;
  return <td>{v === null || v === undefined ? "" : String(v)}</td>;
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
  const gabarits = useQuery({ queryKey: ["m10", "gabarits"], queryFn: () => api.listAll<Gabarit>("/api/comptabilite/gabarits/"), retry: 0 });
  const fournisseurs = useQuery({ queryKey: ["m10", "partners"], queryFn: () => api.listAll<Ref>("/api/referentiels/partners/"), retry: 0 }).data ?? [];
  const comptes = useQuery({ queryKey: ["m10", "accounts"], queryFn: () => api.listAll<Ref>("/api/referentiels/accounts/"), retry: 0 }).data ?? [];
  const taux = useQuery({ queryKey: ["m10", "taux"], queryFn: () => api.listAll<Ref & { taux: string }>("/api/comptabilite/taux-tva/"), retry: 0 }).data ?? [];

  const exporter = (fmt: "xlsx" | "pdf") => {
    setExportError(null);
    api.download(`${url}&export=${fmt}`, `${code}.${fmt}`).catch((e) => setExportError(describeError(e)));
  };
  const provisoire = <Badge tone="warn">{t("ecarts_m10.provisoire")}</Badge>;

  return (
    <>
      <SectionCard title={t("ecarts_m10.etats.title")} subtitle={t("ecarts_m10.etats.subtitle")}>
        <div className="action-bar-buttons">
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
              <label className="field">
                <span>{t("ecarts_m10.etats.du")}</span>
                <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
              </label>
              <label className="field">
                <span>{t("ecarts_m10.etats.au")}</span>
                <input type="date" value={to} onChange={(e) => setTo(e.target.value)} />
              </label>
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
              <div className="table-wrap" key={tab.titre} tabIndex={0} role="region" aria-label={tab.titre}>
                <h4>{tab.titre}</h4>
                <table className="table" data-testid={`etat-${code}`}>
                  <thead>
                    <tr>
                      {tab.colonnes.map((c) => (
                        <th key={c.key}>{t(`ecarts_m10.col.${c.key}`, { defaultValue: c.label })}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {tab.lignes.map((l, i) => (
                      <tr key={i} style={l.total || l.total_ligne || l.entete ? { fontWeight: 600 } : undefined}>
                        {tab.colonnes.map((c) => (
                          <Cell key={c.key} col={c} v={l[c.key]} />
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </>
        )}
      </SectionCard>

      <SectionCard title={t("ecarts_m10.treso.title")} subtitle={t("ecarts_m10.treso.subtitle")}>
        <div className="action-bar-buttons">
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
        </div>
        {treso.data && (
          <>
            <p className="muted">
              {t("ecarts_m10.treso.resume", { n: treso.data.semaines, solde: fcfa(treso.data.solde_initial), seuil: fcfa(treso.data.seuil) })}{" "}
              {treso.data.alertes.length > 0 ? <Badge tone="err">{t("ecarts_m10.treso.alerte", { n: treso.data.alertes.length })}</Badge> : <Badge tone="ok">{t("ecarts_m10.treso.ok")}</Badge>}{" "}
              {treso.data.provisoire && provisoire}
            </p>
            <div className="table-wrap" tabIndex={0} role="region" aria-label={t("ecarts_m10.treso.title")}>
              <table className="table" data-testid="tresorerie-13">
                <thead>
                  <tr>
                    <th>{t("ecarts_m10.treso.semaine")}</th>
                    <th>{t("ecarts_m10.treso.prevuEnc")}</th>
                    <th>{t("ecarts_m10.treso.prevuDec")}</th>
                    <th>{t("ecarts_m10.treso.reelEnc")}</th>
                    <th>{t("ecarts_m10.treso.reelDec")}</th>
                    <th>{t("ecarts_m10.treso.soldePrevu")}</th>
                    <th>{t("ecarts_m10.treso.soldeReel")}</th>
                  </tr>
                </thead>
                <tbody>
                  {treso.data.rows.map((r) => (
                    <tr key={r.semaine}>
                      <td>
                        S{r.numero} · {r.semaine}
                      </td>
                      <td className="num">{fcfa(r.prevu_encaissements)}</td>
                      <td className="num">{fcfa(r.prevu_decaissements)}</td>
                      <td className="num">{fcfa(r.realise_encaissements)}</td>
                      <td className="num">{fcfa(r.realise_decaissements)}</td>
                      <td className="num">
                        {fcfa(r.solde_fin_prevu)} {r.alerte && <Badge tone="err">!</Badge>}
                      </td>
                      <td className="num">{fcfa(r.solde_fin_reel)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </SectionCard>

      <SectionCard title={t("ecarts_m10.autof.title")} subtitle={t("ecarts_m10.autof.subtitle")}>
        <div className="action-bar-buttons">
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
        </div>
        <table className="table" data-testid="autofactures">
          <thead>
            <tr>
              <th>{t("ecarts_m10.autof.code")}</th>
              <th>{t("ecarts_m10.autof.fournisseur")}</th>
              <th>{t("ecarts_m10.autof.objet")}</th>
              <th>{t("ecarts_m10.autof.ht")}</th>
              <th>{t("ecarts_m10.autof.tva")}</th>
              <th>{t("ecarts_m10.autof.ecriture")}</th>
            </tr>
          </thead>
          <tbody>
            {(autof.data ?? []).map((a) => (
              <tr key={a.id}>
                <td>{a.code}</td>
                <td>{a.fournisseur_name}</td>
                <td>
                  {a.objet} <span className="muted">· {a.compte_charge_code}</span>
                </td>
                <td className="num">{fcfa(a.montant_ht)}</td>
                <td className="num">{fcfa(a.montant_tva)}</td>
                <td>
                  {a.move_number ?? "—"}
                  {a.statut === "brouillon" && (
                    <ActionBar actions={[{ label: t("ecarts_m10.autof.emettre"), path: `/api/comptabilite/autofactures/${a.id}/emettre/`, confirm: t("ecarts_m10.autof.confirmEmettre") }]} />
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted">{t("ecarts_m10.autof.note")}</p>
      </SectionCard>

      <SectionCard title={t("ecarts_m10.gr.title")} subtitle={t("ecarts_m10.gr.subtitle")}>
        <table className="table" data-testid="locations-gr-618">
          <thead>
            <tr>
              <th>{t("ecarts_m10.gr.location")}</th>
              <th>{t("ecarts_m10.gr.equipement")}</th>
              <th>{t("ecarts_m10.gr.affaire")}</th>
              <th>{t("ecarts_m10.gr.retour")}</th>
              <th>{t("ecarts_m10.gr.montant")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {(gr.data?.a_comptabiliser ?? []).map((l) => (
              <tr key={l.id}>
                <td>{l.code}</td>
                <td>{l.equipement}</td>
                <td>{l.affaire ?? "—"}</td>
                <td>{l.date_retour ?? "—"}</td>
                <td className="num">{fcfa(l.montant)}</td>
                <td>
                  <ActionBar actions={[{ label: t("ecarts_m10.gr.comptabiliser"), path: `/api/comptabilite/locations-gr/${l.id}/comptabiliser/`, confirm: t("ecarts_m10.gr.confirm") }]} />
                </td>
              </tr>
            ))}
            {(gr.data?.ecritures ?? []).map((e) => (
              <tr key={e.numero}>
                <td>{e.location}</td>
                <td colSpan={2}>{e.libelle}</td>
                <td>{e.date}</td>
                <td className="num">{fcfa(e.montant)}</td>
                <td>
                  <Badge tone="ok">{e.numero}</Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </SectionCard>

      <SectionCard title={t("ecarts_m10.gabarits.title")} subtitle={t("ecarts_m10.gabarits.subtitle")}>
        <table className="table" data-testid="gabarits-etats">
          <thead>
            <tr>
              <th>{t("ecarts_m10.gabarits.gabarit")}</th>
              <th>{t("ecarts_m10.gabarits.parametres")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {(gabarits.data ?? []).map((g) => (
              <tr key={g.id}>
                <td>
                  {g.label} {g.est_provisoire ? provisoire : <Badge tone="ok">{t("ecarts_m10.confirme")}</Badge>}
                </td>
                <td>
                  <code>{JSON.stringify(g.parametres)}</code>
                </td>
                <td>
                  <ActionBar
                    actions={[
                      { label: t("ecarts_m10.gabarits.modifier"), path: `/api/comptabilite/gabarits/${g.id}/modifier/`, tone: "ghost", prompt: { name: "parametres", label: t("ecarts_m10.gabarits.prompt") } },
                      ...(g.est_provisoire ? [{ label: t("ecarts_m10.gabarits.confirmer"), path: `/api/comptabilite/gabarits/${g.id}/confirmer/` }] : []),
                    ]}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted">{t("ecarts_m10.gabarits.note")}</p>
      </SectionCard>
    </>
  );
}
