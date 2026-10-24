import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate, formatMoney } from "../../lib/format";
import { nombre } from "../sections/affichage";
import { SectionActions } from "../sections/SectionActions";
import { ActionBar, Badge, DataTable, QuickForm, SectionCard } from "../ui";
import type { Column } from "../ui";

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

type LigneEcheance = Echeance & { id: string };
interface GroupeEcheances {
  id: string;
  date_limite: string;
  items: LigneEcheance[];
  jours: number;
  deposees: number;
}

/** Écarts M9-A : saisies RH / paie, bulletin préparé depuis le contrat, absences, carrière, grille, échéances. */
/** Période de déclaration lisible : « 2026-07-01 » → « Juillet 2026 ». */
function moisLisible(iso: string, langue: string): string {
  const d = new Date(`${iso.slice(0, 10)}T00:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  const texte = d.toLocaleDateString(langue, { month: "long", year: "numeric" });
  return texte.charAt(0).toUpperCase() + texte.slice(1);
}

export function EcartsM9aSection() {
  const { t, i18n } = useTranslation();
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
  const grilleOpts = grilles.map((g) => ({ value: g.id, label: `${g.code} · ${formatMoney(g.salaire_base)}` }));
  const gainOpts = rubriques.filter((r) => r.nature === "gain").map((r) => ({ value: r.id, label: `${r.code} · ${r.label}` }));
  const choix = (vals: string[], prefix: string) => vals.map((v) => ({ value: v, label: t(`${prefix}.${v}`) }));
  const categorie = (v: string) => (v ? t(`rhPaie.categories.${v}`, { defaultValue: v }) : "—");
  const echeances: LigneEcheance[] = calendrier.map((e) => ({ ...e, id: `${e.code}-${e.periode_debut}` }));

  const colAbsences: Column<Absence>[] = [
    { key: "code", header: t("m9a.f.code"), sortValue: (a) => a.code, render: (a) => a.code },
    { key: "employe", header: t("m9a.f.employe"), sortValue: (a) => a.employe_nom, render: (a) => a.employe_nom },
    { key: "type", header: t("m9a.f.type"), render: (a) => t(`m9a.absences_types.${a.type}`) },
    {
      key: "periode",
      header: t("m9a.f.periode"),
      sortValue: (a) => a.date_debut,
      render: (a) => `${formatDate(a.date_debut)} → ${formatDate(a.date_fin)} · ${nombre(a.nb_jours, 1)} j`,
    },
    { key: "remuneree", header: t("m9a.f.remuneree"), render: (a) => (a.remuneree ? t("m9a.oui_non.true") : <Badge tone="warn">{t("m9a.oui_non.false")}</Badge>) },
    {
      key: "statut",
      header: t("rhPaie.col.statut"),
      render: (a) => <Badge tone={a.statut === "validee" ? "ok" : a.statut === "annulee" ? "err" : "brand"}>{t(`m9a.absences_statut.${a.statut}`)}</Badge>,
    },
    {
      key: "actions",
      header: <span className="sr-only">{t("ui.actions")}</span>,
      render: (a) => (
        <ActionBar
          actions={[
            ...(a.statut === "saisie" ? [{ label: t("actions.valider"), path: `/api/rh-paie/absences/${a.id}/valider/` }] : []),
            ...(a.statut !== "annulee" ? [{ label: t("m9a.annuler"), path: `/api/rh-paie/absences/${a.id}/annuler/`, tone: "danger" as const }] : []),
          ]}
        />
      ),
    },
  ];
  // Calendrier de dépôt groupé par date limite : une ligne par échéance (CNSS, FNH, IRPP, CFP… du même mois),
  // un seul badge de retard, au lieu de la même date répétée quatre fois.
  const groupes = new Map<string, LigneEcheance[]>();
  for (const e of echeances) groupes.set(e.date_limite, [...(groupes.get(e.date_limite) ?? []), e]);
  const echeancesGroupees: GroupeEcheances[] = [...groupes.entries()]
    .sort(([x], [y]) => x.localeCompare(y))
    .map(([date, items]) => ({
      id: date,
      date_limite: date,
      items,
      jours: Math.min(...items.map((e) => e.jours)),
      deposees: items.filter((e) => e.deposee).length,
    }));
  const periodeTexte = (e: Echeance) =>
    `${moisLisible(e.periode_debut, i18n.language)}${e.periode_fin !== e.periode_debut ? ` → ${moisLisible(e.periode_fin, i18n.language)}` : ""}`;
  const colEcheances: Column<GroupeEcheances>[] = [
    { key: "limite", header: t("m9a.echeances.limite"), sortValue: (g) => g.date_limite, render: (g) => <span className="r3-nowrap">{formatDate(g.date_limite)}</span> },
    {
      key: "declarations",
      header: t("premiumModules.rh.declarations"),
      render: (g) => (
        <span className="r3-badges">
          {g.items.map((e) => (
            <Badge key={e.id} tone={e.deposee ? "ok" : "neutral"} title={`${e.libelle} · ${periodeTexte(e)}`}>
              {e.code.replace(/^ECH-/, "")}
            </Badge>
          ))}
        </span>
      ),
    },
    {
      key: "periode",
      header: t("m9a.f.periode"),
      render: (g) => <span className="r3-nowrap">{[...new Set(g.items.map(periodeTexte))].join(" · ")}</span>,
    },
    {
      key: "statut",
      header: t("rhPaie.col.statut"),
      sortValue: (g) => (g.deposees === g.items.length ? null : g.jours),
      render: (g) => (
        <>
          {g.deposees === g.items.length ? (
            <Badge tone="ok">{t("m9a.echeances.deposee")}</Badge>
          ) : g.jours < 0 ? (
            <Badge tone="err">{t("m9a.echeances.retard", { n: -g.jours })}</Badge>
          ) : (
            <Badge tone="warn">{t("m9a.echeances.restant", { n: g.jours })}</Badge>
          )}
          <span className="cell-sub">{t("premiumModules.rh.deposees", { n: g.deposees, total: g.items.length })}</span>
        </>
      ),
    },
  ];
  const colGrilles: Column<Grille>[] = [
    { key: "code", header: t("m9a.f.code"), sortValue: (g) => g.code, render: (g) => g.code },
    { key: "convention", header: t("m9a.f.convention"), render: (g) => g.convention || "—" },
    { key: "salaire", header: t("m9a.f.salaire"), num: true, sortValue: (g) => Number(g.salaire_base), render: (g) => formatMoney(g.salaire_base) },
    {
      key: "effet",
      header: t("m9a.f.effet"),
      sortValue: (g) => g.date_effet,
      render: (g) => `${formatDate(g.date_effet)}${g.date_fin ? ` → ${formatDate(g.date_fin)}` : ""}`,
    },
    {
      key: "statut",
      header: t("rhPaie.col.statut"),
      render: (g) =>
        g.statut_valeur === "confirme" ? (
          <Badge tone="ok">{t("m9a.confirme")}</Badge>
        ) : (
          <ActionBar actions={[{ label: t("m9a.confirmer"), path: `/api/rh-paie/grilles-salaire/${g.id}/confirmer/`, tone: "ghost" as const }]} />
        ),
    },
  ];
  const colCarriere: Column<Evenement>[] = [
    { key: "effet", header: t("m9a.f.effet"), sortValue: (ev) => ev.date_effet, render: (ev) => formatDate(ev.date_effet) },
    { key: "employe", header: t("m9a.f.employe"), sortValue: (ev) => ev.employe_nom, render: (ev) => ev.employe_nom },
    { key: "type", header: t("m9a.f.type"), render: (ev) => `${t(`m9a.carrieres.${ev.type}`)}${ev.fonction_apres ? ` · ${ev.fonction_apres}` : ""}` },
    {
      key: "categorie",
      header: t("rhPaie.col.categorie"),
      render: (ev) => `${categorie(ev.categorie_avant)} → ${categorie(ev.categorie_apres)}${ev.grille_apres_label ? ` (${ev.grille_apres_label})` : ""}`,
    },
    { key: "salaire", header: t("m9a.f.salaire"), num: true, render: (ev) => `${formatMoney(ev.salaire_avant)} → ${formatMoney(ev.salaire_apres)}` },
  ];

  return (
    <>
      <SectionCard title={t("m9a.saisies.title")}>
        <div data-testid="saisies-m9" className="r3-saisies">
          <SectionActions>
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
              title={t("m9a.saisies.bulletin")}
              endpoint="/api/rh-paie/bulletins/"
              fields={[
                { name: "employe", label: t("m9a.f.employe"), type: "select", required: true, options: employeOpts },
                { name: "periode", label: t("m9a.f.periode"), type: "date", required: true },
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
          </SectionActions>
        </div>
        <p className="muted">{t("m9a.saisies.note")}</p>
      </SectionCard>

      {absences.length > 0 ? (
        <SectionCard title={`${t("m9a.absences.title")} · ${absences.length}`}>
          <div data-testid="absences-m9">
            <DataTable columns={colAbsences} rows={absences} caption={t("m9a.absences.title")} />
          </div>
        </SectionCard>
      ) : null}

      <SectionCard
        title={
          <span className="r3-badges">
            {t("m9a.echeances.title")}
            {echeances.some((e) => e.provisoire) ? (
              <Badge tone="warn" title={t("revueR3.rh.echeancesProvisoires")}>
                {t("revueR3.provisoire")}
              </Badge>
            ) : null}
          </span>
        }
      >
        <div data-testid="echeances-m9">
          <DataTable columns={colEcheances} rows={echeancesGroupees} caption={t("m9a.echeances.title")} />
        </div>
      </SectionCard>

      {grilles.length > 0 ? (
        <SectionCard title={t("m9a.grilles.title")}>
          <DataTable columns={colGrilles} rows={grilles} caption={t("m9a.grilles.title")} />
        </SectionCard>
      ) : null}

      {carriere.length > 0 ? (
        <SectionCard title={t("m9a.carriere.title")}>
          <DataTable columns={colCarriere} rows={carriere} caption={t("m9a.carriere.title")} />
        </SectionCard>
      ) : null}
    </>
  );
}
