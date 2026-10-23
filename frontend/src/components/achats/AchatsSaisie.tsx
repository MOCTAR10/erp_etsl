import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate, formatMoney } from "../../lib/format";
import { useFiltresListe } from "../../lib/useFiltresListe";
import { usePagedList } from "../../lib/usePagedList";
import type { Paginated } from "../../types";
import { ActionBar, Badge, FilterBar, PagedDataTable, QuickForm, SectionCard, type ActionDef, type Column } from "../ui";
import { actionsColumn } from "../ui/DataTable";
import { useAnalytiques, useRefOptions } from "./refs";

type Tone = "ok" | "warn" | "err" | "brand";
const TONE: Record<string, Tone> = {
  brouillon: "brand", ouverte: "warn", cloturee: "ok", confirmee: "warn", partielle: "warn",
  annulee: "err", en_attente: "warn", rapprochee: "brand", comptabilisee: "ok",
};

interface Consultation { id: string; code: string; subject: string; request_code: string | null; status: string; offers_total: number; due_date: string | null }
interface Offre { id: string; consultation_code: string; supplier_name: string | null; amount: string | null; delivery_days: number | null; is_selected: boolean }
interface Commande { id: string; code: string; supplier_name: string | null; order_date: string; status: string; is_global_rental: boolean; total: string | null; lines_count: number }
interface Facture { id: string; code: string; order_code: string; supplier_name: string | null; invoice_ref: string; invoice_date: string; status: string; total: string | null; total_tva: string | null; total_ttc: string | null; move_number: string | null }

const montant = (v: string | null) => (v === null ? "••••••" : formatMoney(v));
const num = (v: string | undefined) => (v === undefined ? undefined : Number(v));

function StatusBadge({ status }: { status: string }) {
  const { t } = useTranslation();
  return <Badge tone={TONE[status] ?? "brand"}>{t(`achatsSaisie.status.${status}`)}</Badge>;
}

const useFournisseurs = () =>
  useRefOptions<{ id: string; code: string; name: string }>("fournisseurs", "/api/referentiels/partners/", (p) => `${p.code} — ${p.name}`);
const useArticles = () =>
  useRefOptions<{ id: string; code: string; label: string }>("articles", "/api/referentiels/articles/", (a) => `${a.code} — ${a.label}`);
const useDaApprouvees = () =>
  useRefOptions<{ id: string; code: string; title: string }>("da-approuvees", "/api/achats/requests/?status=approuvee", (d) => `${d.code} — ${d.title}`);

/** Ligne de DA (formulaire ajouté à la section « Demandes d'achat »). */
export function DaLigneForm() {
  const { t } = useTranslation();
  const das = useRefOptions<{ id: string; code: string; title: string }>("da-brouillon", "/api/achats/requests/?status=brouillon", (d) => `${d.code} — ${d.title}`);
  const articles = useArticles();
  return (
    <QuickForm
      title={t("achatsSaisie.newDaLigne")}
      endpoint="/api/achats/request-lines/"
      fields={[
        { name: "request", label: t("achatsSaisie.f.daBrouillon"), type: "select", required: true, options: das },
        { name: "article", label: t("achatsSaisie.f.article"), type: "select", options: articles },
        { name: "label", label: t("achatsSaisie.f.designation"), required: true },
        { name: "quantity", label: t("achatsSaisie.f.quantite"), type: "number", step: "0.01", min: 0, required: true, defaultValue: "1" },
        { name: "estimated_price", label: t("achatsSaisie.f.prixUnitaire"), type: "number", step: "0.01", min: 0 },
      ]}
      transform={(v) => ({ ...v, quantity: num(v.quantity), estimated_price: num(v.estimated_price) })}
    />
  );
}

