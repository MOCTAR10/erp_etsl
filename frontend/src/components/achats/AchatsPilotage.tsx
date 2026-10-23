import { useQuery } from "@tanstack/react-query";
import type { CSSProperties } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate, formatMoney, formatNumber } from "../../lib/format";
import { usePagedList } from "../../lib/usePagedList";
import type { Paginated } from "../../types";
import { Badge, DataTable, PagedDataTable, QuickForm, SectionCard } from "../ui";
import type { ActionDef, Column } from "../ui";
import { actionsColumn } from "../ui/DataTable";
import { useRefOptions } from "./refs";

/** Clôture M2 : réceptions sous contrôle qualité, litiges fournisseurs, notation et reporting achats (CDC §5.4-§5.11). */

interface Reception {
  id: string;
  code: string;
  order_code: string;
  received_at: string;
  status: string;
  status_label: string;
  controle_qualite: { code: string; statut: string; resultat: string } | null;
}
interface Litige {
  id: string;
  code: string;
  order_code: string;
  fournisseur_name: string | null;
  type?: string;
  type_label: string;
  statut: string;
  statut_label: string;
  nb_relances: number;
  contentieux_code: string | null;
}
interface Fournisseur {
  fournisseur_id: string;
  fournisseur: string;
  commandes: number;
  taux_service: number | null;
  retard_moyen_jours: number | null;
  taux_conformite: number | null;
  litiges_ouverts: number;
  note: number | null;
}
interface Reporting {
  prix_moyens: { article: string; libelle: string; quantite: string; prix_moyen: string | null }[];
  engagements: { axe: string; libelle: string; engage: string | null }[];
}

const pct = (v: number | null) => (v === null ? "—" : `${Math.round(v * 100)} %`);
const montant = (v: string | null) => (v === null ? "••••••" : formatMoney(v));
/** Codes de pièce et dates : jamais coupés en fin de ligne. */
const NOWRAP: CSSProperties = { whiteSpace: "nowrap" };

function actionsLitige(l: Litige, t: (k: string) => string): ActionDef[] {
  if (l.statut === "resolu") return [];
  const base = `/api/achats/litiges/${l.id}`;
  const out: ActionDef[] = [{ label: t("achatsPilotage.relancer"), path: `${base}/relancer/`, tone: "ghost" }];
  if (!l.contentieux_code)
    out.push({ label: t("achatsPilotage.escalader"), path: `${base}/escalader/`, tone: "danger", confirm: t("achatsPilotage.confirmEscalader") });
  out.push({ label: t("achatsPilotage.resoudre"), path: `${base}/resoudre/`, prompt: { name: "resolution", label: t("achatsPilotage.resolution") } });
  return out;
}

