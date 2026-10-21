import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate, formatNumber } from "../../lib/format";
import { ActionBar, Badge, QuickForm, SectionCard } from "../ui";

interface Option {
  id: string;
  code: string;
}
interface EmployeOption extends Option {
  nom_complet: string;
}
interface ContratOption extends Option {
  employe_nom: string;
  type: string;
}
interface Grille extends Option {
  convention: string;
  categorie: string;
  classe: string;
  echelon: number;
  salaire_base: string;
  date_effet: string;
  date_fin: string | null;
  statut_valeur: "provisoire" | "confirme";
}
interface Rubrique extends Option {
  label: string;
  nature: "gain" | "retenue";
}
interface Absence extends Option {
  employe_nom: string;
  type: string;
  date_debut: string;
  date_fin: string;
  nb_jours: number;
  remuneree: boolean;
  statut: "saisie" | "validee" | "annulee";
}
interface Evenement extends Option {
  employe_nom: string;
  type: string;
  date_effet: string;
  categorie_avant: string;
  categorie_apres: string;
  fonction_apres: string;
  grille_apres_label: string | null;
  salaire_avant: string | null;
  salaire_apres: string | null;
}
interface Echeance {
  code: string;
  libelle: string;
  periode_debut: string;
  periode_fin: string;
  date_limite: string;
  jours: number;
  deposee: boolean;
  provisoire: boolean;
}

const CATEGORIES = ["cadre", "agent_maitrise", "technicien", "ouvrier"];
const CONTRATS = ["cdi", "cdd", "chantier", "mission", "stage", "expatrie"];
const ABSENCES = ["injustifiee", "autorisee_np", "autorisee_p", "maladie", "accident_travail", "mise_a_pied"];
const CARRIERE = ["embauche", "promotion", "reclassement", "mutation", "augmentation", "avenant"];

function useOptions<T>(key: string, path: string) {
  return useQuery({ queryKey: ["m9a", key], queryFn: () => api.listAll<T>(path), retry: 0 }).data ?? [];
}

const montant = (v: string | null) => (v === null ? "—" : `${formatNumber(Number(v))} F`);

