import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate, formatMoney } from "../../lib/format";
import { usePagedList } from "../../lib/usePagedList";
import type { Paginated } from "../../types";
import { ActionBar, Badge, DataTable, PagedDataTable, SectionCard } from "../ui";
import type { ActionDef, Column } from "../ui";

/** Clôture M1 : offres versionnées, affaires, contrats signés / avenants, marges par axe (CDC §3.4-§3.11). */

interface Offre {
  id: string;
  code: string;
  version: number;
  title: string;
  client_name: string | null;
  montant_offre: string | null;
  status: string;
  status_label: string;
}
interface Affaire {
  id: string;
  code: string;
  title: string;
  client_name: string | null;
  responsable_email: string | null;
  status: string;
  status_label: string;
}
interface Contrat {
  id: string;
  code: string;
  profile_label: string;
  client_name: string | null;
  affaire_title: string | null;
  montant_actuel: string | null;
  end_date: string | null;
  expiry_status: string;
  avenants_total: number;
  status: string;
  status_label: string;
}
interface LigneMarge {
  cle: string;
  affaires: number;
  ca_prevu: string | null;
  marge_prevue: string | null;
  produits: string | null;
  charges: string | null;
  marge_reelle: string | null;
}

const TON: Record<string, "ok" | "warn" | "err" | "brand" | "neutral"> = {
  brouillon: "neutral",
  soumise: "warn",
  gagnee: "ok",
  perdue: "err",
  annulee: "err",
  remplacee: "neutral",
  confirmee: "brand",
  en_cours: "warn",
  cloturee: "ok",
  actif: "ok",
  suspendu: "warn",
  cloture: "neutral",
};

const montant = (v: string | null) => (v === null ? "••••••" : formatMoney(v));

function actionsOffre(o: Offre, t: (k: string) => string): ActionDef[] {
  const base = `/api/commercial/estimates/${o.id}`;
  if (o.status === "brouillon")
    return [
      { label: t("commercial.act.soumettre"), path: `${base}/soumettre/` },
      { label: t("commercial.act.annuler"), path: `${base}/annuler/`, tone: "danger", confirm: t("commercial.act.confirmAnnuler") },
    ];
  if (o.status === "soumise")
    return [
      { label: t("commercial.act.gagner"), path: `${base}/gagner/` },
      { label: t("commercial.act.reviser"), path: `${base}/reviser/`, tone: "ghost" },
      { label: t("commercial.act.perdre"), path: `${base}/perdre/`, tone: "danger", prompt: { name: "motif", label: t("commercial.act.motifPerte") } },
    ];
  return [];
}

function actionsAffaire(a: Affaire, t: (k: string) => string): ActionDef[] {
  const base = `/api/commercial/affaires/${a.id}`;
  if (a.status === "brouillon") return [{ label: t("commercial.act.confirmer"), path: `${base}/confirmer/` }];
  if (a.status === "confirmee") return [{ label: t("actions.demarrer"), path: `${base}/demarrer/` }];
  if (a.status === "en_cours")
    return [{ label: t("actions.cloturer"), path: `${base}/cloturer/`, confirm: t("actions.confirmCloturer") }];
  return [];
}

function actionsContrat(c: Contrat, t: (k: string) => string): ActionDef[] {
  const base = `/api/commercial/contracts/${c.id}`;
  if (c.status === "brouillon")
    return [{ label: t("commercial.act.activer"), path: `${base}/activer/`, prompt: { name: "document", label: t("commercial.act.documentSigne") } }];
  if (c.status === "actif") return [{ label: t("commercial.act.suspendre"), path: `${base}/suspendre/`, tone: "ghost" }];
  if (c.status === "suspendu") return [{ label: t("commercial.act.reprendre"), path: `${base}/reprendre/` }];
  return [];
}

