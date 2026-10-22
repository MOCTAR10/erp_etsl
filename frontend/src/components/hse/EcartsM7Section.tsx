import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate } from "../../lib/format";
import { describeError } from "../../lib/offlineQueue";
import { ActionBar, Badge, QuickForm, SectionCard } from "../ui";
import { useListeHse, type ValeurListeHse } from "./listesHse";

interface Modele {
  id: string;
  code: string;
  intitule: string;
  type_audit: string;
  referentiel: string;
  questions: string[];
  actif: boolean;
  est_provisoire: boolean;
}
interface Audit {
  id: string;
  code: string;
  zone: string;
  date_prevue: string;
  statut: string;
  score: number | null;
  nb_constats: number;
}
interface Reponse {
  id: string;
  ordre: number;
  question: string;
  reponse: string;
  reponse_label: string;
  commentaire: string;
  constat: string | null;
  constat_gravite: string | null;
}
interface Risque {
  id: string;
  code: string;
  description: string;
  score: number;
  criticite: string;
  duer: string | null;
}
interface Duer {
  id: string;
  code: string;
  perimetre: string;
  statut: string;
}
interface Plan {
  id: string;
  code: string;
  entreprise_exterieure: string;
  site: string;
  site_gr: boolean;
  date_inspection_commune: string | null;
  date_debut: string;
  date_fin: string | null;
  statut: string;
  statut_label: string;
  en_vigueur: boolean;
  risques_detail: { id: string; code: string; criticite: string; score: number }[];
}
interface Prestataire {
  id: string;
  nom: string;
  numero_agrement: string;
  autorite: string;
  types_dechets: string;
  date_fin_validite: string;
  valide: boolean;
}
interface Bsd {
  id: string;
  code: string;
  type_dechet: string;
  type_label: string;
  quantite: string;
  unite: string;
  numero_bsd: string;
  prestataire: string | null;
  prestataire_nom: string | null;
  statut: string;
  statut_label: string;
}
interface Fiche {
  id: string;
  code: string;
  titre: string;
  categorie: string;
  version: number;
  provisoire: boolean;
  statut: string;
  statut_label: string;
}

const M = "ecarts_m6m7";
const useListe = <T,>(key: string, path: string) =>
  useQuery({ queryKey: ["ecarts-m6m7", key], queryFn: () => api.listAll<T>(path), retry: 0 }).data ?? [];

function Provisoire({ provisoire }: { provisoire: boolean }) {
  const { t } = useTranslation();
  return provisoire ? <Badge tone="warn">{t(`${M}.provisoire`)}</Badge> : <Badge tone="ok">{t(`${M}.confirme`)}</Badge>;
}

/** Bouton d'édition PATCH (activer / désactiver une valeur de liste) : l'API garde les droits. */
function PatchButton({ path, body, label }: { path: string; body: unknown; label: string }) {
  const qc = useQueryClient();
  const run = useMutation({ mutationFn: () => api.patch<unknown>(path, body), onSuccess: () => void qc.invalidateQueries() });
  return (
    <>
      <button type="button" className="btn ghost" onClick={() => run.mutate()} disabled={run.isPending}>{label}</button>
      {run.isError && <span role="alert" className="muted"> {describeError(run.error)}</span>}
    </>
  );
}

const CATEGORIES = ["type_permis", "type_incident", "type_dechet", "partage_gr"] as const;