function ConsultationsSection() {
  const { t } = useTranslation();
  const consultations = usePagedList<Consultation>("achats-consultations", (q) => api.get<Paginated<Consultation>>(`/api/achats/consultations/${q}`));
  const offres = usePagedList<Offre>("achats-offres", (q) => api.get<Paginated<Offre>>(`/api/achats/consultation-offers/${q}`));
  const das = useDaApprouvees();
  const fournisseurs = useFournisseurs();
  const ouvertes = useRefOptions<{ id: string; code: string; subject: string }>("consultations-ouvertes", "/api/achats/consultations/?status=ouverte", (c) => `${c.code} — ${c.subject}`);

  const colC: Column<Consultation>[] = [
    { key: "code", header: t("achatsSaisie.col.code"), render: (c) => c.code },
    { key: "subject", header: t("achatsSaisie.col.objet"), render: (c) => c.subject },
    { key: "da", header: t("achatsSaisie.col.da"), render: (c) => c.request_code ?? "—" },
    { key: "due", header: t("achatsSaisie.col.echeance"), render: (c) => (c.due_date ? formatDate(c.due_date) : "—") },
    { key: "offres", header: t("achatsSaisie.col.offres"), num: true, render: (c) => c.offers_total },
    {
      key: "status",
      header: t("achatsSaisie.col.statut"),
      render: (c) => <StatusBadge status={c.status} />,
    },
    actionsColumn<Consultation>(t("listes.col.actions"), (c) => [
      ...(c.status === "brouillon" ? [{ label: t("achatsSaisie.ouvrir"), path: `/api/achats/consultations/${c.id}/ouvrir/` }] : []),
      ...(c.status === "ouverte" ? [{ label: t("achatsSaisie.cloturer"), path: `/api/achats/consultations/${c.id}/cloturer/` }] : []),
    ]),
  ];
  const colO: Column<Offre>[] = [
    { key: "consultation", header: t("achatsSaisie.col.consultation"), render: (o) => o.consultation_code },
    { key: "fournisseur", header: t("achatsSaisie.col.fournisseur"), render: (o) => o.supplier_name ?? "—" },
    { key: "montant", header: t("achatsSaisie.col.montant"), num: true, render: (o) => montant(o.amount) },
    { key: "delai", header: t("achatsSaisie.col.delai"), num: true, render: (o) => o.delivery_days ?? "—" },
    {
      key: "retenue",
      header: t("achatsSaisie.col.retenue"),
      render: (o) =>
        o.is_selected ? (
          <Badge tone="ok">{t("achatsSaisie.retenue")}</Badge>
        ) : (
          <ActionBar actions={[{ label: t("achatsSaisie.retenir"), path: `/api/achats/consultation-offers/${o.id}/retenir/`, tone: "ghost" }]} />
        ),
    },
  ];

  return (
    <SectionCard
      title={`${t("achatsSaisie.consultations")} · ${consultations.count}`}
      actions={
        <div className="section-actions">
      <QuickForm
        title={t("achatsSaisie.newConsultation")}
        endpoint="/api/achats/consultations/"
        fields={[
          { name: "subject", label: t("achatsSaisie.f.objet"), required: true },
          { name: "request", label: t("achatsSaisie.f.da"), type: "select", options: das },
          { name: "due_date", label: t("achatsSaisie.f.dateLimite"), type: "date" },
        ]}
      />
      <QuickForm
        title={t("achatsSaisie.newOffre")}
        endpoint="/api/achats/consultation-offers/"
        fields={[
          { name: "consultation", label: t("achatsSaisie.f.consultation"), type: "select", required: true, options: ouvertes },
          { name: "supplier", label: t("achatsSaisie.f.fournisseur"), type: "select", required: true, options: fournisseurs },
          { name: "amount", label: t("achatsSaisie.f.montant"), type: "number", step: "0.01", min: 0, required: true },
          { name: "delivery_days", label: t("achatsSaisie.f.delai"), type: "number", min: 0 },
        ]}
        transform={(v) => ({ ...v, amount: num(v.amount), delivery_days: num(v.delivery_days) })}
      />
        </div>
      }
    >
      {(consultations.count > 0 || consultations.search) && (
        <PagedDataTable list={consultations} columns={colC} caption={t("achatsSaisie.consultations")} searchPlaceholder={t("achatsSaisie.searchConsultations")} />
      )}
      {(offres.count > 0 || offres.search) && (
        <PagedDataTable list={offres} columns={colO} caption={t("achatsSaisie.newOffre")} searchPlaceholder={t("achatsSaisie.searchOffres")} />
      )}
    </SectionCard>
  );
}