export function CommercialSections() {
  const { t } = useTranslation();
  const [axe, setAxe] = useState("client");
  const offres = usePagedList<Offre>("commercial-offres", (q) => api.get<Paginated<Offre>>(`/api/commercial/estimates/${q}`));
  const affaires = usePagedList<Affaire>("commercial-affaires", (q) => api.get<Paginated<Affaire>>(`/api/commercial/affaires/${q}`));
  const contrats = usePagedList<Contrat>("commercial-contrats", (q) => api.get<Paginated<Contrat>>(`/api/commercial/contracts/${q}`));
  const marges = useQuery({
    queryKey: ["commercial-marges", axe],
    queryFn: () => api.get<{ lignes: (LigneMarge & { id: string })[] }>(`/api/commercial/affaires/marges/?par=${axe}`),
    select: (d) => d.lignes.map((l) => ({ ...l, id: l.cle })),
  });

  const statut = (s: string, label: string) => <Badge tone={TON[s] ?? "brand"}>{label}</Badge>;

  const colOffres: Column<Offre>[] = [
    { key: "code", header: t("commercial.col.code"), render: (o) => `${o.code} · v${o.version}` },
    { key: "titre", header: t("commercial.col.titre"), render: (o) => o.title },
    { key: "client", header: t("commercial.col.client"), render: (o) => o.client_name ?? "—" },
    { key: "montant", header: t("commercial.col.montant"), num: true, render: (o) => montant(o.montant_offre) },
    { key: "statut", header: t("commercial.col.statut"), render: (o) => statut(o.status, o.status_label) },
    { key: "actions", header: "", render: (o) => <ActionBar actions={actionsOffre(o, t)} /> },
  ];
  const colAffaires: Column<Affaire>[] = [
    { key: "code", header: t("commercial.col.code"), render: (a) => a.code },
    { key: "titre", header: t("commercial.col.titre"), render: (a) => a.title },
    { key: "client", header: t("commercial.col.client"), render: (a) => a.client_name ?? "—" },
    { key: "resp", header: t("commercial.col.responsable"), render: (a) => a.responsable_email ?? "—" },
    { key: "statut", header: t("commercial.col.statut"), render: (a) => statut(a.status, a.status_label) },
    { key: "actions", header: "", render: (a) => <ActionBar actions={actionsAffaire(a, t)} /> },
  ];
  const colContrats: Column<Contrat>[] = [
    { key: "code", header: t("commercial.col.code"), render: (c) => c.code },
    { key: "profil", header: t("commercial.col.profil"), render: (c) => c.profile_label },
    { key: "client", header: t("commercial.col.client"), render: (c) => c.client_name ?? "—" },
    { key: "affaire", header: t("commercial.col.affaire"), render: (c) => c.affaire_title ?? "—" },
    { key: "montant", header: t("commercial.col.montantActuel"), num: true, render: (c) => montant(c.montant_actuel) },
    { key: "fin", header: t("commercial.col.echeance"), render: (c) => (c.end_date ? `${formatDate(c.end_date)} · ${c.expiry_status}` : "—") },
    { key: "avenants", header: t("commercial.col.avenants"), num: true, render: (c) => c.avenants_total },
    { key: "statut", header: t("commercial.col.statut"), render: (c) => statut(c.status, c.status_label) },
    { key: "actions", header: "", render: (c) => <ActionBar actions={actionsContrat(c, t)} /> },
  ];
  const colMarges: Column<LigneMarge & { id: string }>[] = [
    { key: "cle", header: t(`commercial.axe.${axe}`), render: (l) => l.cle },
    { key: "nb", header: t("commercial.col.affaires"), num: true, render: (l) => l.affaires },
    { key: "ca", header: t("commercial.col.caPrevu"), num: true, render: (l) => montant(l.ca_prevu) },
    { key: "mp", header: t("commercial.col.margePrevue"), num: true, render: (l) => montant(l.marge_prevue) },
    { key: "prod", header: t("commercial.col.produits"), num: true, render: (l) => montant(l.produits) },
    { key: "ch", header: t("commercial.col.charges"), num: true, render: (l) => montant(l.charges) },
    { key: "mr", header: t("commercial.col.margeReelle"), num: true, render: (l) => montant(l.marge_reelle) },
  ];

  return (
    <>
      <SectionCard title={`${t("commercial.offres")} · ${offres.count}`}>
        <PagedDataTable list={offres} columns={colOffres} caption={t("commercial.offres")} searchPlaceholder={t("commercial.searchOffres")} />
      </SectionCard>
      <SectionCard title={`${t("commercial.affaires")} · ${affaires.count}`}>
        <PagedDataTable list={affaires} columns={colAffaires} caption={t("commercial.affaires")} searchPlaceholder={t("commercial.searchAffaires")} />
      </SectionCard>
      <SectionCard title={`${t("commercial.contrats")} · ${contrats.count}`}>
        <PagedDataTable list={contrats} columns={colContrats} caption={t("commercial.contrats")} searchPlaceholder={t("commercial.searchContrats")} />
      </SectionCard>
      <SectionCard title={t("commercial.marges")}>
        <select value={axe} onChange={(e) => setAxe(e.target.value)} aria-label={t("commercial.marges")} style={{ marginBottom: "0.5rem" }}>
          {["client", "profil", "affaire", "responsable"].map((a) => (
            <option key={a} value={a}>
              {t(`commercial.axe.${a}`)}
            </option>
          ))}
        </select>
        <DataTable rows={marges.data ?? []} columns={colMarges} caption={t("commercial.marges")} />
      </SectionCard>
    </>
  );
}
