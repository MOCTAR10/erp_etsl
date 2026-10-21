import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate, formatNumber } from "../../lib/format";
import { describeError } from "../../lib/offlineQueue";
import { ActionBar, Badge, Kpi, QuickForm, SectionCard } from "../ui";

interface Utilisateur {
  id: string;
  nom: string;
  role: string;
}
interface Processus {
  id: string;
  code: string;
  libelle: string;
  type_processus: string;
  pilote_nom: string | null;
  indicateur: string;
  unite: string;
  cible: string | null;
  sens: "mini" | "maxi";
  valeur: string | null;
  date_mesure: string | null;
  cible_atteinte: boolean | null;
}
interface Responsabilite {
  id: string;
  fonction: string;
  titulaire_nom: string | null;
  suppleant_nom: string | null;
  rattachement: string;
  missions: string;
  processus_code: string | null;
}
interface DocQualite {
  id: string;
  reference: string;
  version: number;
  type_doc: string;
  titre: string;
  affaire_code: string | null;
  processus_code: string | null;
  fichier: string | null;
  motif_revision: string;
  date_revue: string | null;
  revue_echue: boolean;
  statut: "brouillon" | "approuve" | "obsolete";
  approuve_par_nom: string | null;
}
interface Constat {
  id: string;
  type_constat: string;
  exigence: string;
  description: string;
  nc_code: string | null;
  nc_statut: string | null;
}
interface Audit {
  id: string;
  code: string;
  type_audit: string;
  referentiel: string;
  perimetre: string;
  fournisseur_nom: string | null;
  agrement_jusqu: string | null;
  organisme: string;
  date_prevue: string;
  score: number | null;
  agrement_accorde: boolean | null;
  statut: "planifie" | "realise" | "cloture";
  constats: Constat[];
  nc_ouvertes: number;
}
interface Competence {
  employe: string;
  code: string;
  nom: string;
  a_renouveler: number;
  items: Array<{ origine: "soudage" | "rh"; code: string; intitule: string; date_validite: string | null; valide: boolean }>;
}
interface Revue {
  id: string;
  code: string;
  annee: number;
  statut: "brouillon" | "validee";
  participants: string;
  conclusions: string;
  decisions: string;
  validee_par_nom: string | null;
}
interface Bilan {
  audits_realises: number;
  audits_planifies: number;
  ecarts_audit: number;
  processus: number;
  processus_cible_atteinte: number;
  processus_mesures: number;
  documents_en_vigueur: number;
  documents_revue_echue: number;
  politique_en_vigueur: boolean;
}

const TYPES_DOC = ["politique", "manuel", "procedure", "instruction", "formulaire", "plan_qualite"];
const TYPES_AUDIT = ["interne", "externe", "certification", "fournisseur"];
const TYPES_CONSTAT = ["point_fort", "observation", "ecart_mineur", "ecart_majeur"];

function useListe<T>(key: string, path: string) {
  return useQuery({ queryKey: ["m6c", key], queryFn: () => api.listAll<T>(path), retry: 0 }).data ?? [];
}

/** Écarts M6-C : système de management de la qualité (ISO 9001) — CDC M6.2. */
export function SystemeQualiteSection() {
  const utilisateurs = useQuery({
    queryKey: ["m6c", "utilisateurs"],
    queryFn: () => api.get<Utilisateur[]>("/api/qualite/organisation/utilisateurs/"),
    retry: 0,
  }).data ?? [];
  const processus = useListe<Processus>("processus", "/api/qualite/processus/");
  const userOpts = utilisateurs.map((u) => ({ value: u.id, label: `${u.nom} · ${u.role}` }));
  const procOpts = processus.map((p) => ({ value: p.id, label: `${p.code} · ${p.libelle}` }));
  return (
    <>
      <DocumentsSection procOpts={procOpts} />
      <ProcessusSection processus={processus} userOpts={userOpts} procOpts={procOpts} />
      <AuditsSection procOpts={procOpts} />
      <CompetencesSection />
      <RevueSection />
    </>
  );
}

