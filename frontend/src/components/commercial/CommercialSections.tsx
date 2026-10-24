import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate, formatMoney, formatNumber } from "../../lib/format";
import { usePagedList } from "../../lib/usePagedList";
import type { Paginated } from "../../types";
import { Badge, DataTable, PagedDataTable, SectionCard } from "../ui";
import type { ActionDef, Column } from "../ui";
import { actionsColumn } from "../ui/DataTable";

/** Clôture M1 : offres versionnées, affaires, contrats signés / avenants, marges par axe. */

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
  profile?: string;
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
/** Bande d'échéance du contrat (OK / J90…J0 / EXPIRED) → badge lisible, rien si le contrat n'approche pas de son terme. */
function Expiration({ status }: { status: string }) {
  const { t } = useTranslation();
  if (!status || status === "OK") return null;
  if (status === "EXPIRED")
    return (
      <span className="cell-sub">
        <Badge tone="err">{t("tableaux.commercial.expire")}</Badge>
      </span>
    );
  const jours = Number(status.replace(/^J/, ""));
  if (Number.isNaN(jours)) return null;
  return (
    <span className="cell-sub">
      <Badge tone={jours <= 15 ? "err" : "warn"}>{t("tableaux.commercial.echeanceDans", { n: jours })}</Badge>
    </span>
  );
}

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

  // Statut traduit d'après son code (le libellé serveur, en français, ne sert que de repli).
  const statut = (famille: "statutsOffre" | "statutsAffaire" | "statutsContrat", s: string, label: string) => (
    <Badge tone={TON[s] ?? "brand"}>{t(`revueR2.pipeline.${famille}.${s}`, { defaultValue: label })}</Badge>
  );

  const colOffres: Column<Offre>[] = [
    { key: "code", header: t("commercial.col.code"), render: (o) => <span className="cell-nowrap">{`${o.code} · v${o.version}`}</span>, sortValue: (o) => o.code },
    { key: "titre", header: t("commercial.col.titre"), render: (o) => o.title },
    { key: "client", header: t("commercial.col.client"), render: (o) => o.client_name ?? "—" },
    { key: "montant", header: t("commercial.col.montant"), num: true, render: (o) => montant(o.montant_offre), sortValue: (o) => (o.montant_offre === null ? null : Number(o.montant_offre)) },
    { key: "statut", header: t("commercial.col.statut"), render: (o) => statut("statutsOffre", o.status, o.status_label) },
    actionsColumn<Offre>(t("ui.actions"), (o) => actionsOffre(o, t)),
  ];
  const colAffaires: Column<Affaire>[] = [
    { key: "code", header: t("commercial.col.code"), render: (a) => <span className="cell-nowrap">{a.code}</span>, sortValue: (a) => a.code },
    { key: "titre", header: t("commercial.col.titre"), render: (a) => a.title },
    { key: "client", header: t("commercial.col.client"), render: (a) => a.client_name ?? "—" },
    { key: "resp", header: t("commercial.col.responsable"), render: (a) => a.responsable_email ?? "—" },
    { key: "statut", header: t("commercial.col.statut"), render: (a) => statut("statutsAffaire", a.status, a.status_label) },
    actionsColumn<Affaire>(t("ui.actions"), (a) => actionsAffaire(a, t)),
  ];
  const colContrats: Column<Contrat>[] = [
    // Profil contractuel en ligne secondaire sous le code : une colonne de moins, client et affaire respirent.
    {
      key: "code",
      header: t("commercial.col.code"),
      sortValue: (c) => c.code,
      render: (c) => (
        <>
          <span className="cell-nowrap">{c.code}</span>
          <span className="cell-sub cell-nowrap">
            {c.profile ? t(`revueR2.pipeline.profils.${c.profile}`, { defaultValue: c.profile_label }) : c.profile_label}
          </span>
        </>
      ),
    },
    // Client et affaire regroupés : l'intitulé d'affaire (long) passe en ligne secondaire au lieu d'écraser une colonne.
    {
      key: "client",
      header: t("revueR2.pipeline.clientAffaire"),
      width: "30%",
      sortValue: (c) => c.client_name,
      render: (c) => (
        <>
          {c.client_name ?? "—"}
          {c.affaire_title ? <span className="cell-sub">{c.affaire_title}</span> : null}
        </>
      ),
    },
    { key: "montant", header: t("commercial.col.montantActuel"), num: true, render: (c) => montant(c.montant_actuel), sortValue: (c) => (c.montant_actuel === null ? null : Number(c.montant_actuel)) },
    {
      key: "fin",
      header: t("commercial.col.echeance"),
      sortValue: (c) => c.end_date,
      render: (c) =>
        c.end_date ? (
          <>
            <span className="cell-nowrap">{formatDate(c.end_date)}</span>
            <Expiration status={c.expiry_status} />
          </>
        ) : (
          "—"
        ),
    },
    { key: "avenants", header: t("commercial.col.avenants"), num: true, render: (c) => formatNumber(c.avenants_total) },
    { key: "statut", header: t("commercial.col.statut"), render: (c) => statut("statutsContrat", c.status, c.status_label) },
    actionsColumn<Contrat>(t("ui.actions"), (c) => actionsContrat(c, t)),
  ];
  const colMarges: Column<LigneMarge & { id: string }>[] = [
    { key: "cle", header: t(`commercial.axe.${axe}`), render: (l) => l.cle },
    { key: "nb", header: t("commercial.col.affaires"), num: true, render: (l) => formatNumber(l.affaires), sortValue: (l) => l.affaires },
    { key: "ca", header: t("commercial.col.caPrevu"), num: true, render: (l) => montant(l.ca_prevu) },
    { key: "mp", header: t("commercial.col.margePrevue"), num: true, render: (l) => montant(l.marge_prevue) },
    { key: "prod", header: t("commercial.col.produits"), num: true, render: (l) => montant(l.produits) },
    { key: "ch", header: t("commercial.col.charges"), num: true, render: (l) => montant(l.charges) },
    { key: "mr", header: t("commercial.col.margeReelle"), num: true, render: (l) => montant(l.marge_reelle), sortValue: (l) => (l.marge_reelle === null ? null : Number(l.marge_reelle)) },
  ];

  return (
    <>
      <SectionCard title={`${t("commercial.offres")} · ${offres.count}`}>
        <PagedDataTable list={offres} columns={colOffres} maxHeight="none" caption={t("commercial.offres")} searchPlaceholder={t("commercial.searchOffres")} />
      </SectionCard>
      <SectionCard title={`${t("commercial.affaires")} · ${affaires.count}`}>
        <PagedDataTable list={affaires} columns={colAffaires} maxHeight="none" caption={t("commercial.affaires")} searchPlaceholder={t("commercial.searchAffaires")} />
      </SectionCard>
      <SectionCard title={`${t("commercial.contrats")} · ${contrats.count}`}>
        <PagedDataTable list={contrats} columns={colContrats} maxHeight="none" caption={t("commercial.contrats")} searchPlaceholder={t("commercial.searchContrats")} />
      </SectionCard>
      <SectionCard
        title={t("commercial.marges")}
        actions={
          <select className="control" value={axe} onChange={(e) => setAxe(e.target.value)} aria-label={t("commercial.marges")}>
            {["client", "profil", "affaire", "responsable"].map((a) => (
              <option key={a} value={a}>
                {t(`commercial.axe.${a}`)}
              </option>
            ))}
          </select>
        }
      >
        <DataTable rows={marges.data ?? []} columns={colMarges} caption={t("commercial.marges")} />
      </SectionCard>
    </>
  );
}