/** Écarts M9-A : saisies RH / paie, bulletin préparé depuis le contrat, absences, carrière, grille, échéances. */
export function EcartsM9aSection() {
  const { t } = useTranslation();
  const employes = useOptions<EmployeOption>("employes", "/api/rh-paie/employes/");
  const contrats = useOptions<ContratOption>("contrats", "/api/rh-paie/contrats/");
  const grilles = useOptions<Grille>("grilles", "/api/rh-paie/grilles-salaire/");
  const rubriques = useOptions<Rubrique>("rubriques", "/api/rh-paie/rubriques/");
  const absences = useOptions<Absence>("absences", "/api/rh-paie/absences/");
  const carriere = useOptions<Evenement>("carriere", "/api/rh-paie/carriere/");
  const calendrier =
    useQuery({
      queryKey: ["m9a", "calendrier"],
      queryFn: () => api.get<Echeance[]>("/api/rh-paie/echeances-declarations/calendrier/"),
      retry: 0,
    }).data ?? [];

  const employeOpts = employes.map((e) => ({ value: e.id, label: `${e.code} · ${e.nom_complet}` }));
  const contratOpts = contrats.map((c) => ({ value: c.id, label: `${c.code} · ${c.employe_nom}` }));
  const grilleOpts = grilles.map((g) => ({ value: g.id, label: `${g.code} · ${formatNumber(Number(g.salaire_base))} F` }));
  const gainOpts = rubriques.filter((r) => r.nature === "gain").map((r) => ({ value: r.id, label: `${r.code} · ${r.label}` }));
  const choix = (vals: string[], prefix: string) => vals.map((v) => ({ value: v, label: t(`${prefix}.${v}`) }));

  return (
    <>
      <SectionCard title={t("m9a.saisies.title")}>
        <div className="action-bar-buttons" data-testid="saisies-m9">
          <QuickForm
            title={t("m9a.saisies.employe")}
            endpoint="/api/rh-paie/employes/"
            fields={[
              { name: "civilite", label: t("m9a.f.civilite"), type: "select", required: true, defaultValue: "masculin", options: choix(["masculin", "feminin"], "m9a.civilites") },
              { name: "nom", label: t("rhPaie.col.nom"), required: true },
              { name: "prenom", label: t("m9a.f.prenom") },
              { name: "categorie", label: t("rhPaie.col.categorie"), type: "select", defaultValue: "ouvrier", options: choix(CATEGORIES, "rhPaie.categories") },
              { name: "fonction", label: t("rhPaie.col.fonction") },
              { name: "departement", label: t("m9a.f.departement") },
              { name: "site", label: t("m9a.f.site") },
              { name: "date_embauche", label: t("m9a.f.embauche"), type: "date" },
              { name: "parts_fiscales", label: t("m9a.f.parts"), type: "number", step: "0.5", defaultValue: "1" },
            ]}
          />
          <QuickForm
            title={t("m9a.saisies.contrat")}
            endpoint="/api/rh-paie/contrats/"
            fields={[
              { name: "employe", label: t("m9a.f.employe"), type: "select", required: true, options: employeOpts },
              { name: "type", label: t("m9a.f.type"), type: "select", required: true, defaultValue: "cdi", options: choix(CONTRATS, "rhPaie.contrats_types") },
              { name: "date_debut", label: t("m9a.f.debut"), type: "date", required: true },
              { name: "date_fin", label: t("m9a.f.fin"), type: "date" },
              { name: "salaire_base", label: t("m9a.f.salaire"), type: "number", step: "1" },
              { name: "grille", label: t("m9a.f.grille"), type: "select", options: grilleOpts },
              { name: "regime_horaire", label: t("m9a.f.regime") },
              { name: "lieu_affectation", label: t("m9a.f.site") },
            ]}
          />
          <QuickForm
            title={t("m9a.saisies.grille")}
            endpoint="/api/rh-paie/grilles-salaire/"
            fields={[
              { name: "convention", label: t("m9a.f.convention") },
              { name: "categorie", label: t("rhPaie.col.categorie"), type: "select", required: true, defaultValue: "ouvrier", options: choix(CATEGORIES, "rhPaie.categories") },
              { name: "classe", label: t("m9a.f.classe") },
              { name: "echelon", label: t("m9a.f.echelon"), type: "number", min: 1, defaultValue: "1" },
              { name: "salaire_base", label: t("m9a.f.salaire"), type: "number", step: "1", required: true },
              { name: "date_effet", label: t("m9a.f.effet"), type: "date", required: true },
            ]}
          />
          <QuickForm
            title={t("m9a.saisies.rubrique")}
            endpoint="/api/rh-paie/rubriques/"
            fields={[
              { name: "code", label: t("m9a.f.code"), required: true },
              { name: "label", label: t("m9a.f.libelle"), required: true },
              { name: "nature", label: t("m9a.f.nature"), type: "select", defaultValue: "gain", options: choix(["gain", "retenue"], "m9a.natures") },
            ]}
          />
          <QuickForm
            title={t("m9a.saisies.element")}
            endpoint="/api/rh-paie/elements-fixes/"
            fields={[
              { name: "contrat", label: t("rhPaie.contrat"), type: "select", required: true, options: contratOpts },
              { name: "rubrique", label: t("m9a.f.rubrique"), type: "select", required: true, options: gainOpts },
              { name: "montant", label: t("m9a.f.montant"), type: "number", step: "1" },
              { name: "taux", label: t("m9a.f.taux"), type: "number", step: "0.001" },
              { name: "date_debut", label: t("m9a.f.debut"), type: "date", required: true },
              { name: "date_fin", label: t("m9a.f.fin"), type: "date" },
            ]}
          />
          <QuickForm
            title={t("m9a.saisies.carriere")}
            endpoint="/api/rh-paie/carriere/"
            fields={[
              { name: "employe", label: t("m9a.f.employe"), type: "select", required: true, options: employeOpts },
              { name: "type", label: t("m9a.f.type"), type: "select", required: true, defaultValue: "promotion", options: choix(CARRIERE, "m9a.carrieres") },
              { name: "date_effet", label: t("m9a.f.effet"), type: "date", required: true },
              { name: "categorie", label: t("rhPaie.col.categorie"), type: "select", options: choix(CATEGORIES, "rhPaie.categories") },
              { name: "fonction", label: t("rhPaie.col.fonction") },
              { name: "grille", label: t("m9a.f.grille"), type: "select", options: grilleOpts },
              { name: "salaire", label: t("m9a.f.salaire"), type: "number", step: "1" },
              { name: "motif", label: t("m9a.f.motif"), type: "textarea" },
            ]}
          />
          <QuickForm
            title={t("m9a.saisies.absence")}
            endpoint="/api/rh-paie/absences/"
            fields={[
              { name: "employe", label: t("m9a.f.employe"), type: "select", required: true, options: employeOpts },
              { name: "type", label: t("m9a.f.type"), type: "select", required: true, defaultValue: "injustifiee", options: choix(ABSENCES, "m9a.absences_types") },
              { name: "date_debut", label: t("m9a.f.debut"), type: "date", required: true },
              { name: "date_fin", label: t("m9a.f.fin"), type: "date", required: true },
              { name: "remuneree", label: t("m9a.f.remuneree"), type: "select", options: choix(["true", "false"], "m9a.oui_non") },
              { name: "motif", label: t("m9a.f.motif") },
            ]}
          />
          <QuickForm
            title={t("m9a.saisies.bulletin")}
            endpoint="/api/rh-paie/bulletins/"
            fields={[
              { name: "employe", label: t("m9a.f.employe"), type: "select", required: true, options: employeOpts },
              { name: "periode", label: t("m9a.f.periode"), type: "date", required: true },
            ]}
          />
        </div>
        <p className="muted">{t("m9a.saisies.note")}</p>
      </SectionCard>

      <SectionCard title={`${t("m9a.absences.title")} · ${absences.length}`}>
        <table className="table" data-testid="absences-m9">
          <thead>
            <tr>
              <th>{t("m9a.f.code")}</th>
              <th>{t("m9a.f.employe")}</th>
              <th>{t("m9a.f.type")}</th>
              <th>{t("m9a.f.periode")}</th>
              <th>{t("m9a.f.remuneree")}</th>
              <th>{t("rhPaie.col.statut")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {absences.map((a) => (
              <tr key={a.id}>
                <td>{a.code}</td>
                <td>{a.employe_nom}</td>
                <td>{t(`m9a.absences_types.${a.type}`)}</td>
                <td>
                  {formatDate(a.date_debut)} → {formatDate(a.date_fin)} · {a.nb_jours} j
                </td>
                <td>{a.remuneree ? t("m9a.oui_non.true") : <Badge tone="warn">{t("m9a.oui_non.false")}</Badge>}</td>
                <td>
                  <Badge tone={a.statut === "validee" ? "ok" : a.statut === "annulee" ? "err" : "brand"}>{t(`m9a.absences_statut.${a.statut}`)}</Badge>
                </td>
                <td>
                  <ActionBar
                    actions={[
                      ...(a.statut === "saisie" ? [{ label: t("actions.valider"), path: `/api/rh-paie/absences/${a.id}/valider/` }] : []),
                      ...(a.statut !== "annulee"
                        ? [{ label: t("m9a.annuler"), path: `/api/rh-paie/absences/${a.id}/annuler/`, tone: "danger" as const }]
                        : []),
                    ]}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </SectionCard>

      <SectionCard title={t("m9a.echeances.title")}>
        <table className="table" data-testid="echeances-m9">
          <thead>
            <tr>
              <th>{t("m9a.echeances.limite")}</th>
              <th>{t("m9a.f.libelle")}</th>
              <th>{t("m9a.f.periode")}</th>
              <th>{t("rhPaie.col.statut")}</th>
            </tr>
          </thead>
          <tbody>
            {calendrier.map((e) => (
              <tr key={`${e.code}-${e.periode_debut}`}>
                <td>{formatDate(e.date_limite)}</td>
                <td>
                  {e.libelle} {e.provisoire && <Badge tone="warn">{t("m9a.provisoire")}</Badge>}
                </td>
                <td>
                  {formatDate(e.periode_debut)}
                  {e.periode_fin !== e.periode_debut ? ` → ${formatDate(e.periode_fin)}` : ""}
                </td>
                <td>
                  {e.deposee ? (
                    <Badge tone="ok">{t("m9a.echeances.deposee")}</Badge>
                  ) : e.jours < 0 ? (
                    <Badge tone="err">{t("m9a.echeances.retard", { n: -e.jours })}</Badge>
                  ) : (
                    <Badge tone="warn">{t("m9a.echeances.restant", { n: e.jours })}</Badge>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </SectionCard>

      <SectionCard title={t("m9a.grilles.title")}>
        <table className="table">
          <thead>
            <tr>
              <th>{t("m9a.f.code")}</th>
              <th>{t("m9a.f.convention")}</th>
              <th>{t("m9a.f.salaire")}</th>
              <th>{t("m9a.f.effet")}</th>
              <th>{t("rhPaie.col.statut")}</th>
            </tr>
          </thead>
          <tbody>
            {grilles.map((g) => (
              <tr key={g.id}>
                <td>{g.code}</td>
                <td>{g.convention || "—"}</td>
                <td>{montant(g.salaire_base)}</td>
                <td>
                  {formatDate(g.date_effet)}
                  {g.date_fin ? ` → ${formatDate(g.date_fin)}` : ""}
                </td>
                <td>
                  {g.statut_valeur === "confirme" ? (
                    <Badge tone="ok">{t("m9a.confirme")}</Badge>
                  ) : (
                    <ActionBar actions={[{ label: t("m9a.confirmer"), path: `/api/rh-paie/grilles-salaire/${g.id}/confirmer/`, tone: "ghost" as const }]} />
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </SectionCard>

      <SectionCard title={t("m9a.carriere.title")}>
        <table className="table">
          <thead>
            <tr>
              <th>{t("m9a.f.effet")}</th>
              <th>{t("m9a.f.employe")}</th>
              <th>{t("m9a.f.type")}</th>
              <th>{t("rhPaie.col.categorie")}</th>
              <th>{t("m9a.f.salaire")}</th>
            </tr>
          </thead>
          <tbody>
            {carriere.map((ev) => (
              <tr key={ev.id}>
                <td>{formatDate(ev.date_effet)}</td>
                <td>{ev.employe_nom}</td>
                <td>
                  {t(`m9a.carrieres.${ev.type}`)}
                  {ev.fonction_apres ? ` · ${ev.fonction_apres}` : ""}
                </td>
                <td>
                  {ev.categorie_avant} → {ev.categorie_apres}
                  {ev.grille_apres_label ? ` (${ev.grille_apres_label})` : ""}
                </td>
                <td>
                  {montant(ev.salaire_avant)} → {montant(ev.salaire_apres)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </SectionCard>
    </>
  );
}