function DocumentsSection({ procOpts }: { procOpts: { value: string; label: string }[] }) {
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const docs = useListe<DocQualite>("documents", "/api/qualite/documents-qualite/");
  const affaires = useListe<{ id: string; code: string; label?: string; name?: string }>("affaires", "/api/commercial/affaires/");
  const [error, setError] = useState<string | null>(null);
  const joindre = useMutation({
    mutationFn: (v: { id: string; f: File }) => api.upload(`/api/qualite/documents-qualite/${v.id}/fichier/`, v.f),
    onSuccess: () => {
      setError(null);
      void qc.invalidateQueries({ queryKey: ["m6c", "documents"] });
    },
    onError: (e) => setError(describeError(e)),
  });
  const politique = docs.find((d) => d.type_doc === "politique" && d.statut === "approuve");
  return (
    <SectionCard title={`${t("m6c.docs.title")} · ${docs.length}`}>
      <div data-testid="liste-maitresse">
        <p className="muted">
          {politique ? t("m6c.docs.politique", { ref: `${politique.reference} v${politique.version}` }) : t("m6c.docs.sansPolitique")}
        </p>
        <QuickForm
          title={t("m6c.docs.nouveau")}
          endpoint="/api/qualite/documents-qualite/"
          fields={[
            { name: "type_doc", label: t("qualite.col.type"), type: "select", required: true, defaultValue: "procedure", options: TYPES_DOC.map((v) => ({ value: v, label: t(`m6c.typesDoc.${v}`) })) },
            { name: "titre", label: t("m6c.docs.titre"), required: true },
            { name: "processus", label: t("m6c.proc.processus"), type: "select", options: procOpts },
            { name: "affaire", label: t("m6c.docs.affaire"), type: "select", options: affaires.map((a) => ({ value: a.id, label: `${a.code} · ${a.label ?? a.name ?? ""}` })) },
            { name: "periodicite_revue_mois", label: t("m6c.docs.periodicite"), type: "number", min: 1, defaultValue: "36" },
          ]}
        />
        {error && <p className="action-error" role="alert">{error}</p>}
        {docs.length > 0 && (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>{t("m6c.docs.reference")}</th>
                  <th>{t("qualite.col.type")}</th>
                  <th>{t("m6c.docs.titre")}</th>
                  <th>{t("m6c.docs.revue")}</th>
                  <th>{t("qualite.col.statut")}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {docs.map((d) => (
                  <tr key={d.id}>
                    <td>
                      {d.reference} v{d.version}
                    </td>
                    <td>{t(`m6c.typesDoc.${d.type_doc}`)}</td>
                    <td>
                      {d.titre}
                      {(d.affaire_code || d.processus_code) && <span className="muted"> · {[d.affaire_code, d.processus_code].filter(Boolean).join(" · ")}</span>}
                      {d.fichier && <span className="muted"> · {t("m6e.wps.fiche")}</span>}
                    </td>
                    <td>
                      {d.date_revue ? formatDate(d.date_revue, i18n.language) : "—"} {d.revue_echue && <Badge tone="err">{t("m6c.docs.echue")}</Badge>}
                    </td>
                    <td>
                      <Badge tone={d.statut === "approuve" ? "ok" : d.statut === "obsolete" ? "err" : "brand"}>{t(`m6c.statutsDoc.${d.statut}`)}</Badge>
                    </td>
                    <td>
                      {d.statut === "brouillon" && (
                        <label className="btn ghost">
                          {t("m6e.wps.joindre")}
                          <input
                            type="file"
                            accept=".pdf,.docx,.xlsx,.doc,.xls"
                            hidden
                            onChange={(e) => {
                              const f = e.target.files?.[0];
                              if (f) joindre.mutate({ id: d.id, f });
                              e.target.value = "";
                            }}
                          />
                        </label>
                      )}
                      <ActionBar
                        actions={[
                          ...(d.statut === "brouillon"
                            ? [{ label: t("m6c.docs.approuver"), path: `/api/qualite/documents-qualite/${d.id}/approuver/`, confirm: t("m6c.docs.confirmApprouver") }]
                            : []),
                          ...(d.statut === "approuve"
                            ? [
                                { label: t("m6c.docs.reviser"), path: `/api/qualite/documents-qualite/${d.id}/reviser/`, tone: "ghost" as const, prompt: { name: "motif", label: t("m6c.docs.motif") } },
                                { label: t("m6e.wps.obsolete"), path: `/api/qualite/documents-qualite/${d.id}/obsolete/`, tone: "danger" as const, confirm: t("m6c.docs.confirmObsolete") },
                              ]
                            : []),
                        ]}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </SectionCard>
  );
}

function ProcessusSection({
  processus,
  userOpts,
  procOpts,
}: {
  processus: Processus[];
  userOpts: { value: string; label: string }[];
  procOpts: { value: string; label: string }[];
}) {
  const { t } = useTranslation();
  const organisation = useListe<Responsabilite>("organisation", "/api/qualite/organisation/");
  return (
    <SectionCard title={t("m6c.proc.title")}>
      <div data-testid="processus-qualite">
        <div className="action-bar-buttons">
          <QuickForm
            title={t("m6c.proc.nouveau")}
            endpoint="/api/qualite/processus/"
            fields={[
              { name: "libelle", label: t("m6c.proc.processus"), required: true },
              { name: "type_processus", label: t("qualite.col.type"), type: "select", required: true, defaultValue: "realisation", options: ["management", "realisation", "support"].map((v) => ({ value: v, label: t(`m6c.typesProc.${v}`) })) },
              { name: "pilote", label: t("m6c.proc.pilote"), type: "select", options: userOpts },
              { name: "finalite", label: t("m6c.proc.finalite"), type: "textarea" },
              { name: "indicateur", label: t("m6c.proc.indicateur") },
              { name: "unite", label: t("m6c.proc.unite") },
              { name: "cible", label: t("m6c.proc.cible"), type: "number", step: "0.01" },
              { name: "sens", label: t("m6c.proc.sens"), type: "select", defaultValue: "mini", options: ["mini", "maxi"].map((v) => ({ value: v, label: t(`m6c.sens.${v}`) })) },
            ]}
          />
          <QuickForm
            title={t("m6c.org.nouveau")}
            endpoint="/api/qualite/organisation/"
            fields={[
              { name: "fonction", label: t("m6c.org.fonction"), required: true },
              { name: "titulaire", label: t("m6c.org.titulaire"), type: "select", options: userOpts },
              { name: "suppleant", label: t("m6c.org.suppleant"), type: "select", options: userOpts },
              { name: "rattachement", label: t("m6c.org.rattachement") },
              { name: "missions", label: t("m6c.org.missions"), type: "textarea", required: true },
              { name: "autorites", label: t("m6c.org.autorites"), type: "textarea" },
              { name: "processus", label: t("m6c.proc.processus"), type: "select", options: procOpts },
            ]}
          />
        </div>
        {processus.length > 0 && (
          <table className="table">
            <thead>
              <tr>
                <th>{t("m6c.proc.processus")}</th>
                <th>{t("m6c.proc.pilote")}</th>
                <th>{t("m6c.proc.indicateur")}</th>
                <th className="num">{t("m6c.proc.cible")}</th>
                <th className="num">{t("m6c.proc.mesure")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {processus.map((p) => (
                <tr key={p.id}>
                  <td>
                    {p.code} · {p.libelle} <span className="muted">· {t(`m6c.typesProc.${p.type_processus}`)}</span>
                  </td>
                  <td>{p.pilote_nom ?? "—"}</td>
                  <td>{p.indicateur || "—"}</td>
                  <td className="num">
                    {p.cible === null ? "—" : `${p.sens === "mini" ? "≥" : "≤"} ${formatNumber(Number(p.cible))} ${p.unite}`}
                  </td>
                  <td className="num">
                    {p.valeur === null ? "—" : `${formatNumber(Number(p.valeur))} ${p.unite}`}{" "}
                    {p.cible_atteinte !== null && <Badge tone={p.cible_atteinte ? "ok" : "err"}>{p.cible_atteinte ? t("m6c.proc.atteinte") : t("m6c.proc.nonAtteinte")}</Badge>}
                  </td>
                  <td>
                    <ActionBar actions={[{ label: t("m6c.proc.mesurer"), path: `/api/qualite/processus/${p.id}/mesurer/`, tone: "ghost", prompt: { name: "valeur", label: t("m6c.proc.mesure") } }]} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {organisation.length > 0 && (
          <table className="table">
            <caption>{t("m6c.org.title")}</caption>
            <thead>
              <tr>
                <th>{t("m6c.org.fonction")}</th>
                <th>{t("m6c.org.titulaire")}</th>
                <th>{t("m6c.org.missions")}</th>
              </tr>
            </thead>
            <tbody>
              {organisation.map((o) => (
                <tr key={o.id}>
                  <td>
                    {o.fonction}
                    {o.rattachement && <span className="muted"> · {o.rattachement}</span>}
                  </td>
                  <td>
                    {o.titulaire_nom ?? "—"}
                    {o.suppleant_nom && <span className="muted"> · {t("m6c.org.suppleant")} {o.suppleant_nom}</span>}
                  </td>
                  <td>
                    {o.missions}
                    {o.processus_code && <span className="muted"> · {o.processus_code}</span>}
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

function AuditsSection({ procOpts }: { procOpts: { value: string; label: string }[] }) {
  const { t, i18n } = useTranslation();
  const audits = useListe<Audit>("audits", "/api/qualite/audits/");
  const fournisseurs = useListe<{ id: string; code: string; name: string; kind: string }>("fournisseurs", "/api/referentiels/partners/");
  const fourOpts = fournisseurs.filter((f) => f.kind === "fournisseur" || f.kind === "both").map((f) => ({ value: f.id, label: `${f.code} · ${f.name}` }));
  const ouverts = audits.filter((a) => a.statut !== "cloture").map((a) => ({ value: a.id, label: `${a.code} · ${a.perimetre}` }));
  return (
    <SectionCard title={`${t("m6c.audits.title")} · ${audits.length}`}>
      <div data-testid="audits-qualite">
        <div className="action-bar-buttons">
          <QuickForm
            title={t("m6c.audits.nouveau")}
            endpoint="/api/qualite/audits/"
            fields={[
              { name: "type_audit", label: t("qualite.col.type"), type: "select", required: true, defaultValue: "interne", options: TYPES_AUDIT.map((v) => ({ value: v, label: t(`m6c.typesAudit.${v}`) })) },
              { name: "perimetre", label: t("m6c.audits.perimetre"), required: true },
              { name: "referentiel", label: t("m6c.audits.referentiel"), defaultValue: "ISO 9001:2015" },
              { name: "processus", label: t("m6c.proc.processus"), type: "select", options: procOpts },
              { name: "fournisseur", label: t("m6c.audits.fournisseur"), type: "select", options: fourOpts },
              { name: "organisme", label: t("m6c.audits.organisme") },
              { name: "auditeur", label: t("m6c.audits.auditeur") },
              { name: "date_prevue", label: t("m6e.f.datePrevue"), type: "date" },
            ]}
          />
          <QuickForm
            title={t("m6c.audits.constat")}
            endpoint="/api/qualite/constats-audit/"
            fields={[
              { name: "audit", label: t("m6c.audits.audit"), type: "select", required: true, options: ouverts },
              { name: "type_constat", label: t("qualite.col.type"), type: "select", required: true, defaultValue: "observation", options: TYPES_CONSTAT.map((v) => ({ value: v, label: t(`m6c.typesConstat.${v}`) })) },
              { name: "exigence", label: t("m6c.audits.exigence") },
              { name: "description", label: t("qualite.form.description"), type: "textarea", required: true },
            ]}
          />
        </div>
        {audits.length > 0 && (
          <table className="table">
            <thead>
              <tr>
                <th>{t("qualite.col.code")}</th>
                <th>{t("m6c.audits.perimetre")}</th>
                <th>{t("m6e.f.datePrevue")}</th>
                <th>{t("m6c.audits.constats")}</th>
                <th>{t("qualite.col.statut")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {audits.map((a) => (
                <tr key={a.id}>
                  <td>
                    {a.code} <span className="muted">· {t(`m6c.typesAudit.${a.type_audit}`)}</span>
                  </td>
                  <td>
                    {a.perimetre}
                    <span className="muted"> · {[a.referentiel, a.fournisseur_nom, a.organisme].filter(Boolean).join(" · ")}</span>
                  </td>
                  <td>{formatDate(a.date_prevue, i18n.language)}</td>
                  <td>
                    {a.constats.map((c) => (
                      <div key={c.id} className="meta">
                        <Badge tone={c.type_constat === "ecart_majeur" ? "err" : c.type_constat === "ecart_mineur" ? "warn" : c.type_constat === "point_fort" ? "ok" : "brand"}>
                          {t(`m6c.typesConstat.${c.type_constat}`)}
                        </Badge>{" "}
                        {c.exigence && `${c.exigence} · `}
                        {c.description}
                        {c.nc_code && <span className="muted"> · {c.nc_code}</span>}
                      </div>
                    ))}
                    {a.nc_ouvertes > 0 && <Badge tone="warn">{t("m6c.audits.ncOuvertes", { count: a.nc_ouvertes })}</Badge>}
                  </td>
                  <td>
                    <Badge tone={a.statut === "cloture" ? "ok" : a.statut === "realise" ? "warn" : "brand"}>{t(`m6c.statutsAudit.${a.statut}`)}</Badge>
                    {a.score !== null && <span className="muted"> · {a.score} %</span>}
                    {a.agrement_accorde !== null && (
                      <div>
                        <Badge tone={a.agrement_accorde ? "ok" : "err"}>
                          {a.agrement_accorde ? t("m6c.audits.agree", { date: a.agrement_jusqu ? formatDate(a.agrement_jusqu, i18n.language) : "—" }) : t("m6c.audits.nonAgree")}
                        </Badge>
                      </div>
                    )}
                  </td>
                  <td>
                    <ActionBar
                      actions={[
                        ...(a.statut === "planifie"
                          ? [{ label: t("m6c.audits.realiser"), path: `/api/qualite/audits/${a.id}/realiser/`, prompt: { name: "score", label: t("m6c.audits.score") } }]
                          : []),
                        ...(a.statut === "realise"
                          ? [{ label: t("actions.cloturer"), path: `/api/qualite/audits/${a.id}/cloturer/`, confirm: t("m6c.audits.confirmCloturer") }]
                          : []),
                      ]}
                    />
                    <button type="button" className="btn ghost" onClick={() => void api.download(`/api/qualite/audits/${a.id}/rapport/`, `rapport-${a.code}.pdf`)}>
                      {t("m6c.audits.rapport")}
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

function CompetencesSection() {
  const { t, i18n } = useTranslation();
  const q = useQuery({ queryKey: ["m6c", "competences"], queryFn: () => api.get<Competence[]>("/api/qualite/competences/"), retry: 0 });
  const rows = q.data ?? [];
  return (
    <SectionCard title={`${t("m6c.comp.title")} · ${rows.length}`}>
      <div data-testid="competences-qualite">
        {rows.length === 0 ? (
          <p className="muted">{t("m6c.comp.vide")}</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>{t("m6c.comp.salarie")}</th>
                <th>{t("m6c.comp.qualifications")}</th>
                <th>{t("qualite.col.statut")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.employe}>
                  <td>
                    {r.code} · {r.nom}
                  </td>
                  <td>
                    {r.items.map((i) => (
                      <div key={`${i.origine}-${i.code}`} className="meta">
                        <Badge tone={i.valide ? "ok" : "err"}>{t(`m6c.comp.${i.origine}`)}</Badge> {i.intitule}
                        <span className="muted"> · {i.date_validite ? formatDate(i.date_validite, i18n.language) : "—"}</span>
                      </div>
                    ))}
                  </td>
                  <td>
                    <Badge tone={r.a_renouveler > 0 ? "warn" : "ok"}>{r.a_renouveler > 0 ? t("m6c.comp.aRenouveler", { count: r.a_renouveler }) : t("m6c.comp.ajour")}</Badge>
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

function RevueSection() {
  const { t } = useTranslation();
  const annee = new Date().getFullYear();
  const bilan = useQuery({ queryKey: ["m6c", "bilan", annee], queryFn: () => api.get<Bilan>(`/api/qualite/revues-direction/bilan/?annee=${annee}`), retry: 0 }).data;
  const revues = useListe<Revue>("revues", "/api/qualite/revues-direction/");
  return (
    <SectionCard title={t("m6c.revue.title")}>
      <div data-testid="revue-qualite">
        {bilan && (
          <div className="kpi-grid">
            <Kpi label={t("m6c.revue.audits")} value={`${bilan.audits_realises} / ${bilan.audits_planifies}`} hint={`${t("m6c.revue.ecarts")} · ${bilan.ecarts_audit}`} tone="brand" delay={0} />
            <Kpi label={t("m6c.revue.processus")} value={`${bilan.processus_cible_atteinte} / ${bilan.processus_mesures}`} hint={`${t("m6c.revue.actifs")} · ${bilan.processus}`} tone="ok" delay={0.05} />
            <Kpi label={t("m6c.revue.documents")} value={bilan.documents_en_vigueur} hint={`${t("m6c.docs.echue")} · ${bilan.documents_revue_echue}`} tone={bilan.documents_revue_echue > 0 ? "warn" : "ok"} delay={0.1} />
          </div>
        )}
        <button type="button" className="btn ghost" onClick={() => void api.download(`/api/qualite/revues-direction/bilan/?annee=${annee}&export=pdf`, `bilan-qualite-${annee}.pdf`)}>
          {t("m6c.revue.bilanPdf")}
        </button>
        <QuickForm
          title={t("m6c.revue.nouvelle")}
          endpoint="/api/qualite/revues-direction/"
          fields={[
            { name: "annee", label: t("m6c.revue.annee"), type: "number", required: true, defaultValue: String(annee) },
            { name: "participants", label: t("m6c.revue.participants"), type: "textarea" },
            { name: "conclusions", label: t("m6c.revue.conclusions"), type: "textarea" },
            { name: "decisions", label: t("m6c.revue.decisions"), type: "textarea" },
          ]}
        />
        {revues.length > 0 && (
          <table className="table">
            <tbody>
              {revues.map((r) => (
                <tr key={r.id}>
                  <td>
                    {r.code} · {r.annee}
                  </td>
                  <td>{r.conclusions || "—"}</td>
                  <td>
                    <Badge tone={r.statut === "validee" ? "ok" : "brand"}>{t(`m6c.revue.statuts.${r.statut}`)}</Badge>
                    {r.validee_par_nom && <span className="muted"> · {r.validee_par_nom}</span>}
                  </td>
                  <td>
                    {r.statut === "brouillon" && (
                      <ActionBar
                        actions={[
                          { label: t("m6c.revue.actualiser"), path: `/api/qualite/revues-direction/${r.id}/actualiser/`, tone: "ghost" },
                          { label: t("actions.valider"), path: `/api/qualite/revues-direction/${r.id}/valider/`, confirm: t("m6c.revue.confirmValider") },
                        ]}
                      />
                    )}
                    <button type="button" className="btn ghost" onClick={() => void api.download(`/api/qualite/revues-direction/${r.id}/pdf/`, `${r.code}.pdf`)}>
                      PDF
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
