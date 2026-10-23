import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate, formatMoney, formatNumber } from "../../lib/format";
import { ActionBar, Badge, QuickForm, SectionCard } from "../ui";

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
const fcfa = (v: string | null) => (v === null ? "—" : formatMoney(Number(v)));

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

  return (
    <>
      <SectionCard title={t("m9c.plan.title")}>
        <div className="action-bar-buttons">
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
        </div>
        <table className="table" data-testid="plans-formation">
          <thead>
            <tr>
              <th>{t("m9c.plan.annee")}</th>
              <th>{t("m9c.plan.budget")}</th>
              <th>{t("m9c.plan.engage")}</th>
              <th>{t("m9c.plan.realise")}</th>
              <th>{t("m9c.plan.reste")}</th>
              <th>{t("m9c.plan.sessions")}</th>
              <th>{t("m9c.plan.coutHeure")}</th>
              <th>{t("m9c.plan.roi")}</th>
            </tr>
          </thead>
          <tbody>
            {plans.map((p) => (
              <tr key={p.id}>
                <td>{p.annee}</td>
                <td>{fcfa(p.synthese.budget)}</td>
                <td>{fcfa(p.synthese.engage)}</td>
                <td>{fcfa(p.synthese.realise)}</td>
                <td>
                  {fcfa(p.synthese.reste)} {Number(p.synthese.reste) < 0 && <Badge tone="err">{t("m9c.plan.depasse")}</Badge>}
                </td>
                <td>
                  {p.synthese.sessions_realisees} / {p.synthese.sessions}
                  {p.synthese.taux_realisation_pct !== null ? ` (${formatNumber(Number(p.synthese.taux_realisation_pct))} %)` : ""}
                </td>
                <td>{fcfa(p.synthese.cout_heure_stagiaire)}</td>
                <td>{p.synthese.roi_pct === null ? "—" : `${formatNumber(Number(p.synthese.roi_pct))} %`}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted">{t("m9c.plan.note")}</p>
        <table className="table" data-testid="sessions-formation">
          <thead>
            <tr>
              <th>{t("m9c.session.theme")}</th>
              <th>{t("m9c.session.date")}</th>
              <th>{t("m9c.session.plan")}</th>
              <th>{t("m9c.session.participants")}</th>
              <th>{t("m9c.session.cout")}</th>
              <th>{t("m9c.plan.roi")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {sessions.map((s) => (
              <tr key={s.id}>
                <td>
                  {s.code} · {s.theme} <Badge tone={s.type === "realisee" ? "ok" : s.type === "annulee" ? "err" : "warn"}>{s.type_label}</Badge>
                </td>
                <td>{formatDate(s.date_session)}</td>
                <td>{s.plan_annee ?? "—"}</td>
                <td>
                  {s.nb_participants}
                  {s.nb_qualifications_delivrees > 0 && <Badge tone="ok">{t("m9c.session.qualifsDelivrees", { n: s.nb_qualifications_delivrees })}</Badge>}
                </td>
                <td>{s.type === "realisee" ? fcfa(s.cout_reel) : fcfa(s.cout_prevu)}</td>
                <td>{s.roi_pct === null ? "—" : `${formatNumber(Number(s.roi_pct))} %`}</td>
                <td>
                  {s.type === "planifie" && (
                    <ActionBar
                      actions={[
                        { label: t("m9c.session.inscrire"), path: `/api/rh-paie/formations/${s.id}/inscrire/`, tone: "ghost" as const, prompt: { name: "employe", label: t("m9c.session.salarie"), options: empOpts } },
                        { label: t("m9c.session.realiser"), path: `/api/rh-paie/formations/${s.id}/realiser/`, prompt: { name: "cout_reel", label: t("m9c.session.coutReel") } },
                      ]}
                    />
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </SectionCard>

      <SectionCard title={t("m9c.habilitations.title")}>
        <div className="action-bar-buttons">
          <QuickForm
            title={t("m9c.habilitations.ajouter")}
            endpoint="/api/rh-paie/habilitations-postes/"
            fields={[
              { name: "poste", label: t("m9c.habilitations.poste"), type: "select", required: true, options: POSTES.map((p) => ({ value: p, label: t(`m9c.postes.${p}`) })) },
              { name: "mot_cle", label: t("m9c.habilitations.motCle"), required: true },
            ]}
          />
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
        </div>
        <table className="table" data-testid="matrice-habilitations">
          <thead>
            <tr>
              <th>{t("m9c.habilitations.poste")}</th>
              <th>{t("m9c.habilitations.motCle")}</th>
            </tr>
          </thead>
          <tbody>
            {matrice.map((h) => (
              <tr key={h.id}>
                <td>{h.poste_label}</td>
                <td>{h.mot_cle}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted">{t("m9c.habilitations.note")}</p>
      </SectionCard>
    </>
  );
}