function CommandesSection() {
  const { t } = useTranslation();
  const filtresBc = useFiltresListe("/api/achats/orders/");
  const commandes = usePagedList<Commande>("achats-bc-saisie", (q) => api.get<Paginated<Commande>>(`/api/achats/orders/${q}`), {
    extra: filtresBc.extra,
  });
  const fournisseurs = useFournisseurs();
  const das = useDaApprouvees();
  const analytiques = useAnalytiques();
  const articles = useArticles();
  const consultations = useRefOptions<{ id: string; code: string; subject: string }>("consultations-cloturees", "/api/achats/consultations/?status=cloturee", (c) => `${c.code} — ${c.subject}`);
  const brouillons = useRefOptions<{ id: string; code: string; supplier_name: string | null }>("bc-brouillon", "/api/achats/orders/?status=brouillon", (o) => `${o.code} — ${o.supplier_name ?? "—"}`);

  const actions = (o: Commande): ActionDef[] => {
    const base = `/api/achats/orders/${o.id}`;
    if (o.status === "brouillon")
      return [
        { label: t("achatsSaisie.confirmer"), path: `${base}/confirmer/` },
        { label: t("achatsSaisie.visaDg"), path: `${base}/visa-dg/`, tone: "ghost", prompt: { name: "motif", label: t("achatsSaisie.motifVisa") } },
        { label: t("achatsSaisie.annuler"), path: `${base}/annuler/`, tone: "danger", confirm: t("achatsSaisie.confirmAnnuler") },
      ];
    if (o.status === "confirmee" || o.status === "partielle")
      return [{ label: t("achatsSaisie.annuler"), path: `${base}/annuler/`, tone: "danger", confirm: t("achatsSaisie.confirmAnnuler") }];
    return [];
  };
  const cols: Column<Commande>[] = [
    { key: "code", header: t("achatsSaisie.col.code"), sortValue: (o) => o.code, render: (o) => <>{o.code} {o.is_global_rental && <Badge tone="brand" title={t("purchases.gr")}>GR</Badge>}</> },
    { key: "fournisseur", header: t("achatsSaisie.col.fournisseur"), render: (o) => o.supplier_name ?? "—" },
    { key: "date", header: t("achatsSaisie.col.date"), render: (o) => formatDate(o.order_date) },
    { key: "total", header: t("achatsSaisie.col.total"), num: true, render: (o) => montant(o.total) },
    { key: "status", header: t("achatsSaisie.col.statut"), render: (o) => <StatusBadge status={o.status} /> },
    actionsColumn<Commande>(t("listes.col.actions"), actions),
  ];
  const ouiNon = [
    { value: "false", label: t("achatsSaisie.f.non") },
    { value: "true", label: t("achatsSaisie.f.oui") },
  ];

  return (
    <SectionCard
      title={`${t("achatsSaisie.commandes")} · ${commandes.count}`}
      actions={
        <div className="section-actions">
      <QuickForm
        title={t("achatsSaisie.newBc")}
        endpoint="/api/achats/orders/"
        fields={[
          { name: "supplier", label: t("achatsSaisie.f.fournisseur"), type: "select", required: true, options: fournisseurs },
          { name: "request", label: t("achatsSaisie.f.da"), type: "select", options: das },
          { name: "consultation", label: t("achatsSaisie.f.consultation"), type: "select", options: consultations },
          { name: "expected_date", label: t("achatsSaisie.f.livraison"), type: "date" },
          { name: "analytic", label: t("achatsSaisie.f.analytique"), type: "select", options: analytiques },
          { name: "is_global_rental", label: t("achatsSaisie.f.gr"), type: "select", required: true, defaultValue: "false", options: ouiNon },
          { name: "notes", label: t("achatsSaisie.f.notes"), type: "textarea" },
        ]}
        transform={(v) => ({ ...v, is_global_rental: v.is_global_rental === "true" })}
      />
      <QuickForm
        title={t("achatsSaisie.newBcLigne")}
        endpoint="/api/achats/order-lines/"
        fields={[
          { name: "purchase_order", label: t("achatsSaisie.f.bc"), type: "select", required: true, options: brouillons },
          { name: "article", label: t("achatsSaisie.f.article"), type: "select", options: articles },
          { name: "label", label: t("achatsSaisie.f.designation"), required: true },
          { name: "quantity", label: t("achatsSaisie.f.quantite"), type: "number", step: "0.01", min: 0, required: true, defaultValue: "1" },
          { name: "unit_price", label: t("achatsSaisie.f.prixUnitaire"), type: "number", step: "0.01", min: 0, required: true },
        ]}
        transform={(v) => ({ ...v, quantity: num(v.quantity), unit_price: num(v.unit_price) })}
      />
        </div>
      }
    >
      <FilterBar defs={filtresBc.defs} value={filtresBc.criteres} onChange={filtresBc.setCriteres} idPrefix="bc-f" />
      {(commandes.count > 0 || commandes.search || filtresBc.extra) && (
        <PagedDataTable list={commandes} columns={cols} caption={t("achatsSaisie.commandes")} searchPlaceholder={t("achatsSaisie.searchCommandes")} />
      )}
    </SectionCard>
  );
}

