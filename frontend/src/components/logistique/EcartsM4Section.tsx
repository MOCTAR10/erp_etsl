import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate, formatMoney, formatNumber } from "../../lib/format";
import { describeError } from "../../lib/offlineQueue";
import { ActionBar, Badge, QuickForm, SectionCard } from "../ui";

interface Equipement {
  id: string;
  code: string;
  label: string;
  compteur_type_label: string;
  compteur_value: string;
  plafond_compteur: string | null;
  plafond_pct: string | null;
}
interface Releve {
  id: string;
  equipement_code: string;
  date: string;
  valeur: string;
  source_label: string;
  saisi_par_name: string | null;
}
interface Historique {
  id: string;
  equipement_code: string;
  champ: string;
  ancienne_valeur: string;
  nouvelle_valeur: string;
  modifie_par_name: string | null;
  modifie_le: string;
}
interface Audit {
  id: string;
  code: string;
  equipement_code: string;
  date_audit: string;
  etat_label: string;
  photo: string | null;
  photo_sha256: string;
  conserver_jusqu_au: string;
  auditeur_name: string | null;
}
interface Location {
  id: string;
  code: string;
  equipement_code: string;
  partenaire_name: string | null;
  statut: string;
  statut_label: string;
  emis_le: string | null;
  validations: { m2: boolean; dr: boolean; m2_ok: boolean; dr_ok: boolean };
  bon_commande_code: string | null;
  facture_code: string | null;
  facture_conforme: boolean | null;
  facture_ecart: string | null;
  montant_attendu: string | null;
  reference_bl: string;
}
interface Ligne {
  id: string;
  location_code: string;
  designation: string;
  quantite: string;
  unite: string;
  prix_unitaire: string | null;
  montant: string | null;
  quantite_livree: string | null;
}
interface ReceptionBL {
  id: string;
  code: string;
  location_code: string;
  reference_bl: string;
  date_reception: string;
  ecart_pct: string;
  litige: boolean;
  contentieux_code: string | null;
  dossier_gr_code: string | null;
}
interface Archive {
  id: string;
  location_code: string;
  sha256: string;
  integre: boolean;
  conserver_jusqu_au: string;
  contenu: { consommation: string | null; releves: unknown[] };
}
interface Glissant {
  fenetre_jours: number;
  horizon_jours: number;
  taux_jour: string | null;
  dernier_releve: string | null;
  projection_valeur: string | null;
  provisoire: boolean;
}
interface Reporting {
  periode: string;
  rows: { equipement: string; label: string; gr: boolean; jours_mobilises: number; utilisation_pct: string; economie: string | null }[];
  utilisation_moyenne_pct: string;
  economies: string | null;
  cout_gr: string | null;
  rentabilite_pct: string | null;
  provisoire: boolean;
}
interface Flux {
  rows: { affaire: string | null; titre: string; machines: { equipement: string; source: string; of: string | null }[]; consommation_gr: string; bl: { reference_bl: string; litige: boolean }[] }[];
}
interface BcAchat {
  id: string;
  code: string;
  is_global_rental: boolean;
}
interface FactureAchat {
  id: string;
  code: string;
  purchase_order: string;
}

const num = (v: string | null | undefined) => (v === null || v === undefined ? "—" : formatNumber(Number(v)));
const fcfa = (v: string | null) => (v === null ? "••••••" : formatMoney(v));
const moisCourant = () => new Date().toISOString().slice(0, 7);
const ETATS = ["bon", "usage", "degrade", "hors_service"];

function useListe<T>(key: string, path: string): T[] {
  return useQuery({ queryKey: ["m4e", key], queryFn: () => api.listAll<T>(path), retry: 0 }).data ?? [];
}

