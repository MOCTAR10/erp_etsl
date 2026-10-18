import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate } from "../../lib/format";
import { usePagedList } from "../../lib/usePagedList";
import type { Paginated } from "../../types";
import { DaLigneForm } from "../achats/AchatsSaisie";
import { useAnalytiques } from "../achats/refs";
import { ActionBar, Badge, PagedDataTable, QuickForm, SectionCard, type Column } from "../ui";

interface DemandeAchat {
  id: string;
  code: string;
  title: string;
  requester_name: string | null;
  department: string;
  expected_date: string | null;
  status: "brouillon" | "soumise" | "approuvee" | "rejetee" | "convertie";
  is_urgent: boolean;
  lines_count: number;
}

const TONE: Record<DemandeAchat["status"], "ok" | "warn" | "err" | "brand"> = {
  brouillon: "warn",
  soumise: "brand",
  approuvee: "ok",
  rejetee: "err",
  convertie: "ok",
};

/** Demandes d'achat : saisie + circuit soumettre → approuver / rejeter (validation hiérarchique côté API). */
export function DemandesAchat() {
  const { t } = useTranslation();
  const analytiques = useAnalytiques();
  const list = usePagedList<DemandeAchat>("achats-da", (q) => api.get<Paginated<DemandeAchat>>(`/api/achats/requests/${q}`));

  const columns: Column<DemandeAchat>[] = [
    { key: "code", header: t("purchases.da.code"), render: (d) => d.code },
    {
      key: "title",
      header: t("purchases.da.objet"),
      render: (d) => (
        <>
          {d.title} {d.is_urgent && <Badge tone="err">{t("purchases.da.urgente")}</Badge>}
        </>
      ),
    },
    { key: "req", header: t("purchases.da.demandeur"), render: (d) => d.requester_name ?? "—" },
    { key: "date", header: t("purchases.da.echeance"), render: (d) => (d.expected_date ? formatDate(d.expected_date) : "—") },
    {
      key: "status",
      header: t("purchases.da.statut"),
      render: (d) => (
        <>
          <Badge tone={TONE[d.status]}>{t(`purchases.da.status.${d.status}`)}</Badge>
          <ActionBar
            actions={[
              ...(d.status === "brouillon"
                ? [{ label: t("purchases.da.soumettre"), path: `/api/achats/requests/${d.id}/soumettre/`, tone: "ghost" as const }]
                : []),
              ...(d.status === "soumise"
                ? [
                    { label: t("actions.valider"), path: `/api/achats/requests/${d.id}/approuver/` },
                    {
                      label: t("actions.refuser"),
                      path: `/api/achats/requests/${d.id}/rejeter/`,
                      tone: "danger" as const,
                      prompt: { name: "motif", label: t("purchases.da.motif") },
                    },
                  ]
                : []),
            ]}
          />
        </>
      ),
    },
  ];

  return (
    <SectionCard title={`${t("purchases.da.title")} · ${list.count}`}>
      <QuickForm
        title={t("purchases.da.new")}
        endpoint="/api/achats/requests/"
        fields={[
          { name: "title", label: t("purchases.da.objet"), required: true },
          { name: "department", label: t("purchases.da.service") },
          { name: "expected_date", label: t("purchases.da.echeance"), type: "date" },
          {
            name: "is_urgent",
            label: t("purchases.da.urgente"),
            type: "select",
            defaultValue: "false",
            required: true,
            options: [
              { value: "false", label: t("purchases.da.non") },
              { value: "true", label: t("purchases.da.oui") },
            ],
          },
          { name: "analytic", label: t("achatsSaisie.f.analytique"), type: "select", options: analytiques },
          { name: "notes", label: t("purchases.da.notes"), type: "textarea" },
        ]}
        transform={(v) => ({ ...v, is_urgent: v.is_urgent === "true" })}
      />
      <DaLigneForm />
      {(list.count > 0 || list.search) && (
        <PagedDataTable list={list} columns={columns} caption={t("purchases.da.title")} searchPlaceholder={t("purchases.da.search")} />
      )}
    </SectionCard>
  );
}