/** §9.2 : listes paramétrables (types de permis, d'incidents, de déchets ; destinataires du partage site GR). */
export function ListesHseSection() {
  const { t } = useTranslation();
  const [categorie, setCategorie] = useState<(typeof CATEGORIES)[number]>("type_permis");
  const valeurs = useListe<ValeurListeHse>(`listes-${categorie}`, `/api/hse/listes/?categorie=${categorie}`);
  return (
    <SectionCard title={t(`${M}.listes.title`)}>
      <div data-testid="listes-hse">
        <p className="muted">{t(`${M}.listes.aide`)}</p>
        <label>
          {t(`${M}.listes.categorie`)}{" "}
          <select value={categorie} onChange={(e) => setCategorie(e.target.value as (typeof CATEGORIES)[number])} aria-label={t(`${M}.listes.categorie`)}>
            {CATEGORIES.map((c) => <option key={c} value={c}>{t(`${M}.listes.categories.${c}`)}</option>)}
          </select>
        </label>{" "}
        <QuickForm
          title={t(`${M}.listes.ajouter`)}
          endpoint="/api/hse/listes/"
          transform={(v) => ({ ...v, categorie, gaz_obligatoire: v.gaz_obligatoire === "true", dangereux: v.dangereux === "true" })}
          fields={[
            { name: "code", label: t(`${M}.listes.code`), required: true },
            { name: "libelle", label: t(`${M}.listes.libelle`), required: true },
            ...(categorie === "type_permis" ? [{ name: "gaz_obligatoire", label: t(`${M}.listes.gaz`), type: "select" as const, defaultValue: "false", options: [{ value: "false", label: t(`${M}.non`) }, { value: "true", label: t(`${M}.oui`) }] }] : []),
            ...(categorie === "type_dechet" ? [{ name: "dangereux", label: t(`${M}.listes.dangereux`), type: "select" as const, defaultValue: "false", options: [{ value: "false", label: t(`${M}.non`) }, { value: "true", label: t(`${M}.oui`) }] }] : []),
          ]}
        />
        <table className="table">
          <caption className="sr-only">{t(`${M}.listes.title`)}</caption>
          <thead>
            <tr>
              <th>{t(`${M}.listes.code`)}</th>
              <th>{t(`${M}.listes.libelle`)}</th>
              <th>{t(`${M}.listes.etat`)}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {valeurs.map((v) => (
              <tr key={v.id}>
                <td><code>{v.code}</code></td>
                <td>
                  {v.libelle}
                  {v.gaz_obligatoire && <Badge tone="warn">{t(`${M}.listes.gaz`)}</Badge>}
                  {v.dangereux && <Badge tone="err">{t(`${M}.listes.dangereux`)}</Badge>}
                </td>
                <td>
                  <Badge tone={v.actif ? "ok" : "neutral"}>{t(v.actif ? `${M}.actif` : `${M}.inactif`)}</Badge> <Provisoire provisoire={v.est_provisoire} />
                </td>
                <td>
                  <PatchButton path={`/api/hse/listes/${v.id}/`} body={{ actif: !v.actif }} label={t(v.actif ? `${M}.desactiver` : `${M}.activer`)} />
                  {v.est_provisoire && <ActionBar actions={[{ label: t(`${M}.confirmer`), path: `/api/hse/listes/${v.id}/confirmer/`, tone: "ghost" }]} />}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </SectionCard>
  );
}

/** M7-02 : check-lists d'audit (trames provisoires), réponses, constats et rapport PDF. */
export function ChecklistsAuditSection() {
  const { t } = useTranslation();
  const modeles = useListe<Modele>("modeles", "/api/hse/modeles-checklist/");
  const audits = useListe<Audit>("audits", "/api/hse/audits/");
  const [audit, setAudit] = useState("");
  const reponses = useListe<Reponse>(`reponses-${audit}`, audit ? `/api/hse/reponses-checklist/?audit=${audit}` : "/api/hse/reponses-checklist/?audit=aucun");
  const courant = audits.find((a) => a.id === audit);
  const ouverts = audits.filter((a) => a.statut !== "cloture");
  const gravites = ["mineur", "majeur", "critique"].map((g) => ({ value: g, label: t(`${M}.checklist.gravites.${g}`) }));
  return (
    <SectionCard title={t(`${M}.checklist.title`)}>
      <div data-testid="checklists-hse">
        <div className="action-bar-buttons">
          <QuickForm
            title={t(`${M}.checklist.modele`)}
            endpoint="/api/hse/modeles-checklist/"
            fields={[
              { name: "intitule", label: t(`${M}.checklist.intitule`), required: true },
              { name: "type_audit", label: t(`${M}.checklist.type`), type: "select", defaultValue: "inspection", options: ["audit", "inspection"].map((v) => ({ value: v, label: t(`${M}.checklist.types.${v}`) })) },
              { name: "referentiel", label: t(`${M}.checklist.referentiel`) },
              { name: "questions_texte", label: t(`${M}.checklist.questions`), type: "textarea", required: true },
            ]}
          />
          <QuickForm
            title={t(`${M}.checklist.constat`)}
            endpoint="/api/hse/constats-audit/"
            fields={[
              { name: "audit", label: t(`${M}.checklist.audit`), type: "select", required: true, options: ouverts.map((a) => ({ value: a.id, label: `${a.code} · ${a.zone}` })) },
              { name: "description", label: t(`${M}.checklist.description`), type: "textarea", required: true },
              { name: "gravite", label: t(`${M}.checklist.gravite`), type: "select", required: true, defaultValue: "mineur", options: [{ value: "conforme", label: t(`${M}.checklist.gravites.conforme`) }, ...gravites] },
            ]}
          />
        </div>
        <table className="table">
          <caption className="sr-only">{t(`${M}.checklist.modeles`)}</caption>
          <tbody>
            {modeles.map((m) => (
              <tr key={m.id}>
                <td><strong>{m.code}</strong> · {m.intitule}</td>
                <td>{t(`${M}.checklist.nbQuestions`, { n: m.questions.length })}</td>
                <td><Provisoire provisoire={m.est_provisoire} /></td>
                <td>{m.est_provisoire && <ActionBar actions={[{ label: t(`${M}.confirmer`), path: `/api/hse/modeles-checklist/${m.id}/confirmer/`, tone: "ghost" }]} />}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <label>
          {t(`${M}.checklist.audit`)}{" "}
          <select value={audit} onChange={(e) => setAudit(e.target.value)} aria-label={t(`${M}.checklist.choisirAudit`)}>
            <option value="">—</option>
            {audits.map((a) => <option key={a.id} value={a.id}>{`${a.code} · ${a.zone} · ${formatDate(a.date_prevue)}`}</option>)}
          </select>
        </label>
        {courant && (
          <>
            <div className="action-bar-buttons">
              {courant.statut === "planifie" && modeles.length > 0 && (
                <ActionBar
                  actions={[{
                    label: t(`${M}.checklist.appliquer`), path: `/api/hse/audits/${courant.id}/appliquer-checklist/`,
                    prompt: { name: "modele", label: t(`${M}.checklist.modele`), options: modeles.filter((m) => m.actif).map((m) => ({ value: m.id, label: `${m.code} · ${m.intitule}` })) },
                  }]}
                />
              )}
              <button type="button" className="btn ghost" onClick={() => void api.download(`/api/hse/audits/${courant.id}/rapport-pdf/`, `rapport-audit-${courant.code}.pdf`)}>
                {t(`${M}.checklist.rapport`)}
              </button>
            </div>
            {courant.score !== null && <p role="status">{t(`${M}.checklist.score`, { score: courant.score })}</p>}
            {reponses.length > 0 && (
              <table className="table" data-testid="reponses-checklist">
                <caption className="sr-only">{t(`${M}.checklist.title`)}</caption>
                <tbody>
                  {reponses.map((r) => (
                    <tr key={r.id}>
                      <td className="num">{r.ordre}</td>
                      <td>{r.question}{r.commentaire ? <div className="muted">{r.commentaire}</div> : null}</td>
                      <td>
                        <Badge tone={r.reponse === "conforme" ? "ok" : r.reponse === "non_conforme" ? "err" : r.reponse === "sans_objet" ? "neutral" : "warn"}>{r.reponse_label}</Badge>
                        {r.constat_gravite && <span className="muted"> · {t(`${M}.checklist.gravites.${r.constat_gravite}`)}</span>}
                      </td>
                      <td>
                        {courant.statut !== "cloture" && (
                          <ActionBar
                            actions={[
                              { label: t(`${M}.checklist.conforme`), path: `/api/hse/reponses-checklist/${r.id}/repondre/`, body: { reponse: "conforme" }, tone: "ghost" },
                              { label: t(`${M}.checklist.nonConforme`), path: `/api/hse/reponses-checklist/${r.id}/repondre/`, body: { reponse: "non_conforme" }, tone: "danger", prompt: { name: "gravite", label: t(`${M}.checklist.gravite`), options: gravites } },
                              { label: t(`${M}.checklist.sansObjet`), path: `/api/hse/reponses-checklist/${r.id}/repondre/`, body: { reponse: "sans_objet" }, tone: "ghost" },
                            ]}
                          />
                        )}
                      </td>
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

/** M7-03 : plan de prévention (inspection commune, risques, mesures) et saisie des risques à l'écran. */
export function PlansPreventionSection() {
  const { t } = useTranslation();
  const plans = useListe<Plan>("plans", "/api/hse/plans-prevention/");
  const risques = useListe<Risque>("risques", "/api/hse/evaluations-risques/?ouverts=1");
  const duers = useListe<Duer>("duers", "/api/hse/duer/");
  const ouiNon = [{ value: "false", label: t(`${M}.non`) }, { value: "true", label: t(`${M}.oui`) }];
  return (
    <SectionCard title={`${t(`${M}.pdp.title`)} · ${plans.length}`}>
      <div data-testid="plans-prevention">
        <div className="action-bar-buttons">
          <QuickForm
            title={t(`${M}.pdp.nouveau`)}
            endpoint="/api/hse/plans-prevention/"
            transform={(v) => ({ ...v, site_gr: v.site_gr === "true" })}
            fields={[
              { name: "entreprise_exterieure", label: t(`${M}.pdp.entreprise`), required: true },
              { name: "site", label: t(`${M}.pdp.site`), required: true },
              { name: "site_gr", label: t(`${M}.gr.siteGr`), type: "select", defaultValue: "false", options: ouiNon },
              { name: "date_inspection_commune", label: t(`${M}.pdp.inspection`), type: "date" },
              { name: "date_debut", label: t(`${M}.pdp.periodeDu`), type: "date", required: true },
              { name: "date_fin", label: t(`${M}.pdp.periodeAu`), type: "date" },
              { name: "mesures", label: t(`${M}.pdp.mesures`), type: "textarea", required: true },
              { name: "consignes_urgence", label: t(`${M}.pdp.urgence`), type: "textarea" },
            ]}
          />
          <QuickForm
            title={t(`${M}.risque.nouveau`)}
            endpoint="/api/hse/evaluations-risques/"
            fields={[
              { name: "lieux", label: t(`${M}.risque.lieu`), required: true },
              { name: "activite", label: t(`${M}.risque.activite`) },
              { name: "description", label: t(`${M}.risque.description`), type: "textarea", required: true },
              { name: "probabilite", label: t(`${M}.risque.probabilite`), type: "number", required: true, min: 1, defaultValue: "1" },
              { name: "gravite", label: t(`${M}.risque.gravite`), type: "number", required: true, min: 1, defaultValue: "1" },
              { name: "mesure", label: t(`${M}.risque.mesure`), type: "textarea" },
              { name: "duer", label: "DUER", type: "select", options: duers.filter((d) => d.statut !== "approuve").map((d) => ({ value: d.id, label: `${d.code} · ${d.perimetre}` })) },
            ]}
          />
        </div>
        <p className="muted">{t(`${M}.pdp.aide`)}</p>
        {plans.length > 0 && (
          <table className="table">
            <caption className="sr-only">{t(`${M}.pdp.title`)}</caption>
            <thead>
              <tr>
                <th>{t(`${M}.pdp.plan`)}</th>
                <th>{t(`${M}.pdp.inspection`)}</th>
                <th>{t(`${M}.pdp.risques`)}</th>
                <th>{t(`${M}.pdp.statut`)}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {plans.map((p) => (
                <tr key={p.id}>
                  <td>
                    <strong>{p.code}</strong> · {p.entreprise_exterieure} · {p.site}
                    {p.site_gr && <Badge tone="brand">{t(`${M}.gr.badge`)}</Badge>}
                  </td>
                  <td>{p.date_inspection_commune ? formatDate(p.date_inspection_commune) : "—"}</td>
                  <td>{p.risques_detail.map((r) => `${r.code} (${r.score})`).join(", ") || "—"}</td>
                  <td>
                    <Badge tone={p.statut === "valide" ? "ok" : p.statut === "clos" ? "neutral" : "warn"}>{p.statut_label}</Badge>
                    {p.en_vigueur && <span className="muted"> · {t(`${M}.pdp.enVigueur`)}</span>}
                  </td>
                  <td>
                    <ActionBar
                      actions={[
                        ...(p.statut === "brouillon"
                          ? [
                              { label: t(`${M}.pdp.ajouterRisque`), path: `/api/hse/plans-prevention/${p.id}/ajouter-risque/`, tone: "ghost" as const, prompt: { name: "risque", label: t(`${M}.pdp.risque`), options: risques.map((r) => ({ value: r.id, label: `${r.code} · ${r.description.slice(0, 50)} (${r.score})` })) } },
                              { label: t(`${M}.pdp.valider`), path: `/api/hse/plans-prevention/${p.id}/valider/` },
                            ]
                          : []),
                        ...(p.statut === "valide" ? [{ label: t(`${M}.pdp.clore`), path: `/api/hse/plans-prevention/${p.id}/cloturer/`, tone: "ghost" as const, confirm: t(`${M}.pdp.clore`) }] : []),
                      ]}
                    />
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

/** BSD : prestataires déchets agréés, formulaire BSD, émission et traitement contrôlés. */
export function BsdPrestatairesSection() {
  const { t } = useTranslation();
  const prestataires = useListe<Prestataire>("prestataires", "/api/hse/prestataires-dechets/");
  const bsds = useListe<Bsd>("bsd", "/api/hse/bordereaux-dechets/");
  const types = useListeHse("type_dechet");
  const valides = prestataires.filter((p) => p.valide).map((p) => ({ value: p.id, label: `${p.nom} · ${p.numero_agrement}` }));
  const ouverts = bsds.filter((b) => b.statut !== "traite");
  return (
    <SectionCard title={t(`${M}.bsd.title`)}>
      <div data-testid="bsd-prestataires">
        <div className="action-bar-buttons">
          <QuickForm
            title={t(`${M}.bsd.prestataire`)}
            endpoint="/api/hse/prestataires-dechets/"
            fields={[
              { name: "nom", label: t(`${M}.bsd.nom`), required: true },
              { name: "numero_agrement", label: t(`${M}.bsd.agrement`), required: true },
              { name: "autorite", label: t(`${M}.bsd.autorite`) },
              { name: "types_dechets", label: t(`${M}.bsd.types`) },
              { name: "date_fin_validite", label: t(`${M}.bsd.validite`), type: "date", required: true },
            ]}
          />
          <QuickForm
            title={t(`${M}.bsd.nouveau`)}
            endpoint="/api/hse/bordereaux-dechets/"
            fields={[
              { name: "type_dechet", label: t(`${M}.bsd.typeDechet`), type: "select", required: true, defaultValue: "dib", options: types },
              { name: "quantite", label: t(`${M}.bsd.quantite`), type: "number", required: true, min: 0, step: "0.01" },
              { name: "unite", label: t(`${M}.bsd.unite`), type: "select", defaultValue: "kg", options: ["kg", "t", "l", "unite"].map((u) => ({ value: u, label: u })) },
              { name: "prestataire", label: t(`${M}.bsd.prestataireAgree`), type: "select", options: valides },
              { name: "date_enlevement", label: t(`${M}.bsd.enlevement`), type: "date" },
              { name: "destination", label: t(`${M}.bsd.destination`) },
            ]}
          />
        </div>
        <p className="muted">{t(`${M}.bsd.aide`)}</p>
        {prestataires.length > 0 && (
          <table className="table">
            <caption className="sr-only">{t(`${M}.bsd.prestataires`)}</caption>
            <tbody>
              {prestataires.map((p) => (
                <tr key={p.id}>
                  <td>{p.nom}{p.autorite ? <span className="muted"> · {p.autorite}</span> : null}</td>
                  <td>{p.numero_agrement}</td>
                  <td>{p.types_dechets || t(`${M}.bsd.tous`)}</td>
                  <td>{formatDate(p.date_fin_validite)} <Badge tone={p.valide ? "ok" : "err"}>{t(p.valide ? `${M}.bsd.valide` : `${M}.bsd.expire`)}</Badge></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {ouverts.length > 0 && (
          <table className="table" data-testid="bsd-ouverts">
            <caption className="sr-only">{t(`${M}.bsd.ouverts`)}</caption>
            <tbody>
              {ouverts.map((b) => (
                <tr key={b.id}>
                  <td><strong>{b.code}</strong> · {b.type_label}</td>
                  <td className="num">{b.quantite} {b.unite}</td>
                  <td>{b.prestataire_nom ?? <Badge tone="warn">{t(`${M}.bsd.sansPrestataire`)}</Badge>}</td>
                  <td><Badge tone={b.statut === "emis" ? "brand" : "warn"}>{b.statut_label}</Badge></td>
                  <td>
                    <ActionBar
                      actions={[
                        ...(!b.prestataire && valides.length > 0
                          ? [{ label: t(`${M}.bsd.affecter`), path: `/api/hse/bordereaux-dechets/${b.id}/affecter-prestataire/`, tone: "ghost" as const, prompt: { name: "prestataire", label: t(`${M}.bsd.prestataireAgree`), options: valides } }]
                          : []),
                        ...(b.statut === "en_attente"
                          ? [{ label: t(`${M}.bsd.emettre`), path: `/api/hse/bordereaux-dechets/${b.id}/emettre/`, prompt: { name: "numero_bsd", label: t(`${M}.bsd.numero`) } }]
                          : []),
                        ...(b.statut === "emis" ? [{ label: t(`${M}.bsd.traiter`), path: `/api/hse/bordereaux-dechets/${b.id}/traiter/`, confirm: t(`${M}.bsd.traiter`) }] : []),
                      ]}
                    />
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

/** M7-08 : fiches sécurité (publiées = consultables sur /terrain, y compris hors ligne). */
export function FichesSecuriteSection() {
  const { t } = useTranslation();
  const fiches = useListe<Fiche>("fiches", "/api/hse/fiches-securite/");
  const types = useListeHse("type_permis");
  return (
    <SectionCard title={`${t(`${M}.fiches.title`)} · ${fiches.length}`}>
      <div data-testid="fiches-securite">
        <QuickForm
          title={t(`${M}.fiches.nouvelle`)}
          endpoint="/api/hse/fiches-securite/"
          fields={[
            { name: "titre", label: t(`${M}.fiches.titre`), required: true },
            { name: "categorie", label: t(`${M}.fiches.categorie`), type: "select", options: types },
            { name: "risques", label: t(`${M}.fiches.risques`), type: "textarea" },
            { name: "consignes", label: t(`${M}.fiches.consignes`), type: "textarea", required: true },
            { name: "epi", label: t(`${M}.fiches.epi`), type: "textarea" },
            { name: "urgence", label: t(`${M}.fiches.urgence`), type: "textarea" },
          ]}
        />
        <p className="muted">{t(`${M}.fiches.aide`)}</p>
        <table className="table">
          <caption className="sr-only">{t(`${M}.fiches.title`)}</caption>
          <tbody>
            {fiches.map((f) => (
              <tr key={f.id}>
                <td><strong>{f.code}</strong> · {f.titre} <span className="muted">v{f.version}</span></td>
                <td>
                  <Badge tone={f.statut === "publiee" ? "ok" : f.statut === "retiree" ? "neutral" : "warn"}>{f.statut_label}</Badge>{" "}
                  {f.provisoire && <Badge tone="warn">{t(`${M}.provisoire`)}</Badge>}
                </td>
                <td>
                  <ActionBar
                    actions={[
                      ...(f.statut !== "publiee" ? [{ label: t(`${M}.fiches.publier`), path: `/api/hse/fiches-securite/${f.id}/publier/` }] : []),
                      ...(f.statut === "publiee" ? [{ label: t(`${M}.fiches.retirer`), path: `/api/hse/fiches-securite/${f.id}/retirer/`, tone: "ghost" as const }] : []),
                    ]}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </SectionCard>
  );
}

/** Sections des écarts M7 (lot ecarts-m6m7), montées dans la page HSE. */
export function EcartsM7Sections() {
  return (
    <>
      <ChecklistsAuditSection />
      <PlansPreventionSection />
      <BsdPrestatairesSection />
      <FichesSecuriteSection />
      <ListesHseSection />
    </>
  );
}