export function AchatsPilotage() {
  const { t } = useTranslation();
  const receptions = usePagedList<Reception>("achats-receptions", (q) => api.get<Paginated<Reception>>(`/api/achats/receipts/${q}`));
  const depotsQuery = useQuery({
    queryKey: ["achats-ref", "depots"],
    queryFn: () => api.listAll<{ id: string; code: string; label: string; is_active: boolean }>("/api/stocks/depots/"),
    retry: 0,
  });
  const depots = (depotsQuery.data ?? []).filter((d) => d.is_active).map((d) => ({ value: d.id, label: `${d.code} — ${d.label}` }));
  const litiges = usePagedList<Litige>("achats-litiges", (q) => api.get<Paginated<Litige>>(`/api/achats/litiges/${q}`));
  // Choix du BC par code (et non par identifiant technique) dans le formulaire de litige.
  const commandes = useRefOptions<{ id: string; code: string; supplier_name: string | null }>(
    "bc-litiges", "/api/achats/orders/", (o) => `${o.code} — ${o.supplier_name ?? "—"}`,
  );
  const reporting = useQuery({
    queryKey: ["achats-reporting"],
    queryFn: () => api.get<Reporting & { fournisseurs: Fournisseur[] }>("/api/achats/orders/reporting/"),
  });

  const colReceptions: Column<Reception>[] = [
    { key: "code", header: t("achatsPilotage.col.reception"), render: (r) => <span style={NOWRAP}>{`${r.code} · ${r.order_code}`}</span> },
    { key: "date", header: t("achatsPilotage.col.date"), render: (r) => <span style={NOWRAP}>{formatDate(r.received_at)}</span> },
    {
      key: "qc",
      header: t("achatsPilotage.col.controle"),
      render: (r) => {
        const qc = r.controle_qualite;
        if (!qc) return "—";
        // Résultat (ou, à défaut, statut) du contrôle traduit d'après son code.
        const etat = qc.resultat
          ? t(`revueR2.purchases.resultats.${qc.resultat}`, { defaultValue: qc.resultat })
          : t(`revueR2.purchases.qcStatuts.${qc.statut}`, { defaultValue: qc.statut });
        return (
          <Badge tone={qc.resultat === "non_conforme" ? "err" : qc.statut === "valide" ? "ok" : "warn"}>
            <span style={NOWRAP}>{`${qc.code} · ${etat}`}</span>
          </Badge>
        );
      },
    },
    {
      key: "statut",
      header: t("achatsPilotage.col.statut"),
      render: (r) => (
        <Badge tone={r.status === "valide" ? "ok" : r.status === "annule" ? "neutral" : "warn"}>
          {t(`revueR2.purchases.receptionStatuts.${r.status}`, { defaultValue: r.status_label })}
        </Badge>
      ),
    },
    actionsColumn<Reception>(t("ui.actions"), (r) =>
      r.status === "en_attente"
        ? [
            {
              label: t("achatsPilotage.validerReception"),
              path: `/api/achats/receipts/${r.id}/valider/`,
              // Plusieurs dépôts actifs : la mise en stock exige de choisir le dépôt de réception.
              ...(depots.length > 1 ? { prompt: { name: "depot", label: t("achatsSaisie.depot"), options: depots } } : {}),
            },
          ]
        : [],
    ),
  ];
  const colLitiges: Column<Litige>[] = [
    {
      key: "code",
      header: t("achatsPilotage.col.litige"),
      render: (l) => (
        <>
          <span style={NOWRAP}>{l.code}</span>
          <span className="cell-sub" style={NOWRAP}>
            {l.order_code}
          </span>
        </>
      ),
    },
    { key: "fournisseur", header: t("achatsPilotage.col.fournisseur"), render: (l) => l.fournisseur_name ?? "—" },
    { key: "type", header: t("achatsPilotage.col.type"), render: (l) => (l.type ? t(`achatsPilotage.types.${l.type}`, { defaultValue: l.type_label }) : l.type_label) },
    { key: "relances", header: t("achatsPilotage.col.relances"), num: true, render: (l) => l.nb_relances },
    {
      key: "statut",
      header: t("achatsPilotage.col.statut"),
      render: (l) => (
        <>
          <Badge tone={l.statut === "resolu" ? "ok" : l.statut === "escalade" ? "err" : "warn"}>
            {t(`revueR2.purchases.litigeStatuts.${l.statut}`, { defaultValue: l.statut_label })}
          </Badge>
          {l.contentieux_code ? (
            <span className="cell-sub" style={NOWRAP}>
              {l.contentieux_code}
            </span>
          ) : null}
        </>
      ),
    },
    // Une action principale (Résoudre) + les autres dans « ⋯ » : plus de boutons empilés sur trois lignes.
    actionsColumn<Litige>(t("ui.actions"), (l) => actionsLitige(l, t), () => t("achatsPilotage.resoudre")),
  ];
  const colFournisseurs: Column<Fournisseur & { id: string }>[] = [
    { key: "nom", header: t("achatsPilotage.col.fournisseur"), render: (f) => f.fournisseur },
    { key: "note", header: t("achatsPilotage.col.note"), num: true, render: (f) => (f.note === null ? "—" : `${f.note}/100`) },
    { key: "bc", header: t("achatsPilotage.col.commandes"), num: true, render: (f) => f.commandes },
    { key: "service", header: t("achatsPilotage.col.service"), num: true, render: (f) => pct(f.taux_service) },
    { key: "retard", header: t("achatsPilotage.col.retard"), num: true, render: (f) => (f.retard_moyen_jours === null ? "—" : `${f.retard_moyen_jours} j`) },
    { key: "qualite", header: t("achatsPilotage.col.conformite"), num: true, render: (f) => pct(f.taux_conformite) },
    { key: "litiges", header: t("achatsPilotage.col.litiges"), num: true, render: (f) => f.litiges_ouverts },
  ];
  const colPrix: Column<Reporting["prix_moyens"][number] & { id: string }>[] = [
    { key: "article", header: t("achatsPilotage.col.article"), render: (p) => `${p.article} · ${p.libelle}` },
    { key: "qte", header: t("achatsPilotage.col.quantite"), num: true, render: (p) => formatNumber(p.quantite) },
    { key: "prix", header: t("achatsPilotage.col.prixMoyen"), num: true, render: (p) => montant(p.prix_moyen) },
  ];
  const colEngagements: Column<Reporting["engagements"][number] & { id: string }>[] = [
    { key: "axe", header: t("achatsPilotage.col.axe"), render: (e) => (e.axe && e.axe !== "—" ? `${e.axe} · ${e.libelle}` : e.libelle) },
    { key: "engage", header: t("achatsPilotage.col.engage"), num: true, render: (e) => montant(e.engage) },
  ];

  const r = reporting.data;
  return (
    <>
      <SectionCard title={`${t("achatsPilotage.receptions")} · ${receptions.count}`}>
        <p className="muted">{t("achatsPilotage.receptionsIntro")}</p>
        <PagedDataTable list={receptions} columns={colReceptions} maxHeight="none" caption={t("achatsPilotage.receptions")} searchPlaceholder={t("achatsPilotage.searchReceptions")} />
      </SectionCard>
      <SectionCard
        title={`${t("achatsPilotage.litiges")} · ${litiges.count}`}
        actions={
          <div className="section-actions">
        <QuickForm
          title={t("achatsPilotage.nouveauLitige")}
          endpoint="/api/achats/litiges/"
          fields={[
            { name: "purchase_order", label: t("achatsPilotage.bc"), type: "select", required: true, options: commandes },
            {
              name: "type",
              label: t("achatsPilotage.col.type"),
              type: "select",
              required: true,
              options: ["quantite", "qualite", "prix", "delai", "autre"].map((v) => ({ value: v, label: t(`achatsPilotage.types.${v}`) })),
            },
            { name: "description", label: t("achatsPilotage.description"), type: "textarea", required: true },
            { name: "montant_en_jeu", label: t("achatsPilotage.montant"), type: "number" },
          ]}
        />
          </div>
        }
      >
        <PagedDataTable list={litiges} columns={colLitiges} maxHeight="none" caption={t("achatsPilotage.litiges")} searchPlaceholder={t("achatsPilotage.searchLitiges")} />
      </SectionCard>
      <SectionCard title={t("achatsPilotage.fournisseurs")}>
        <DataTable rows={(r?.fournisseurs ?? []).map((f) => ({ ...f, id: f.fournisseur_id }))} columns={colFournisseurs} caption={t("achatsPilotage.fournisseurs")} />
      </SectionCard>
      <SectionCard title={t("achatsPilotage.reporting")}>
        <h4>{t("revueR2.purchases.prixMoyens")}</h4>
        <DataTable rows={(r?.prix_moyens ?? []).map((p) => ({ ...p, id: p.article }))} columns={colPrix} caption={t("revueR2.purchases.prixMoyens")} />
        <h4>{t("revueR2.purchases.engagements")}</h4>
        <DataTable rows={(r?.engagements ?? []).map((e) => ({ ...e, id: e.axe }))} columns={colEngagements} caption={t("revueR2.purchases.engagements")} />
      </SectionCard>
    </>
  );
}