/** Écarts M4 : parc (plafond, historique, audit photo), commandes GR (validation, lignes, BL, 618), compteurs GR, reporting, plan de charge. */
export function EcartsM4Section() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const equipements = useListe<Equipement>("equipements", "/api/logistique/equipements/");
  const releves = useListe<Releve>("releves", "/api/logistique/releves-parc/");
  const historique = useListe<Historique>("historique", "/api/logistique/historique-equipements/");
  const audits = useListe<Audit>("audits", "/api/logistique/audits/");
  const locations = useListe<Location>("locations", "/api/logistique/locations/").filter((l) => l.statut !== "annulee");
  const lignes = useListe<Ligne>("lignes", "/api/logistique/lignes-gr/");
  const receptions = useListe<ReceptionBL>("receptions", "/api/logistique/receptions-bl/");
  const archives = useListe<Archive>("archives", "/api/logistique/archives-gr/");
  const bcs = useListe<BcAchat>("bcs", "/api/achats/orders/").filter((b) => b.is_global_rental);
  const factures = useListe<FactureAchat>("factures", "/api/achats/invoices/").filter((f) => bcs.some((b) => b.id === f.purchase_order));

  const actives = locations.filter((l) => l.statut === "active");
  const glissants = useQueries({
    queries: actives.map((l) => ({
      queryKey: ["m4e", "glissant", l.id],
      queryFn: () => api.get<Glissant>(`/api/logistique/locations/${l.id}/glissant/`),
      retry: 0,
    })),
  });

  const [periode, setPeriode] = useState(moisCourant());
  const reporting = useQuery({
    queryKey: ["m4e", "reporting", periode],
    queryFn: () => api.get<Reporting>(`/api/logistique/equipements/reporting/?periode=${periode}`),
    enabled: /^\d{4}-\d{2}$/.test(periode),
    retry: 0,
  }).data;
  const flux = useQuery({ queryKey: ["m4e", "flux"], queryFn: () => api.get<Flux>("/api/logistique/locations/flux-operations/"), retry: 0 }).data;

  // Audit photo : formulaire multipart (la photo est hachée SHA-256 côté serveur).
  const [audit, setAudit] = useState({ equipement: "", date_audit: new Date().toISOString().slice(0, 10), etat: "bon", observations: "" });
  const [photo, setPhoto] = useState<File | null>(null);
  const [auditMsg, setAuditMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const envoyerAudit = useMutation({
    mutationFn: () => api.upload("/api/logistique/audits/", photo as File, "photo", audit),
    onSuccess: () => {
      setAuditMsg({ ok: true, text: t("quickForm.created") });
      setPhoto(null);
      void qc.invalidateQueries({ queryKey: ["m4e"] });
    },
    onError: (e) => setAuditMsg({ ok: false, text: describeError(e) }),
  });
  const submitAudit = (e: FormEvent) => {
    e.preventDefault();
    setAuditMsg(null);
    if (photo) envoyerAudit.mutate();
  };

  const eqOpts = equipements.map((e) => ({ value: e.id, label: `${e.code} · ${e.label}` }));
  const locOpts = (ls: Location[]) => ls.map((l) => ({ value: l.id, label: `${l.code} · ${l.equipement_code}` }));
  const brouillons = locations.filter((l) => l.statut === "brouillon" && !l.emis_le);

  return (
    <>
      <SectionCard title={t("ecarts_m4.parc.title")}>
        <div data-testid="m4-parc">
          <p className="muted">{t("ecarts_m4.parc.hint")}</p>
          <div className="action-bar-buttons">
            <QuickForm
              title={t("ecarts_m4.parc.releve")}
              endpoint="/api/logistique/releves-parc/"
              fields={[
                { name: "equipement", label: t("ecarts_m4.equipement"), type: "select", required: true, options: eqOpts },
                { name: "date", label: t("ecarts_m4.date"), type: "date", required: true, defaultValue: new Date().toISOString().slice(0, 10) },
                { name: "valeur", label: t("ecarts_m4.parc.valeur"), type: "number", min: 0, step: "0.01", required: true },
                { name: "commentaire", label: t("ecarts_m4.parc.commentaire") },
              ]}
            />
          </div>
          <div style={{ overflowX: "auto" }}>
            <table className="table">
              <thead>
                <tr>
                  <th>{t("ecarts_m4.equipement")}</th>
                  <th className="num">{t("ecarts_m4.parc.compteur")}</th>
                  <th className="num">{t("ecarts_m4.parc.plafond")}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {equipements.map((e) => (
                  <tr key={e.id}>
                    <td>
                      {e.code} · {e.label}
                    </td>
                    <td className="num">
                      {num(e.compteur_value)} <span className="muted">{e.compteur_type_label}</span>
                    </td>
                    <td className="num">
                      {num(e.plafond_compteur)}{" "}
                      {e.plafond_pct !== null && <Badge tone={Number(e.plafond_pct) >= 90 ? "warn" : "ok"}>{formatNumber(Number(e.plafond_pct))} %</Badge>}
                    </td>
                    <td>
                      <ActionBar
                        actions={[{ label: t("ecarts_m4.parc.fixerPlafond"), path: `/api/logistique/equipements/${e.id}/plafond/`, tone: "ghost" as const, prompt: { name: "plafond_compteur", label: t("ecarts_m4.parc.plafond") } }]}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <h4>{t("ecarts_m4.parc.historiqueCompteurs")}</h4>
          <div style={{ overflowX: "auto" }}>
            <table className="table">
              <thead>
                <tr>
                  <th>{t("ecarts_m4.equipement")}</th>
                  <th>{t("ecarts_m4.date")}</th>
                  <th className="num">{t("ecarts_m4.parc.valeur")}</th>
                  <th>{t("ecarts_m4.parc.source")}</th>
                </tr>
              </thead>
              <tbody>
                {releves.slice(0, 15).map((r) => (
                  <tr key={r.id}>
                    <td>{r.equipement_code}</td>
                    <td>{formatDate(r.date)}</td>
                    <td className="num">{num(r.valeur)}</td>
                    <td>
                      {r.source_label}
                      {r.saisi_par_name ? ` · ${r.saisi_par_name}` : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </SectionCard>

      <SectionCard title={t("ecarts_m4.audit.title")}>
        <div data-testid="m4-audit">
          <p className="muted">{t("ecarts_m4.audit.hint")}</p>
          <form className="card quick-form" onSubmit={submitAudit} aria-label={t("ecarts_m4.audit.nouveau")}>
            <div className="quick-form-grid">
              <div className="field">
                <label htmlFor="m4-audit-eq">{t("ecarts_m4.equipement")} *</label>
                <select id="m4-audit-eq" required value={audit.equipement} onChange={(e) => setAudit({ ...audit, equipement: e.target.value })}>
                  <option value="">—</option>
                  {eqOpts.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label htmlFor="m4-audit-date">{t("ecarts_m4.date")} *</label>
                <input id="m4-audit-date" type="date" required value={audit.date_audit} onChange={(e) => setAudit({ ...audit, date_audit: e.target.value })} />
              </div>
              <div className="field">
                <label htmlFor="m4-audit-etat">{t("ecarts_m4.audit.etat")}</label>
                <select id="m4-audit-etat" value={audit.etat} onChange={(e) => setAudit({ ...audit, etat: e.target.value })}>
                  {ETATS.map((v) => (
                    <option key={v} value={v}>
                      {t(`ecarts_m4.audit.etats.${v}`)}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label htmlFor="m4-audit-photo">{t("ecarts_m4.audit.photo")} *</label>
                <input id="m4-audit-photo" type="file" accept="image/*" required onChange={(e) => setPhoto(e.target.files?.[0] ?? null)} />
              </div>
              <div className="field wide">
                <label htmlFor="m4-audit-obs">{t("ecarts_m4.audit.observations")}</label>
                <textarea id="m4-audit-obs" rows={2} value={audit.observations} onChange={(e) => setAudit({ ...audit, observations: e.target.value })} />
              </div>
            </div>
            <div className="quick-form-actions">
              <button type="submit" className="btn primary" disabled={envoyerAudit.isPending}>
                {t("ecarts_m4.audit.enregistrer")}
              </button>
              {auditMsg && (
                <p className={auditMsg.ok ? "quick-form-ok" : "action-error"} role={auditMsg.ok ? "status" : "alert"}>
                  {auditMsg.text}
                </p>
              )}
            </div>
          </form>
          <div style={{ overflowX: "auto" }}>
            <table className="table">
              <thead>
                <tr>
                  <th>{t("ecarts_m4.audit.code")}</th>
                  <th>{t("ecarts_m4.date")}</th>
                  <th>{t("ecarts_m4.audit.etat")}</th>
                  <th>{t("ecarts_m4.audit.empreinte")}</th>
                  <th>{t("ecarts_m4.audit.conservation")}</th>
                </tr>
              </thead>
              <tbody>
                {audits.map((a) => (
                  <tr key={a.id}>
                    <td>
                      {a.code} · {a.equipement_code}{" "}
                      {a.photo && (
                        <a href={a.photo} target="_blank" rel="noreferrer">
                          {t("ecarts_m4.audit.voirPhoto")}
                        </a>
                      )}
                    </td>
                    <td>{formatDate(a.date_audit)}</td>
                    <td>{a.etat_label}</td>
                    <td>
                      <code>{a.photo_sha256.slice(0, 12)}…</code>
                    </td>
                    <td>{formatDate(a.conserver_jusqu_au)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <h4>{t("ecarts_m4.audit.historique")}</h4>
          <div style={{ overflowX: "auto" }}>
            <table className="table">
              <thead>
                <tr>
                  <th>{t("ecarts_m4.equipement")}</th>
                  <th>{t("ecarts_m4.audit.champ")}</th>
                  <th>{t("ecarts_m4.audit.avantApres")}</th>
                  <th>{t("ecarts_m4.audit.par")}</th>
                </tr>
              </thead>
              <tbody>
                {historique.slice(0, 20).map((h) => (
                  <tr key={h.id}>
                    <td>{h.equipement_code}</td>
                    <td>{h.champ}</td>
                    <td>
                      {h.ancienne_valeur || "—"} → {h.nouvelle_valeur || "—"}
                    </td>
                    <td>
                      {h.modifie_par_name ?? "—"} · {formatDate(h.modifie_le)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </SectionCard>

      <SectionCard title={t("ecarts_m4.commandes.title")}>
        <div data-testid="m4-commandes">
          <p className="muted">{t("ecarts_m4.commandes.hint")}</p>
          <div className="action-bar-buttons">
            <QuickForm
              title={t("ecarts_m4.commandes.ajouterLigne")}
              endpoint="/api/logistique/lignes-gr/"
              fields={[
                { name: "location", label: t("ecarts_m4.location"), type: "select", required: true, options: locOpts(brouillons) },
                { name: "designation", label: t("ecarts_m4.commandes.designation"), required: true },
                { name: "quantite", label: t("ecarts_m4.commandes.quantite"), type: "number", min: 0, step: "0.01", required: true },
                { name: "unite", label: t("ecarts_m4.commandes.unite"), defaultValue: "j" },
                { name: "prix_unitaire", label: t("ecarts_m4.commandes.prix"), type: "number", min: 0 },
              ]}
            />
          </div>
          <div style={{ overflowX: "auto" }}>
            <table className="table">
              <thead>
                <tr>
                  <th>{t("ecarts_m4.location")}</th>
                  <th>{t("ecarts_m4.commandes.validations")}</th>
                  <th>{t("ecarts_m4.commandes.achats")}</th>
                  <th className="num">{t("ecarts_m4.commandes.attendu")}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {locations.map((l) => (
                  <tr key={l.id}>
                    <td>
                      {l.code} · {l.equipement_code} <Badge tone="brand">{l.statut_label}</Badge>
                    </td>
                    <td>
                      {l.validations.m2 && <Badge tone={l.validations.m2_ok ? "ok" : "warn"}>M2</Badge>}{" "}
                      {l.validations.dr && <Badge tone={l.validations.dr_ok ? "ok" : "warn"}>DR</Badge>}
                      {!l.validations.m2 && !l.validations.dr && <span className="muted">{t("ecarts_m4.commandes.sousSeuil")}</span>}
                    </td>
                    <td>
                      {l.bon_commande_code ?? "—"} / {l.facture_code ?? "—"}{" "}
                      {l.facture_conforme !== null && (
                        <Badge tone={l.facture_conforme ? "ok" : "err"}>{l.facture_conforme ? t("ecarts_m4.commandes.conforme") : t("ecarts_m4.commandes.ecart")}</Badge>
                      )}{" "}
                      <Badge tone="warn">618</Badge>
                    </td>
                    <td className="num">{fcfa(l.montant_attendu)}</td>
                    <td>
                      <ActionBar
                        actions={[
                          ...(l.statut === "brouillon" && !l.emis_le && l.validations.m2 && !l.validations.m2_ok
                            ? [{ label: t("ecarts_m4.commandes.validerM2"), path: `/api/logistique/locations/${l.id}/valider-m2/`, tone: "ghost" as const }]
                            : []),
                          ...(l.statut === "brouillon" && !l.emis_le && l.validations.dr && !l.validations.dr_ok
                            ? [{ label: t("ecarts_m4.commandes.validerDr"), path: `/api/logistique/locations/${l.id}/valider-dr/`, tone: "ghost" as const }]
                            : []),
                          ...(!l.bon_commande_code
                            ? [{ label: t("ecarts_m4.commandes.lierBc"), path: `/api/logistique/locations/${l.id}/lier-bc-achat/`, tone: "ghost" as const, prompt: { name: "bon_commande_achat", label: t("ecarts_m4.commandes.choisirBc"), options: bcs.map((b) => ({ value: b.id, label: b.code })) } }]
                            : []),
                          ...(!l.facture_code
                            ? [{ label: t("ecarts_m4.commandes.rapprocher"), path: `/api/logistique/locations/${l.id}/rapprocher-facture/`, tone: "ghost" as const, prompt: { name: "facture_achat", label: t("ecarts_m4.commandes.choisirFacture"), options: factures.map((f) => ({ value: f.id, label: f.code })) } }]
                            : []),
                          ...(l.statut === "brouillon" || l.statut === "active"
                            ? [{ label: t("ecarts_m4.commandes.receptionnerBl"), path: `/api/logistique/locations/${l.id}/receptionner-bl/`, tone: "ghost" as const, prompt: { name: "reference_bl", label: t("ecarts_m4.commandes.referenceBl") } }]
                            : []),
                          { label: t("ecarts_m4.commandes.escalader"), path: `/api/logistique/locations/${l.id}/escalader/`, tone: "danger" as const, prompt: { name: "motif", label: t("ecarts_m4.commandes.motif") } },
                        ]}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <h4>{t("ecarts_m4.commandes.lignes")}</h4>
          <div style={{ overflowX: "auto" }}>
            <table className="table">
              <thead>
                <tr>
                  <th>{t("ecarts_m4.location")}</th>
                  <th>{t("ecarts_m4.commandes.designation")}</th>
                  <th className="num">{t("ecarts_m4.commandes.quantite")}</th>
                  <th className="num">{t("ecarts_m4.commandes.livree")}</th>
                  <th className="num">{t("ecarts_m4.commandes.montant")}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {lignes.map((g) => (
                  <tr key={g.id}>
                    <td>{g.location_code}</td>
                    <td>{g.designation}</td>
                    <td className="num">
                      {num(g.quantite)} {g.unite}
                    </td>
                    <td className="num">{num(g.quantite_livree)}</td>
                    <td className="num">{fcfa(g.montant)}</td>
                    <td>
                      <ActionBar
                        actions={[{ label: t("ecarts_m4.commandes.livrer"), path: `/api/logistique/lignes-gr/${g.id}/livrer/`, tone: "ghost" as const, prompt: { name: "quantite_livree", label: t("ecarts_m4.commandes.livree") } }]}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <h4>{t("ecarts_m4.commandes.receptions")}</h4>
          <div style={{ overflowX: "auto" }}>
            <table className="table" data-testid="m4-receptions-bl">
              <thead>
                <tr>
                  <th>{t("ecarts_m4.commandes.referenceBl")}</th>
                  <th>{t("ecarts_m4.date")}</th>
                  <th className="num">{t("ecarts_m4.commandes.ecartPct")}</th>
                  <th>{t("ecarts_m4.commandes.escaladeM12")}</th>
                </tr>
              </thead>
              <tbody>
                {receptions.map((r) => (
                  <tr key={r.id}>
                    <td>
                      {r.code} · {r.location_code} · {r.reference_bl}
                    </td>
                    <td>{formatDate(r.date_reception)}</td>
                    <td className="num">{formatNumber(Number(r.ecart_pct))} %</td>
                    <td>{r.litige ? <Badge tone="err">{`${r.contentieux_code ?? ""} · ${r.dossier_gr_code ?? ""}`}</Badge> : <Badge tone="ok">{t("ecarts_m4.commandes.conforme")}</Badge>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </SectionCard>

      <SectionCard title={t("ecarts_m4.compteurs.title")}>
        <div data-testid="m4-compteurs">
          <p className="muted">{t("ecarts_m4.compteurs.hint")}</p>
          <div className="action-bar-buttons">
            <QuickForm
              title={t("ecarts_m4.compteurs.saisir")}
              endpoint="/api/logistique/lectures/"
              fields={[
                { name: "location", label: t("ecarts_m4.location"), type: "select", required: true, options: locOpts(actives) },
                { name: "date", label: t("ecarts_m4.date"), type: "date", required: true, defaultValue: new Date().toISOString().slice(0, 10) },
                { name: "valeur", label: t("ecarts_m4.parc.valeur"), type: "number", min: 0, step: "0.01", required: true },
                {
                  name: "type_lecture",
                  label: t("ecarts_m4.compteurs.type"),
                  type: "select",
                  required: true,
                  defaultValue: "periodique",
                  options: ["initiale", "periodique", "finale"].map((v) => ({ value: v, label: t(`ecarts_m4.compteurs.types.${v}`) })),
                },
              ]}
            />
          </div>
          <div style={{ overflowX: "auto" }}>
            <table className="table">
              <thead>
                <tr>
                  <th>{t("ecarts_m4.location")}</th>
                  <th className="num">{t("ecarts_m4.compteurs.dernier")}</th>
                  <th className="num">{t("ecarts_m4.compteurs.taux")}</th>
                  <th className="num">{t("ecarts_m4.compteurs.projection")}</th>
                </tr>
              </thead>
              <tbody>
                {actives.map((l, i) => {
                  const g = glissants[i]?.data;
                  return (
                    <tr key={l.id}>
                      <td>
                        {l.code} · {l.equipement_code} {g?.provisoire && <Badge tone="warn">{t("ecarts_m4.provisoire")}</Badge>}
                      </td>
                      <td className="num">{num(g?.dernier_releve)}</td>
                      <td className="num">{num(g?.taux_jour)}</td>
                      <td className="num">{num(g?.projection_valeur)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="muted">{t("ecarts_m4.compteurs.formule")}</p>
          <h4>{t("ecarts_m4.compteurs.archives")}</h4>
          <div style={{ overflowX: "auto" }}>
            <table className="table">
              <thead>
                <tr>
                  <th>{t("ecarts_m4.location")}</th>
                  <th className="num">{t("ecarts_m4.compteurs.consommation")}</th>
                  <th>{t("ecarts_m4.audit.empreinte")}</th>
                  <th>{t("ecarts_m4.audit.conservation")}</th>
                </tr>
              </thead>
              <tbody>
                {archives.map((a) => (
                  <tr key={a.id}>
                    <td>{a.location_code}</td>
                    <td className="num">{num(a.contenu.consommation)}</td>
                    <td>
                      <code>{a.sha256.slice(0, 12)}…</code> <Badge tone={a.integre ? "ok" : "err"}>{a.integre ? t("ecarts_m4.compteurs.integre") : t("ecarts_m4.compteurs.altere")}</Badge>
                    </td>
                    <td>{formatDate(a.conserver_jusqu_au)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </SectionCard>

      <SectionCard title={t("ecarts_m4.reporting.title")}>
        <div data-testid="m4-reporting">
          <label>
            {t("ecarts_m4.reporting.mois")}{" "}
            <input type="month" value={periode} onChange={(e) => setPeriode(e.target.value)} aria-label={t("ecarts_m4.reporting.mois")} />
          </label>
          {reporting?.provisoire && (
            <p className="action-error" role="note">
              {t("ecarts_m4.reporting.warnProvisoire")}
            </p>
          )}
          {reporting && (
            <>
              <p>
                {t("ecarts_m4.reporting.utilisation")} : <strong>{formatNumber(Number(reporting.utilisation_moyenne_pct))} %</strong> · {t("ecarts_m4.reporting.economies")} :{" "}
                <strong>{fcfa(reporting.economies)}</strong> · {t("ecarts_m4.reporting.rentabilite")} :{" "}
                <strong>{reporting.rentabilite_pct === null ? "—" : `${formatNumber(Number(reporting.rentabilite_pct))} %`}</strong>
              </p>
              <p className="muted">{t("ecarts_m4.reporting.formules")}</p>
              <div style={{ overflowX: "auto" }}>
                <table className="table">
                  <thead>
                    <tr>
                      <th>{t("ecarts_m4.equipement")}</th>
                      <th className="num">{t("ecarts_m4.reporting.jours")}</th>
                      <th className="num">{t("ecarts_m4.reporting.utilisation")}</th>
                      <th className="num">{t("ecarts_m4.reporting.economies")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {reporting.rows.map((r) => (
                      <tr key={r.equipement}>
                        <td>
                          {r.equipement} · {r.label} {r.gr && <Badge tone="warn">GR</Badge>}
                        </td>
                        <td className="num">{r.jours_mobilises}</td>
                        <td className="num">{formatNumber(Number(r.utilisation_pct))} %</td>
                        <td className="num">{r.gr ? "—" : fcfa(r.economie)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      </SectionCard>

      <SectionCard title={t("ecarts_m4.flux.title")}>
        <div data-testid="m4-flux">
          <p className="muted">{t("ecarts_m4.flux.hint")}</p>
          <ActionBar actions={[{ label: t("ecarts_m4.flux.proposer"), path: "/api/logistique/demandes/proposer/" }]} />
          <div style={{ overflowX: "auto" }}>
            <table className="table">
              <thead>
                <tr>
                  <th>{t("ecarts_m4.flux.affaire")}</th>
                  <th>{t("ecarts_m4.flux.machines")}</th>
                  <th className="num">{t("ecarts_m4.compteurs.consommation")}</th>
                  <th>{t("ecarts_m4.flux.bl")}</th>
                </tr>
              </thead>
              <tbody>
                {(flux?.rows ?? []).map((r) => (
                  <tr key={r.affaire ?? "sans"}>
                    <td>{r.affaire ? `${r.affaire} — ${r.titre}` : r.titre}</td>
                    <td>{r.machines.map((m) => `${m.equipement}${m.of ? ` (${m.of})` : ""}${m.source === "gr" ? " GR" : ""}`).join(", ")}</td>
                    <td className="num">{num(r.consommation_gr)}</td>
                    <td>
                      {r.bl.length} {r.bl.some((b) => b.litige) && <Badge tone="err">{t("ecarts_m4.flux.litige")}</Badge>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </SectionCard>
    </>
  );
}
