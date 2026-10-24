import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate, formatMoney, formatNumber } from "../../lib/format";
import { InfoFormule, ScelleBadge, nomPersonne } from "../sections/affichage";
import { describeError } from "../../lib/offlineQueue";
import { SectionActions } from "../sections/SectionActions";
import { ActionBar, Badge, DataTable, DatePicker, QuickForm, SectionCard } from "../ui";
import type { Column } from "../ui";
import { actionsColumn } from "../ui/DataTable";

interface Equipement {
  id: string;
  code: string;
  label: string;
  compteur_type: string;
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
  source?: string;
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
  etat?: string;
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

type Suivi = Location & { g: Glissant | undefined };
type LigneReporting = Reporting["rows"][number] & { id: string };
type LigneFlux = Flux["rows"][number] & { id: string };

/** Nombre exact : entier sans décimales, sinon deux décimales (taux par jour). */
const num = (v: string | null | undefined) => {
  if (v === null || v === undefined) return "—";
  const n = Number(v);
  return Number.isInteger(n) ? formatNumber(n) : formatNumber(n, { decimals: 2 });
};
/** Code (sur une ligne) et libellé en dessous : la colonne ne se fragmente plus mot à mot sur mobile. */
const codeLibelle = (code: string, libelle?: string | null) => (
  <>
    <span className="cell-nowrap">{code}</span>
    {libelle ? <span className="cell-sub">{libelle}</span> : null}
  </>
);
const fcfa = (v: string | null) => (v === null ? "••••••" : formatMoney(v));
const moisCourant = () => new Date().toISOString().slice(0, 7);
/** Les 12 derniers mois (AAAA-MM), du plus récent au plus ancien : un choix lisible dans la langue de l'interface. */
const derniersMois = () => {
  const d = new Date();
  return Array.from({ length: 12 }, (_, i) => {
    const m = new Date(d.getFullYear(), d.getMonth() - i, 1);
    return `${m.getFullYear()}-${String(m.getMonth() + 1).padStart(2, "0")}`;
  });
};
const ETATS = ["bon", "usage", "degrade", "hors_service"];

function useListe<T>(key: string, path: string): T[] {
  return useQuery({ queryKey: ["m4e", key], queryFn: () => api.listAll<T>(path), retry: 0 }).data ?? [];
}

/** Écarts M4 : parc (plafond, historique, audit photo), commandes GR (validation, lignes, BL, 618), compteurs GR, reporting, plan de charge. */
export function EcartsM4Section() {
  const { t, i18n } = useTranslation();
  const lbl = (key: string, fallback: string) => String(t(key, { defaultValue: fallback }));
  const unite = (e: Equipement) => lbl(`revueR2.logistique.unite.${e.compteur_type}`, e.compteur_type_label);
  const moisLabel = (ym: string) => {
    const [y, m] = ym.split("-").map(Number);
    const txt = new Date(y, m - 1, 1).toLocaleDateString(i18n.language || "fr", { month: "long", year: "numeric" });
    return txt.charAt(0).toUpperCase() + txt.slice(1);
  };
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
  const [toutReporting, setToutReporting] = useState(false);
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
  const photoRef = useRef<HTMLInputElement>(null);
  const [auditMsg, setAuditMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const envoyerAudit = useMutation({
    mutationFn: () => api.upload("/api/logistique/audits/", photo as File, "photo", audit),
    onSuccess: () => {
      setAuditMsg({ ok: true, text: t("quickForm.created") });
      setPhoto(null);
      if (photoRef.current) photoRef.current.value = "";
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

  const actionsHeader = t("ui.actions");
  const suivis: Suivi[] = actives.map((l, i) => ({ ...l, g: glissants[i]?.data }));

  const colsParc: Column<Equipement>[] = [
    { key: "equipement", header: t("ecarts_m4.equipement"), sortValue: (e) => e.code, render: (e) => codeLibelle(e.code, e.label) },
    {
      key: "compteur",
      header: t("ecarts_m4.parc.compteur"),
      num: true,
      sortValue: (e) => Number(e.compteur_value),
      render: (e) => (
        <>
          {e.compteur_type === "forfait" ? (
            <span className="muted">{unite(e)}</span>
          ) : (
            <span className="cell-nowrap">
              {num(e.compteur_value)} <span className="muted">{unite(e)}</span>
            </span>
          )}
        </>
      ),
    },
    {
      key: "plafond",
      header: t("ecarts_m4.parc.plafond"),
      num: true,
      render: (e) => (
        <span className="cell-nowrap">
          {num(e.plafond_compteur)}{" "}
          {e.plafond_pct !== null && <Badge tone={Number(e.plafond_pct) >= 90 ? "warn" : "ok"}>{formatNumber(Number(e.plafond_pct))} %</Badge>}
        </span>
      ),
    },
    actionsColumn<Equipement>(actionsHeader, (e) => [
      { label: t("ecarts_m4.parc.fixerPlafond"), path: `/api/logistique/equipements/${e.id}/plafond/`, prompt: { name: "plafond_compteur", label: t("ecarts_m4.parc.plafond") } },
    ]),
  ];
  const colsReleves: Column<Releve>[] = [
    { key: "equipement", header: t("ecarts_m4.equipement"), sortValue: (r) => r.equipement_code, render: (r) => r.equipement_code },
    { key: "date", header: t("ecarts_m4.date"), sortValue: (r) => r.date, render: (r) => formatDate(r.date) },
    { key: "valeur", header: t("ecarts_m4.parc.valeur"), num: true, render: (r) => num(r.valeur) },
    { key: "source", header: t("ecarts_m4.parc.source"), render: (r) => (
        <>
          {r.source ? lbl(`revueR2.logistique.sourceReleve.${r.source}`, r.source_label) : r.source_label}
          {r.saisi_par_name ? <span className="cell-sub">{nomPersonne(t, r.saisi_par_name)}</span> : null}
        </>
      ),
    },
  ];
  const colsAudits: Column<Audit>[] = [
    {
      key: "code",
      header: t("ecarts_m4.audit.code"),
      sortValue: (a) => a.code,
      render: (a) => (
        <>
          <span className="cell-nowrap">
            {a.code} · {a.equipement_code}
          </span>{" "}
          {a.photo && (
            <a href={a.photo} target="_blank" rel="noreferrer">
              {t("ecarts_m4.audit.voirPhoto")}
            </a>
          )}
        </>
      ),
    },
    { key: "date", header: t("ecarts_m4.date"), sortValue: (a) => a.date_audit, render: (a) => formatDate(a.date_audit) },
    { key: "etat", header: t("ecarts_m4.audit.etat"), render: (a) => (a.etat ? lbl(`revueR2.logistique.etatAudit.${a.etat}`, a.etat_label) : a.etat_label) },
    { key: "empreinte", header: t("ecarts_m4.audit.empreinte"), render: (a) => <ScelleBadge sha={a.photo_sha256} /> },
    { key: "conservation", header: t("ecarts_m4.audit.conservation"), sortValue: (a) => a.conserver_jusqu_au, render: (a) => formatDate(a.conserver_jusqu_au) },
  ];
  const colsHistorique: Column<Historique>[] = [
    { key: "equipement", header: t("ecarts_m4.equipement"), sortValue: (h) => h.equipement_code, render: (h) => h.equipement_code },
    { key: "champ", header: t("ecarts_m4.audit.champ"), render: (h) => h.champ },
    { key: "avantApres", header: t("ecarts_m4.audit.avantApres"), render: (h) => `${h.ancienne_valeur || "—"} → ${h.nouvelle_valeur || "—"}` },
    { key: "par", header: t("ecarts_m4.audit.par"), sortValue: (h) => h.modifie_le, render: (h) => `${nomPersonne(t, h.modifie_par_name)} · ${formatDate(h.modifie_le)}` },
  ];
  const colsLocations: Column<Location>[] = [
    {
      key: "location",
      header: t("ecarts_m4.location"),
      sortValue: (l) => l.code,
      render: (l) => (
        <span className="cell-nowrap">
          {l.code} · {l.equipement_code}{" "}
          <Badge tone={l.statut === "active" ? "warn" : l.statut === "terminee" ? "ok" : "neutral"}>
            {lbl(`revueR2.logistique.statutLocation.${l.statut}`, l.statut_label)}
          </Badge>
        </span>
      ),
    },
    {
      key: "validations",
      header: t("ecarts_m4.commandes.validations"),
      render: (l) => (
        <>
          {l.validations.m2 && <Badge tone={l.validations.m2_ok ? "ok" : "warn"}>{t("tableaux.logistique.validAchats")}</Badge>}{" "}
          {l.validations.dr && <Badge tone={l.validations.dr_ok ? "ok" : "warn"}>{t("tableaux.logistique.validDirection")}</Badge>}
          {!l.validations.m2 && !l.validations.dr && <span className="muted cell-nowrap">{t("ecarts_m4.commandes.sousSeuil")}</span>}
        </>
      ),
    },
    {
      key: "achats",
      header: t("ecarts_m4.commandes.achats"),
      render: (l) => (
        <span className="cell-nowrap">
          {l.bon_commande_code ?? "—"} / {l.facture_code ?? "—"}{" "}
          {l.facture_conforme !== null && (
            <Badge tone={l.facture_conforme ? "ok" : "err"}>{l.facture_conforme ? t("ecarts_m4.commandes.conforme") : t("ecarts_m4.commandes.ecart")}</Badge>
          )}
          <span className="cell-sub" title={t("tableaux.logistique.compte618")}>
            {t("premiumModules.compte618")}
          </span>
        </span>
      ),
    },
    {
      key: "attendu",
      header: t("ecarts_m4.commandes.attendu"),
      num: true,
      sortValue: (l) => (l.montant_attendu === null ? null : Number(l.montant_attendu)),
      render: (l) => fcfa(l.montant_attendu),
    },
    actionsColumn<Location>(actionsHeader, (l) => [
      ...(l.statut === "brouillon" && !l.emis_le && l.validations.m2 && !l.validations.m2_ok
        ? [{ label: t("ecarts_m4.commandes.validerM2"), path: `/api/logistique/locations/${l.id}/valider-m2/` }]
        : []),
      ...(l.statut === "brouillon" && !l.emis_le && l.validations.dr && !l.validations.dr_ok
        ? [{ label: t("ecarts_m4.commandes.validerDr"), path: `/api/logistique/locations/${l.id}/valider-dr/` }]
        : []),
      ...(!l.bon_commande_code
        ? [
            {
              label: t("ecarts_m4.commandes.lierBc"),
              path: `/api/logistique/locations/${l.id}/lier-bc-achat/`,
              prompt: { name: "bon_commande_achat", label: t("ecarts_m4.commandes.choisirBc"), options: bcs.map((b) => ({ value: b.id, label: b.code })) },
            },
          ]
        : []),
      ...(!l.facture_code
        ? [
            {
              label: t("ecarts_m4.commandes.rapprocher"),
              path: `/api/logistique/locations/${l.id}/rapprocher-facture/`,
              prompt: { name: "facture_achat", label: t("ecarts_m4.commandes.choisirFacture"), options: factures.map((f) => ({ value: f.id, label: f.code })) },
            },
          ]
        : []),
      ...(l.statut === "brouillon" || l.statut === "active"
        ? [
            {
              label: t("ecarts_m4.commandes.receptionnerBl"),
              path: `/api/logistique/locations/${l.id}/receptionner-bl/`,
              prompt: { name: "reference_bl", label: t("ecarts_m4.commandes.referenceBl") },
            },
          ]
        : []),
      { label: t("ecarts_m4.commandes.escalader"), path: `/api/logistique/locations/${l.id}/escalader/`, tone: "danger" as const, prompt: { name: "motif", label: t("ecarts_m4.commandes.motif") } },
    ]),
  ];
  const colsLignes: Column<Ligne>[] = [
    { key: "location", header: t("ecarts_m4.location"), sortValue: (g) => g.location_code, render: (g) => g.location_code },
    { key: "designation", header: t("ecarts_m4.commandes.designation"), render: (g) => g.designation },
    { key: "quantite", header: t("ecarts_m4.commandes.quantite"), num: true, render: (g) => `${num(g.quantite)} ${g.unite}` },
    { key: "livree", header: t("ecarts_m4.commandes.livree"), num: true, render: (g) => num(g.quantite_livree) },
    { key: "montant", header: t("ecarts_m4.commandes.montant"), num: true, sortValue: (g) => (g.montant === null ? null : Number(g.montant)), render: (g) => fcfa(g.montant) },
    actionsColumn<Ligne>(actionsHeader, (g) => [
      { label: t("ecarts_m4.commandes.livrer"), path: `/api/logistique/lignes-gr/${g.id}/livrer/`, prompt: { name: "quantite_livree", label: t("ecarts_m4.commandes.livree") } },
    ]),
  ];
  const colsReceptions: Column<ReceptionBL>[] = [
    { key: "bl", header: t("ecarts_m4.commandes.referenceBl"), sortValue: (r) => r.code, render: (r) => `${r.code} · ${r.location_code} · ${r.reference_bl}` },
    { key: "date", header: t("ecarts_m4.date"), sortValue: (r) => r.date_reception, render: (r) => formatDate(r.date_reception) },
    { key: "ecart", header: t("ecarts_m4.commandes.ecartPct"), num: true, sortValue: (r) => Number(r.ecart_pct), render: (r) => `${formatNumber(Number(r.ecart_pct))} %` },
    {
      key: "escalade",
      header: t("ecarts_m4.commandes.escaladeM12"),
      render: (r) =>
        r.litige ? (
          <Badge tone="err">{[r.contentieux_code, r.dossier_gr_code].filter(Boolean).join(" · ") || t("ecarts_m4.flux.litige")}</Badge>
        ) : (
          <Badge tone="ok">{t("ecarts_m4.commandes.conforme")}</Badge>
        ),
    },
  ];
  const colsSuivis: Column<Suivi>[] = [
    {
      key: "location",
      header: t("ecarts_m4.location"),
      sortValue: (l) => l.code,
      render: (l) => (
        <span className="cell-nowrap">
          {l.code} · {l.equipement_code} {l.g?.provisoire && <Badge tone="warn">{t("ecarts_m4.provisoire")}</Badge>}
        </span>
      ),
    },
    { key: "dernier", header: t("ecarts_m4.compteurs.dernier"), num: true, render: (l) => num(l.g?.dernier_releve) },
    { key: "taux", header: t("ecarts_m4.compteurs.taux"), num: true, render: (l) => num(l.g?.taux_jour) },
    { key: "projection", header: t("ecarts_m4.compteurs.projection"), num: true, render: (l) => num(l.g?.projection_valeur) },
  ];
  const colsArchives: Column<Archive>[] = [
    { key: "location", header: t("ecarts_m4.location"), sortValue: (a) => a.location_code, render: (a) => a.location_code },
    { key: "consommation", header: t("ecarts_m4.compteurs.consommation"), num: true, render: (a) => num(a.contenu.consommation) },
    {
      key: "empreinte",
      header: t("ecarts_m4.audit.empreinte"),
      render: (a) => (
        a.integre ? (
          <ScelleBadge sha={a.sha256} />
        ) : (
          <Badge tone="err" title={t("premiumModules.scelle.title", { sha: a.sha256 })}>{t("ecarts_m4.compteurs.altere")}</Badge>
        )
      ),
    },
    { key: "conservation", header: t("ecarts_m4.audit.conservation"), sortValue: (a) => a.conserver_jusqu_au, render: (a) => formatDate(a.conserver_jusqu_au) },
  ];
  const colsReporting: Column<LigneReporting>[] = [
    {
      key: "equipement",
      header: t("ecarts_m4.equipement"),
      sortValue: (r) => r.equipement,
      render: (r) => (
        <>
          <span className="cell-nowrap">
            {r.equipement} {r.gr && <Badge tone="brand">GR</Badge>}
          </span>
          <span className="cell-sub">{r.label}</span>
        </>
      ),
    },
    { key: "jours", header: t("ecarts_m4.reporting.jours"), num: true, sortValue: (r) => r.jours_mobilises, render: (r) => formatNumber(r.jours_mobilises) },
    { key: "utilisation", header: t("ecarts_m4.reporting.utilisation"), num: true, sortValue: (r) => Number(r.utilisation_pct), render: (r) => `${formatNumber(Number(r.utilisation_pct))} %` },
    { key: "economies", header: t("ecarts_m4.reporting.economies"), num: true, render: (r) => (r.gr ? "—" : fcfa(r.economie)) },
  ];
  const colsFlux: Column<LigneFlux>[] = [
    { key: "affaire", header: t("ecarts_m4.flux.affaire"), sortValue: (r) => r.affaire ?? r.titre, render: (r) => (r.affaire ? codeLibelle(r.affaire, r.titre) : lbl("revueR2.logistique.sansAffaire", r.titre)) },
    {
      key: "machines",
      header: t("ecarts_m4.flux.machines"),
      render: (r) => r.machines.map((m) => `${m.equipement}${m.of ? ` (${m.of})` : ""}${m.source === "gr" ? " GR" : ""}`).join(", "),
    },
    { key: "consommation", header: t("ecarts_m4.compteurs.consommation"), num: true, render: (r) => num(r.consommation_gr) },
    {
      key: "bl",
      header: t("ecarts_m4.flux.bl"),
      render: (r) => (
        <>
          {r.bl.length} {r.bl.some((b) => b.litige) && <Badge tone="err">{t("ecarts_m4.flux.litige")}</Badge>}
        </>
      ),
    },
  ];

  return (
    <>
      <SectionCard
        title={t("ecarts_m4.parc.title")}
        actions={
          <SectionActions>
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
          </SectionActions>
        }
      >
        <div data-testid="m4-parc">
          <p className="muted">{t("ecarts_m4.parc.hint")}</p>
          <DataTable columns={colsParc} rows={equipements} caption={t("ecarts_m4.parc.title")} emptyLabel={t("tableaux.logistique.aucunEquipement")} />
          <h4>{t("ecarts_m4.parc.historiqueCompteurs")}</h4>
          <DataTable
            columns={colsReleves}
            rows={releves.slice(0, 15)}
            caption={t("ecarts_m4.parc.historiqueCompteurs")}
            density="compact"
            emptyLabel={t("tableaux.logistique.aucunReleve")}
          />
        </div>
      </SectionCard>

      <SectionCard title={t("ecarts_m4.audit.title")}>
        <div data-testid="m4-audit">
          <p className="muted">{t("ecarts_m4.audit.hint")}</p>
          <form className="card quick-form" onSubmit={submitAudit} aria-label={t("ecarts_m4.audit.nouveau")}>
            <div className="quick-form-grid">
              <div className="field">
                <label htmlFor="m4-audit-eq">{t("ecarts_m4.equipement")} *</label>
                <select id="m4-audit-eq" className="control" required value={audit.equipement} onChange={(e) => setAudit({ ...audit, equipement: e.target.value })}>
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
                <DatePicker id="m4-audit-date" required value={audit.date_audit} onChange={(iso) => setAudit({ ...audit, date_audit: iso })} />
              </div>
              <div className="field">
                <label htmlFor="m4-audit-etat">{t("ecarts_m4.audit.etat")}</label>
                <select id="m4-audit-etat" className="control" value={audit.etat} onChange={(e) => setAudit({ ...audit, etat: e.target.value })}>
                  {ETATS.map((v) => (
                    <option key={v} value={v}>
                      {t(`ecarts_m4.audit.etats.${v}`)}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label htmlFor="m4-audit-photo">{t("ecarts_m4.audit.photo")} *</label>
                {/* Champ fichier natif masqué (son « Choose File » suit la langue du navigateur) : bouton + nom du fichier dans la langue de l'interface. */}
                <input
                  ref={photoRef}
                  id="m4-audit-photo"
                  className="sr-only"
                  type="file"
                  accept="image/*"
                  tabIndex={-1}
                  onChange={(e) => setPhoto(e.target.files?.[0] ?? null)}
                />
                <span style={{ display: "flex", alignItems: "center", gap: "var(--space-2)", minWidth: 0, minHeight: "var(--control-h)" }}>
                  <button type="button" className="btn ghost sm" style={{ flex: "none" }} onClick={() => photoRef.current?.click()}>
                    {t("revueR2.logistique.choisirPhoto")}
                  </button>
                  <span className="muted" style={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {photo ? photo.name : t("revueR2.logistique.aucunePhoto")}
                  </span>
                </span>
              </div>
              <div className="field wide">
                <label htmlFor="m4-audit-obs">{t("ecarts_m4.audit.observations")}</label>
                <textarea id="m4-audit-obs" className="control" rows={3} value={audit.observations} onChange={(e) => setAudit({ ...audit, observations: e.target.value })} />
              </div>
            </div>
            <div className="quick-form-actions">
              <button type="submit" className="btn primary" disabled={envoyerAudit.isPending || !photo || !audit.equipement}>
                {t("ecarts_m4.audit.enregistrer")}
              </button>
              {auditMsg && (
                <p className={auditMsg.ok ? "quick-form-ok" : "action-error"} role={auditMsg.ok ? "status" : "alert"}>
                  {auditMsg.text}
                </p>
              )}
            </div>
          </form>
          <DataTable columns={colsAudits} rows={audits} caption={t("ecarts_m4.audit.title")} emptyLabel={t("tableaux.logistique.aucunAudit")} />
          <h4>{t("ecarts_m4.audit.historique")}</h4>
          <DataTable
            columns={colsHistorique}
            rows={historique.slice(0, 20)}
            caption={t("ecarts_m4.audit.historique")}
            density="compact"
            emptyLabel={t("tableaux.logistique.aucuneModification")}
          />
        </div>
      </SectionCard>

      <SectionCard
        title={t("ecarts_m4.commandes.title")}
        actions={
          <SectionActions>
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
          </SectionActions>
        }
      >
        <div data-testid="m4-commandes">
          <p className="muted">{t("ecarts_m4.commandes.hint")}</p>
          <DataTable columns={colsLocations} rows={locations} caption={t("ecarts_m4.commandes.title")} emptyLabel={t("tableaux.logistique.aucuneCommande")} />
          <h4>{t("ecarts_m4.commandes.lignes")}</h4>
          <DataTable columns={colsLignes} rows={lignes} caption={t("ecarts_m4.commandes.lignes")} emptyLabel={t("tableaux.logistique.aucuneLigne")} />
          <h4>{t("ecarts_m4.commandes.receptions")}</h4>
          <div data-testid="m4-receptions-bl">
            <DataTable columns={colsReceptions} rows={receptions} caption={t("ecarts_m4.commandes.receptions")} emptyLabel={t("tableaux.logistique.aucuneReception")} />
          </div>
        </div>
      </SectionCard>

      <SectionCard
        title={
          <span className="r3-badges">
            {t("ecarts_m4.compteurs.title")}
            <InfoFormule>{t("ecarts_m4.compteurs.formule")}</InfoFormule>
          </span>
        }
        actions={
          <SectionActions>
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
          </SectionActions>
        }
      >
        <div data-testid="m4-compteurs">
          <p className="muted">{t("ecarts_m4.compteurs.hint")}</p>
          <DataTable columns={colsSuivis} rows={suivis} caption={t("ecarts_m4.compteurs.title")} emptyLabel={t("tableaux.logistique.aucuneLocationActive")} />
          <h4>{t("ecarts_m4.compteurs.archives")}</h4>
          <DataTable columns={colsArchives} rows={archives} caption={t("ecarts_m4.compteurs.archives")} emptyLabel={t("tableaux.logistique.aucuneArchive")} />
        </div>
      </SectionCard>

      <SectionCard
        title={
          <span className="r3-badges">
            {t("ecarts_m4.reporting.title")}
            <InfoFormule>{t("ecarts_m4.reporting.formules")}</InfoFormule>
          </span>
        }
      >
        <div data-testid="m4-reporting">
          <div className="field" style={{ maxWidth: 220 }}>
            <label htmlFor="m4-reporting-mois">{t("ecarts_m4.reporting.mois")}</label>
            <select id="m4-reporting-mois" className="control" value={periode} onChange={(e) => setPeriode(e.target.value)}>
              {derniersMois().map((m) => (
                <option key={m} value={m}>
                  {moisLabel(m)}
                </option>
              ))}
            </select>
          </div>
          {reporting?.provisoire && (
            <p className="muted" role="note">
              <Badge tone="warn">{t("revueR2.logistique.provisoire")}</Badge> {t("ecarts_m4.reporting.warnProvisoire")}
            </p>
          )}
          {reporting && (
            <>
              <p>
                <span className="muted">{t("ecarts_m4.reporting.utilisation")}</span>{" "}
                <strong className="num">{formatNumber(Number(reporting.utilisation_moyenne_pct))} %</strong>
                <span className="muted"> · {t("ecarts_m4.reporting.economies")}</span> <strong className="amount">{fcfa(reporting.economies)}</strong>
                <span className="muted"> · {t("ecarts_m4.reporting.rentabilite")}</span>{" "}
                <strong className="num">{reporting.rentabilite_pct === null ? "—" : `${formatNumber(Number(reporting.rentabilite_pct))} %`}</strong>
              </p>
              <DataTable
                columns={colsReporting}
                rows={reporting.rows.filter((r) => toutReporting || r.jours_mobilises > 0).map((r) => ({ ...r, id: r.equipement }))}
                caption={t("ecarts_m4.reporting.title")}
                emptyLabel={t("tableaux.logistique.aucunReporting")}
              />
              {/* Équipements à 0 jour mobilisé (0 % / 0 FCFA) repliés : seule l'activité réelle est listée. */}
              {reporting.rows.some((r) => r.jours_mobilises <= 0) && (
                <button type="button" className="btn ghost sm" aria-expanded={toutReporting} onClick={() => setToutReporting((v) => !v)}>
                  {toutReporting
                    ? t("premiumModules.reporting.masquerInactifs")
                    : t("premiumModules.reporting.voirInactifs", { count: reporting.rows.filter((r) => r.jours_mobilises <= 0).length })}
                </button>
              )}
            </>
          )}
        </div>
      </SectionCard>

      <SectionCard
        title={t("ecarts_m4.flux.title")}
        actions={
          <SectionActions>
            <ActionBar actions={[{ label: t("ecarts_m4.flux.proposer"), path: "/api/logistique/demandes/proposer/", tone: "ghost" }]} />
          </SectionActions>
        }
      >
        <div data-testid="m4-flux">
          <p className="muted">{t("ecarts_m4.flux.hint")}</p>
          <DataTable
            columns={colsFlux}
            rows={(flux?.rows ?? []).map((r) => ({ ...r, id: r.affaire ?? "sans-affaire" }))}
            caption={t("ecarts_m4.flux.title")}
            emptyLabel={t("tableaux.logistique.aucunFlux")}
          />
        </div>
      </SectionCard>
    </>
  );
}
