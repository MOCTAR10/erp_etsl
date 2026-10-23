import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate, formatMoney, formatPercent } from "../../lib/format";
import { SectionActions } from "../sections/SectionActions";
import { ActionBar, Badge, DataTable, QuickForm, SectionCard } from "../ui";
import type { Column } from "../ui";

interface Catalogue {
  id: string;
  code: string;
  intitule: string;
  organisme: string;
  duree_heures: string;
  cout_session: string;
  qualification_type: string;
  qualification_type_label: string;
  validite_mois: number | null;
}
interface Synthese {
  budget: string;
  engage: string;
  realise: string;
  reste: string;
  sessions: number;
  sessions_realisees: number;
  taux_realisation_pct: string | null;
  heures_stagiaires: string;
  cout_heure_stagiaire: string | null;
  roi_pct: string | null;
}
interface Plan {
  id: string;
  annee: number;
  budget: string;
  synthese: Synthese;
}
interface Session {
  id: string;
  code: string;
  theme: string;
  date_session: string;
  type: string;
  type_label: string;
  plan_annee: number | null;
  nb_participants: number;
  cout_prevu: string;
  cout_reel: string | null;
  roi_pct: string | null;
  nb_qualifications_delivrees: number;
}
interface Habilitation {
  id: string;
  poste: string;
  poste_label: string;
  mot_cle: string;
}
interface Employe {
  id: string;
  code: string;
  nom_complet?: string;
  nom: string;
  prenom?: string;
}

const POSTES = ["decoupe", "tuyauterie", "soudure", "chaudronnerie", "structure", "montage", "controle"];
const TYPES_QUALIF = ["habilitation", "permis", "certificat", "diplome"];


