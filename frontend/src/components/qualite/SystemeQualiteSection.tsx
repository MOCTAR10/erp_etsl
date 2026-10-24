import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { FileDown } from "lucide-react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate, formatNumber } from "../../lib/format";
import { displayName } from "../../lib/people";
import { describeError } from "../../lib/offlineQueue";
import { roleLabel } from "../../lib/roles";
import { SectionActions } from "../sections/SectionActions";
import { ActionBar, Badge, DataTable, Kpi, QuickForm, SectionCard } from "../ui";
import type { Column } from "../ui";

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

/** Écarts M6-C : système de management de la qualité (ISO 9001). */
export function SystemeQualiteSection() {
  const { t } = useTranslation();
  const utilisateurs = useQuery({
    queryKey: ["m6c", "utilisateurs"],
    queryFn: () => api.get<Utilisateur[]>("/api/qualite/organisation/utilisateurs/"),
    retry: 0,
  }).data ?? [];
  const processus = useListe<Processus>("processus", "/api/qualite/processus/");
  const userOpts = utilisateurs.map((u) => ({ value: u.id, label: `${u.nom} · ${roleLabel(t, u.role)}` }));
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

/** Enveloppe sans boîte : porte le data-testid d'une section (création + tableau) sans changer la mise en page. */
const CONTENTS = { display: "contents" } as const;

/** Valeur d'indicateur : décimales conservées (« 0,5 »), entiers sans virgule. */
const nombre = (v: string) => formatNumber(v, { decimals: Number.isInteger(Number(v)) ? 0 : 2 });

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
  const cols: Column<DocQualite>[] = [
    { key: "reference", header: t("m6c.docs.reference"), render: (d) => `${d.reference} v${d.version}`, sortValue: (d) => d.reference },
    { key: "type", header: t("qualite.col.type"), render: (d) => t(`m6c.typesDoc.${d.type_doc}`), sortValue: (d) => d.type_doc },
    {
      key: "titre",
      header: t("m6c.docs.titre"),
      render: (d) => (
        <>
          {d.titre}
          {(d.affaire_code || d.processus_code) && <span className="muted"> · {[d.affaire_code, d.processus_code].filter(Boolean).join(" · ")}</span>}
          {d.fichier && <span className="muted"> · {t("m6e.wps.fiche")}</span>}
        </>
      ),
      sortValue: (d) => d.titre,
    },
    {
      key: "revue",
      header: t("m6c.docs.revue"),
      render: (d) => (
        <>
          {d.date_revue ? formatDate(d.date_revue, i18n.language) : "—"} {d.revue_echue && <Badge tone="err">{t("m6c.docs.echue")}</Badge>}
        </>
      ),
      sortValue: (d) => d.date_revue,
    },
    {
      key: "statut",
      header: t("qualite.col.statut"),
      render: (d) => <Badge tone={d.statut === "approuve" ? "ok" : d.statut === "obsolete" ? "err" : "brand"}>{t(`m6c.statutsDoc.${d.statut}`)}</Badge>,
      sortValue: (d) => d.statut,
    },
    {
      key: "actions",
      header: <span className="sr-only">{t("ui.actions")}</span>,
      render: (d) => (
        <div className="action-bar-buttons">
          {d.statut === "brouillon" && (
            <label className="btn ghost sm">
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
        </div>
      ),
    },
  ];
  return (
    <div data-testid="liste-maitresse" style={CONTENTS}>
      <SectionCard
        title={`${t("m6c.docs.title")} · ${docs.length}`}
        subtitle={politique ? t("m6c.docs.politique", { ref: `${politique.reference} v${politique.version}` }) : t("m6c.docs.sansPolitique")}
        actions={
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
        }
      >
        {error && <p className="action-error" role="alert">{error}</p>}
        <DataTable columns={cols} rows={docs} caption={t("m6c.docs.title")} />
      </SectionCard>
    </div>
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
  const procCols: Column<Processus>[] = [
    {
      key: "processus",
      header: t("m6c.proc.processus"),
      render: (p) => (
        <>
          {p.code} · {p.libelle} <span className="muted">· {t(`m6c.typesProc.${p.type_processus}`)}</span>
        </>
      ),
      sortValue: (p) => p.code,
    },
    { key: "pilote", header: t("m6c.proc.pilote"), render: (p) => displayName(p.pilote_nom), sortValue: (p) => p.pilote_nom },
    { key: "indicateur", header: t("m6c.proc.indicateur"), render: (p) => p.indicateur || "—" },
    {
      key: "cible",
      header: t("m6c.proc.cible"),
      num: true,
      render: (p) => (p.cible === null ? "—" : `${p.sens === "mini" ? "≥" : "≤"} ${nombre(p.cible)} ${p.unite}`),
    },
    {
      key: "mesure",
      header: t("m6c.proc.mesure"),
      num: true,
      render: (p) => (
        <>
          {p.valeur === null ? "—" : `${nombre(p.valeur)} ${p.unite}`}{" "}
          {p.cible_atteinte !== null && <Badge tone={p.cible_atteinte ? "ok" : "err"}>{p.cible_atteinte ? t("m6c.proc.atteinte") : t("m6c.proc.nonAtteinte")}</Badge>}
        </>
      ),
    },
    {
      key: "actions",
      header: <span className="sr-only">{t("ui.actions")}</span>,
      render: (p) => <ActionBar actions={[{ label: t("m6c.proc.mesurer"), path: `/api/qualite/processus/${p.id}/mesurer/`, tone: "ghost", prompt: { name: "valeur", label: t("m6c.proc.mesure") } }]} />,
    },
  ];
  const orgCols: Column<Responsabilite>[] = [
    {
      key: "fonction",
      header: t("m6c.org.fonction"),
      render: (o) => (
        <>
          {o.fonction}
          {o.rattachement && <span className="muted"> · {o.rattachement}</span>}
        </>
      ),
      sortValue: (o) => o.fonction,
    },
    {
      key: "titulaire",
      header: t("m6c.org.titulaire"),
      render: (o) => (
        <>
          {o.titulaire_nom ?? "—"}
          {o.suppleant_nom && <span className="muted"> · {t("m6c.org.suppleant")} {o.suppleant_nom}</span>}
        </>
      ),
    },
    {
      key: "missions",
      header: t("m6c.org.missions"),
      render: (o) => (
        <>
          {o.missions}
          {o.processus_code && <span className="muted"> · {o.processus_code}</span>}
        </>
      ),
    },
  ];
  return (
    <div data-testid="processus-qualite" style={CONTENTS}>
      <SectionCard
        title={t("m6c.proc.title")}
        actions={
          <SectionActions>
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
          </SectionActions>
        }
      >
        <DataTable columns={procCols} rows={processus} caption={t("m6c.proc.title")} />
        {organisation.length > 0 && (
          <>
            <h4 className="card-sub" style={{ margin: "var(--space-5) 0 var(--space-2)" }}>
              {t("m6c.org.title")}
            </h4>
            <DataTable columns={orgCols} rows={organisation} caption={t("m6c.org.title")} />
          </>
        )}
      </SectionCard>
    </div>
  );
}

function AuditsSection({ procOpts }: { procOpts: { value: string; label: string }[] }) {
  const { t, i18n } = useTranslation();
  const audits = useListe<Audit>("audits", "/api/qualite/audits/");
  const fournisseurs = useListe<{ id: string; code: string; name: string; kind: string }>("fournisseurs", "/api/referentiels/partners/");
  const fourOpts = fournisseurs.filter((f) => f.kind === "fournisseur" || f.kind === "both").map((f) => ({ value: f.id, label: `${f.code} · ${f.name}` }));
  const ouverts = audits.filter((a) => a.statut !== "cloture").map((a) => ({ value: a.id, label: `${a.code} · ${a.perimetre}` }));
  const cols: Column<Audit>[] = [
    {
      key: "code",
      header: t("qualite.col.code"),
      render: (a) => (
        <>
          {a.code} <span className="muted">· {t(`m6c.typesAudit.${a.type_audit}`)}</span>
        </>
      ),
      sortValue: (a) => a.code,
    },
    {
      key: "perimetre",
      header: t("m6c.audits.perimetre"),
      render: (a) => (
        <>
          {a.perimetre}
          <span className="muted"> · {[a.referentiel, a.fournisseur_nom, a.organisme].filter(Boolean).join(" · ")}</span>
        </>
      ),
    },
    { key: "date", header: t("m6e.f.datePrevue"), render: (a) => formatDate(a.date_prevue, i18n.language), sortValue: (a) => a.date_prevue },
    {
      key: "constats",
      header: t("m6c.audits.constats"),
      render: (a) => (
        <>
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
        </>
      ),
    },
    {
      key: "statut",
      header: t("qualite.col.statut"),
      render: (a) => (
        <>
          <Badge tone={a.statut === "cloture" ? "ok" : a.statut === "realise" ? "warn" : "brand"}>{t(`m6c.statutsAudit.${a.statut}`)}</Badge>
          {a.score !== null && <span className="muted"> · {formatNumber(a.score)} %</span>}
          {a.agrement_accorde !== null && (
            <div>
              <Badge tone={a.agrement_accorde ? "ok" : "err"}>
                {a.agrement_accorde ? t("m6c.audits.agree", { date: a.agrement_jusqu ? formatDate(a.agrement_jusqu, i18n.language) : "—" }) : t("m6c.audits.nonAgree")}
              </Badge>
            </div>
          )}
        </>
      ),
      sortValue: (a) => a.statut,
    },
    {
      key: "actions",
      header: <span className="sr-only">{t("ui.actions")}</span>,
      render: (a) => (
        <div className="action-bar-buttons">
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
          <button type="button" className="btn ghost sm" onClick={() => void api.download(`/api/qualite/audits/${a.id}/rapport/`, `rapport-${a.code}.pdf`)}>
            <FileDown size={14} aria-hidden="true" /> {t("m6c.audits.rapport")}
          </button>
        </div>
      ),
    },
  ];
  return (
    <div data-testid="audits-qualite" style={CONTENTS}>
      <SectionCard
        title={`${t("m6c.audits.title")} · ${audits.length}`}
        actions={
          <SectionActions>
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
          </SectionActions>
        }
      >
        <DataTable columns={cols} rows={audits} caption={t("m6c.audits.title")} />
      </SectionCard>
    </div>
  );
}

function CompetencesSection() {
  const { t, i18n } = useTranslation();
  const q = useQuery({ queryKey: ["m6c", "competences"], queryFn: () => api.get<Competence[]>("/api/qualite/competences/"), retry: 0 });
  const rows = (q.data ?? []).map((r) => ({ ...r, id: r.employe }));
  const cols: Column<Competence & { id: string }>[] = [
    { key: "salarie", header: t("m6c.comp.salarie"), render: (r) => `${r.code} · ${r.nom}`, sortValue: (r) => r.nom },
    {
      key: "qualifications",
      header: t("m6c.comp.qualifications"),
      render: (r) =>
        r.items.map((i) => (
          <div key={`${i.origine}-${i.code}`} className="meta">
            <Badge tone={i.valide ? "ok" : "err"}>{t(`m6c.comp.${i.origine}`)}</Badge> {i.intitule}
            <span className="muted"> · {i.date_validite ? formatDate(i.date_validite, i18n.language) : "—"}</span>
          </div>
        )),
    },
    {
      key: "statut",
      header: t("qualite.col.statut"),
      render: (r) => <Badge tone={r.a_renouveler > 0 ? "warn" : "ok"}>{r.a_renouveler > 0 ? t("m6c.comp.aRenouveler", { count: r.a_renouveler }) : t("m6c.comp.ajour")}</Badge>,
      sortValue: (r) => r.a_renouveler,
    },
  ];
  return (
    <SectionCard title={`${t("m6c.comp.title")} · ${rows.length}`}>
      <div data-testid="competences-qualite">
        <DataTable columns={cols} rows={rows} caption={t("m6c.comp.title")} loading={q.isLoading} emptyLabel={t("m6c.comp.vide")} />
      </div>
    </SectionCard>
  );
}

function RevueSection() {
  const { t } = useTranslation();
  const annee = new Date().getFullYear();
  const bilan = useQuery({ queryKey: ["m6c", "bilan", annee], queryFn: () => api.get<Bilan>(`/api/qualite/revues-direction/bilan/?annee=${annee}`), retry: 0 }).data;
  const revues = useListe<Revue>("revues", "/api/qualite/revues-direction/");
  const cols: Column<Revue>[] = [
    { key: "code", header: t("qualite.col.code"), render: (r) => `${r.code} · ${r.annee}`, sortValue: (r) => r.annee },
    { key: "conclusions", header: t("m6c.revue.conclusions"), render: (r) => r.conclusions || "—" },
    {
      key: "statut",
      header: t("qualite.col.statut"),
      render: (r) => (
        <>
          <Badge tone={r.statut === "validee" ? "ok" : "brand"}>{t(`m6c.revue.statuts.${r.statut}`)}</Badge>
          {r.validee_par_nom && <span className="muted"> · {r.validee_par_nom}</span>}
        </>
      ),
    },
    {
      key: "actions",
      header: <span className="sr-only">{t("ui.actions")}</span>,
      render: (r) => (
        <div className="action-bar-buttons">
          {r.statut === "brouillon" && (
            <ActionBar
              actions={[
                { label: t("m6c.revue.actualiser"), path: `/api/qualite/revues-direction/${r.id}/actualiser/`, tone: "ghost" },
                { label: t("actions.valider"), path: `/api/qualite/revues-direction/${r.id}/valider/`, confirm: t("m6c.revue.confirmValider") },
              ]}
            />
          )}
          <button type="button" className="btn ghost sm" onClick={() => void api.download(`/api/qualite/revues-direction/${r.id}/pdf/`, `${r.code}.pdf`)}>
            <FileDown size={14} aria-hidden="true" /> PDF
          </button>
        </div>
      ),
    },
  ];
  return (
    <div data-testid="revue-qualite" style={CONTENTS}>
      <SectionCard
        title={t("m6c.revue.title")}
        actions={
          <SectionActions>
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
            <button type="button" className="btn ghost" onClick={() => void api.download(`/api/qualite/revues-direction/bilan/?annee=${annee}&export=pdf`, `bilan-qualite-${annee}.pdf`)}>
              <FileDown size={14} aria-hidden="true" /> {t("m6c.revue.bilanPdf")}
            </button>
          </SectionActions>
        }
      >
        {bilan && (
          <div className="kpi-grid">
            <Kpi label={t("m6c.revue.audits")} value={`${bilan.audits_realises} / ${bilan.audits_planifies}`} hint={`${t("m6c.revue.ecarts")} · ${bilan.ecarts_audit}`} tone="brand" delay={0} />
            <Kpi label={t("m6c.revue.processus")} value={`${bilan.processus_cible_atteinte} / ${bilan.processus_mesures}`} hint={`${t("m6c.revue.actifs")} · ${bilan.processus}`} tone="ok" delay={0.05} />
            <Kpi label={t("m6c.revue.documents")} value={bilan.documents_en_vigueur} hint={`${t("m6c.docs.echue")} · ${bilan.documents_revue_echue}`} tone={bilan.documents_revue_echue > 0 ? "warn" : "ok"} delay={0.1} />
          </div>
        )}
        <DataTable columns={cols} rows={revues} caption={t("m6c.revue.title")} />
      </SectionCard>
    </div>
  );
}