function FacturesSection() {
  const { t } = useTranslation();
  const filtresFf = useFiltresListe("/api/achats/invoices/");
  const factures = usePagedList<Facture>("achats-factures", (q) => api.get<Paginated<Facture>>(`/api/achats/invoices/${q}`), {
    extra: filtresFf.extra,
  });
  const fournisseurs = useFournisseurs();
  const commandes = useRefOptions<{ id: string; code: string; supplier_name: string | null }>(
    "bc-facturables", "/api/achats/orders/", (o) => `${o.code} — ${o.supplier_name ?? "—"}`,
  );
  const enAttente = useRefOptions<{ id: string; code: string; invoice_ref: string }>(
    "factures-en-attente", "/api/achats/invoices/?status=en_attente", (f) => `${f.code} — ${f.invoice_ref || "—"}`,
  );
  const lignesBc = useRefOptions<{ id: string; order_code: string; label: string; quantity: string }>(
    "lignes-bc", "/api/achats/order-lines/", (l) => `${l.order_code} · ${l.label} × ${l.quantity}`,
  );
  const taux = useRefOptions<{ id: string; code: string; taux: string }>("taux-tva", "/api/comptabilite/taux-tva/", (x) => `${x.code} — ${x.taux} %`);

  const actions = (f: Facture): ActionDef[] => {
    const base = `/api/achats/invoices/${f.id}`;
    if (f.status === "en_attente") return [{ label: t("achatsSaisie.rapprocher"), path: `${base}/rapprocher/` }];
    if (f.status === "rapprochee")
      return [{ label: t("achatsSaisie.comptabiliser"), path: `${base}/comptabiliser/`, confirm: t("achatsSaisie.confirmComptabiliser") }];
    return [];
  };
  const cols: Column<Facture>[] = [
    { key: "code", header: t("achatsSaisie.col.code"), render: (f) => `${f.code} · ${f.order_code}` },
    { key: "ref", header: t("achatsSaisie.col.reference"), render: (f) => f.invoice_ref || "—" },
    { key: "fournisseur", header: t("achatsSaisie.col.fournisseur"), render: (f) => f.supplier_name ?? "—" },
    { key: "date", header: t("achatsSaisie.col.date"), render: (f) => formatDate(f.invoice_date) },
    { key: "ht", header: t("achatsSaisie.col.total"), num: true, render: (f) => montant(f.total) },
    { key: "tva", header: t("achatsSaisie.col.tva"), num: true, render: (f) => montant(f.total_tva) },
    { key: "ttc", header: t("achatsSaisie.col.ttc"), num: true, render: (f) => montant(f.total_ttc) },
    { key: "ecr", header: t("achatsSaisie.col.ecriture"), render: (f) => f.move_number ?? "—" },
    { key: "status", header: t("achatsSaisie.col.statut"), render: (f) => <StatusBadge status={f.status} /> },
    actionsColumn<Facture>(t("listes.col.actions"), actions),
  ];

  return (
    <SectionCard
      title={`${t("achatsSaisie.factures")} · ${factures.count}`}
      actions={
        <div className="section-actions">
      <QuickForm
        title={t("achatsSaisie.newFacture")}
        endpoint="/api/achats/invoices/"
        fields={[
          { name: "purchase_order", label: t("achatsSaisie.f.bc"), type: "select", required: true, options: commandes },
          { name: "supplier", label: t("achatsSaisie.f.fournisseur"), type: "select", options: fournisseurs },
          { name: "invoice_ref", label: t("achatsSaisie.f.referenceFacture") },
          { name: "invoice_date", label: t("achatsSaisie.f.dateFacture"), type: "date", defaultValue: new Date().toISOString().slice(0, 10) },
        ]}
      />
      <QuickForm
        title={t("achatsSaisie.newFactureLigne")}
        endpoint="/api/achats/invoice-lines/"
        fields={[
          { name: "invoice", label: t("achatsSaisie.f.facture"), type: "select", required: true, options: enAttente },
          { name: "purchase_order_line", label: t("achatsSaisie.f.ligneBc"), type: "select", required: true, options: lignesBc },
          { name: "quantity", label: t("achatsSaisie.f.quantite"), type: "number", step: "0.01", min: 0, required: true },
          { name: "unit_price", label: t("achatsSaisie.f.prixUnitaire"), type: "number", step: "0.01", min: 0, required: true },
          { name: "taux_tva", label: t("achatsSaisie.f.tauxTva"), type: "select", options: taux },
        ]}
        transform={(v) => ({ ...v, quantity: num(v.quantity), unit_price: num(v.unit_price) })}
      />
        </div>
      }
    >
      <FilterBar defs={filtresFf.defs} value={filtresFf.criteres} onChange={filtresFf.setCriteres} idPrefix="ff-f" />
      {(factures.count > 0 || factures.search || filtresFf.extra) && (
        <PagedDataTable list={factures} columns={cols} caption={t("achatsSaisie.factures")} searchPlaceholder={t("achatsSaisie.searchFactures")} />
      )}
    </SectionCard>
  );
}

/** Saisie et actions M2 jusque-là réservées à l'API : consultations/offres, bons de commande, factures fournisseurs. */
export function AchatsSaisie() {
  return (
    <>
      <ConsultationsSection />
      <CommandesSection />
      <FacturesSection />
    </>
  );
}