/** Écarts M9-C : catalogue et plan de formation (budget, coût, ROI), qualifications, matrice habilitation ↔ poste. */
export function EcartsM9cSection() {
  const { t } = useTranslation();
  const catalogue = useQuery({ queryKey: ["m9c", "catalogue"], queryFn: () => api.listAll<Catalogue>("/api/rh-paie/catalogue-formations/"), retry: 0 }).data ?? [];
  const plans = useQuery({ queryKey: ["m9c", "plans"], queryFn: () => api.listAll<Plan>("/api/rh-paie/plans-formation/"), retry: 0 }).data ?? [];
  const sessions = useQuery({ queryKey: ["m9c", "sessions"], queryFn: () => api.listAll<Session>("/api/rh-paie/formations/"), retry: 0 }).data ?? [];
  const matrice = useQuery({ queryKey: ["m9c", "matrice"], queryFn: () => api.listAll<Habilitation>("/api/rh-paie/habilitations-postes/"), retry: 0 }).data ?? [];
  const employes = useQuery({ queryKey: ["m9c", "employes"], queryFn: () => api.listAll<Employe>("/api/rh-paie/employes/"), retry: 0 }).data ?? [];
  const empOpts = employes.map((e) => ({ value: e.id, label: `${e.code} · ${e.nom_complet ?? `${e.nom} ${e.prenom ?? ""}`}` }));
  const typeOpts = TYPES_QUALIF.map((v) => ({ value: v, label: t(`m9c.typesQualif.${v}`) }));

  const colPlans: Column<Plan>[] = [
    { key: "annee", header: t("m9c.plan.annee"), sortValue: (p) => p.annee, render: (p) => p.annee },
    { key: "budget", header: t("m9c.plan.budget"), num: true, render: (p) => formatMoney(p.synthese.budget) },
    { key: "engage", header: t("m9c.plan.engage"), num: true, render: (p) => formatMoney(p.synthese.engage) },
    { key: "realise", header: t("m9c.plan.realise"), num: true, render: (p) => formatMoney(p.synthese.realise) },
    {
      key: "reste",
      header: t("m9c.plan.reste"),
      num: true,
      render: (p) => (
        <>
          {Number(p.synthese.reste) < 0 && <Badge tone="err">{t("m9c.plan.depasse")}</Badge>} {formatMoney(p.synthese.reste)}
        </>
      ),
    },
    {
      key: "sessions",
      header: t("m9c.plan.sessions"),
      num: true,
      render: (p) =>
        `${p.synthese.sessions_realisees} / ${p.synthese.sessions}${p.synthese.taux_realisation_pct !== null ? ` (${formatPercent(p.synthese.taux_realisation_pct)})` : ""}`,
    },
    { key: "coutHeure", header: t("m9c.plan.coutHeure"), num: true, render: (p) => formatMoney(p.synthese.cout_heure_stagiaire) },
    { key: "roi", header: t("m9c.plan.roi"), num: true, render: (p) => formatPercent(p.synthese.roi_pct) },
  ];
  const colSessions: Column<Session>[] = [
    {
      key: "theme",
      header: t("m9c.session.theme"),
      sortValue: (s) => s.code,
      render: (s) => (
        <>
          {s.code} · {s.theme} <Badge tone={s.type === "realisee" ? "ok" : s.type === "annulee" ? "err" : "warn"}>{s.type_label}</Badge>
        </>
      ),
    },
    { key: "date", header: t("m9c.session.date"), sortValue: (s) => s.date_session, render: (s) => formatDate(s.date_session) },
    { key: "plan", header: t("m9c.session.plan"), render: (s) => s.plan_annee ?? "—" },
    {
      key: "participants",
      header: t("m9c.session.participants"),
      num: true,
      render: (s) => (
        <>
          {s.nb_qualifications_delivrees > 0 && <Badge tone="ok">{t("m9c.session.qualifsDelivrees", { n: s.nb_qualifications_delivrees })}</Badge>} {s.nb_participants}
        </>
      ),
    },
    { key: "cout", header: t("m9c.session.cout"), num: true, render: (s) => formatMoney(s.type === "realisee" ? s.cout_reel : s.cout_prevu) },
    { key: "roi", header: t("m9c.plan.roi"), num: true, render: (s) => formatPercent(s.roi_pct) },
    {
      key: "actions",
      header: <span className="sr-only">{t("ui.actions")}</span>,
      render: (s) =>
        s.type === "planifie" ? (
          <ActionBar
            actions={[
              { label: t("m9c.session.realiser"), path: `/api/rh-paie/formations/${s.id}/realiser/`, prompt: { name: "cout_reel", label: t("m9c.session.coutReel") } },
              { label: t("m9c.session.inscrire"), path: `/api/rh-paie/formations/${s.id}/inscrire/`, tone: "ghost" as const, prompt: { name: "employe", label: t("m9c.session.salarie"), options: empOpts } },
            ]}
          />
        ) : null,
    },
  ];
  const colMatrice: Column<Habilitation>[] = [
    { key: "poste", header: t("m9c.habilitations.poste"), sortValue: (h) => h.poste_label, render: (h) => h.poste_label },
    { key: "motCle", header: t("m9c.habilitations.motCle"), render: (h) => h.mot_cle },
  ];

  return (
    <>
      <SectionCard
        title={t("m9c.plan.title")}
        actions={
          <SectionActions>
            <QuickForm
              title={t("m9c.session.ajouter")}
              endpoint="/api/rh-paie/formations/"
              fields={[
                { name: "catalogue", label: t("m9c.session.catalogue"), type: "select", options: catalogue.map((c) => ({ value: c.id, label: `${c.code} · ${c.intitule}` })) },
                { name: "theme", label: t("m9c.session.theme") },
                { name: "plan", label: t("m9c.session.plan"), type: "select", options: plans.map((p) => ({ value: p.id, label: String(p.annee) })) },
                { name: "date_session", label: t("m9c.session.date"), type: "date", required: true },
                { name: "cout_prevu", label: t("m9c.session.coutPrevu"), type: "number", min: 0 },
              ]}
            />
            <QuickForm
              title={t("m9c.plan.ajouter")}
              endpoint="/api/rh-paie/plans-formation/"
              fields={[
                { name: "annee", label: t("m9c.plan.annee"), type: "number", required: true, defaultValue: String(new Date().getFullYear()) },
                { name: "budget", label: t("m9c.plan.budget"), type: "number", min: 0, required: true },
                { name: "objectifs", label: t("m9c.plan.objectifs"), type: "textarea" },
              ]}
            />
            <QuickForm
              title={t("m9c.catalogue.ajouter")}
              endpoint="/api/rh-paie/catalogue-formations/"
              fields={[
                { name: "intitule", label: t("m9c.catalogue.intitule"), required: true },
                { name: "organisme", label: t("m9c.catalogue.organisme") },
                { name: "duree_heures", label: t("m9c.catalogue.duree"), type: "number", min: 0, step: "0.5" },
                { name: "cout_session", label: t("m9c.catalogue.cout"), type: "number", min: 0 },
                { name: "qualification_type", label: t("m9c.catalogue.qualif"), type: "select", options: typeOpts },
                { name: "validite_mois", label: t("m9c.catalogue.validite"), type: "number", min: 1 },
              ]}
            />
          </SectionActions>
        }
      >
        <div data-testid="plans-formation">
          <DataTable columns={colPlans} rows={plans} caption={t("m9c.plan.title")} />
        </div>
        <p className="muted">{t("m9c.plan.note")}</p>
        <div data-testid="sessions-formation">
          <DataTable columns={colSessions} rows={sessions} caption={t("tableaux.rhpaie.sessions")} />
        </div>
      </SectionCard>

      <SectionCard
        title={t("m9c.habilitations.title")}
        actions={
          <SectionActions>
            <QuickForm
              title={t("m9c.qualification.ajouter")}
              endpoint="/api/rh-paie/qualifications/"
              fields={[
                { name: "employe", label: t("m9c.session.salarie"), type: "select", required: true, options: empOpts },
                { name: "type", label: t("m9c.catalogue.qualif"), type: "select", required: true, defaultValue: "habilitation", options: typeOpts },
                { name: "intitule", label: t("m9c.catalogue.intitule"), required: true },
                { name: "organisme", label: t("m9c.catalogue.organisme") },
                { name: "date_obtention", label: t("m9c.qualification.obtention"), type: "date" },
                { name: "date_validite", label: t("m9c.qualification.validite"), type: "date" },
              ]}
            />
            <QuickForm
              title={t("m9c.habilitations.ajouter")}
              endpoint="/api/rh-paie/habilitations-postes/"
              fields={[
                { name: "poste", label: t("m9c.habilitations.poste"), type: "select", required: true, options: POSTES.map((p) => ({ value: p, label: t(`m9c.postes.${p}`) })) },
                { name: "mot_cle", label: t("m9c.habilitations.motCle"), required: true },
              ]}
            />
          </SectionActions>
        }
      >
        <div data-testid="matrice-habilitations">
          <DataTable columns={colMatrice} rows={matrice} caption={t("m9c.habilitations.title")} />
        </div>
        <p className="muted">{t("m9c.habilitations.note")}</p>
      </SectionCard>
    </>
  );
}
