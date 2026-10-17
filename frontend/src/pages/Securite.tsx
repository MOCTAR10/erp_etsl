import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { ActionBar, Badge, DataTable, EmptyState, PageHeader, QuickForm, SectionCard } from "../components/ui";
import type { Column } from "../components/ui";
import { formatDate, formatDateTime } from "../lib/format";
import { useAuth } from "../store/auth";
import type { Delegation, JournalAcces, Me, Paginated } from "../types";

const EVENEMENTS = [
  "connexion",
  "echec_connexion",
  "connexion_bloquee",
  "mfa_enrolement",
  "mfa_succes",
  "mfa_echec",
  "mfa_reinitialisation",
  "export",
];

/** Sécurité (lot 15b) : MFA du compte, délégations temporaires (EX-G-02), journal des accès pour l'admin (EX-G-10). */
export function SecuritePage() {
  const { t } = useTranslation();
  const user = useAuth((s) => s.user) as (Me & { mfa_active?: boolean; mfa_requise?: boolean }) | null;
  const admin = user?.role === "admin";
  const [evenement, setEvenement] = useState("");

  const delegations = useQuery({
    queryKey: ["delegations"],
    queryFn: () => api.get<Paginated<Delegation>>("/api/workflow/delegations/?page_size=50"),
    select: (page) => page.results,
  });
  const journal = useQuery({
    queryKey: ["journal-acces", evenement],
    queryFn: () =>
      api.get<Paginated<JournalAcces>>(`/api/users/journal-acces/?page_size=100${evenement ? `&evenement=${evenement}` : ""}`),
    select: (page) => page.results,
    enabled: admin,
  });

  const delegationColumns: Column<Delegation>[] = [
    { key: "code", header: "Code", render: (d) => d.code },
    { key: "qui", header: t("securite.delegataire"), render: (d) => `${d.delegant_email} → ${d.delegataire_email}` },
    { key: "periode", header: `${t("securite.du")} / ${t("securite.au")}`, render: (d) => `${formatDate(d.date_debut)} → ${formatDate(d.date_fin)}` },
    { key: "motif", header: t("securite.motif"), render: (d) => d.motif },
    {
      key: "etat",
      header: "",
      render: (d) => (
        <>
          <Badge tone={d.active ? "ok" : "neutral"}>{d.active ? t("securite.active") : t("securite.inactive")}</Badge>
          {!d.annulee_le && d.delegant_email === user?.email ? (
            <ActionBar
              actions={[
                {
                  label: t("securite.annuler"),
                  path: `/api/workflow/delegations/${d.id}/annuler/`,
                  tone: "danger",
                  confirm: t("securite.confirmAnnuler"),
                },
              ]}
            />
          ) : null}
        </>
      ),
    },
  ];
  const journalColumns: Column<JournalAcces>[] = [
    { key: "quand", header: t("securite.col.quand"), render: (j) => formatDateTime(j.cree_le) },
    { key: "evenement", header: t("securite.col.evenement"), render: (j) => j.evenement_label },
    { key: "compte", header: t("securite.col.compte"), render: (j) => j.email || "—" },
    { key: "ip", header: t("securite.col.ip"), render: (j) => j.ip ?? "—" },
    { key: "ressource", header: t("securite.col.ressource"), render: (j) => j.chemin },
  ];

  return (
    <>
      <PageHeader title={t("securite.title")} />

      <SectionCard title={t("securite.mfa")}>
        <p>
          <Badge tone={user?.mfa_active ? "ok" : user?.mfa_requise ? "warn" : "neutral"}>
            {user?.mfa_active ? t("securite.mfaActive") : t("securite.mfaInactive")}
          </Badge>{" "}
          {user?.mfa_requise ? <span className="muted">{t("securite.mfaRequise")}</span> : null}
        </p>
      </SectionCard>

      <SectionCard title={t("securite.delegations")}>
        <p className="muted">{t("securite.delegationsIntro")}</p>
        <QuickForm
          title={t("securite.nouvelle")}
          endpoint="/api/workflow/delegations/"
          fields={[
            { name: "email_delegataire", label: t("securite.delegataire"), required: true },
            { name: "date_debut", label: t("securite.du"), type: "date", required: true },
            { name: "date_fin", label: t("securite.au"), type: "date", required: true },
            { name: "motif", label: t("securite.motif"), required: true },
          ]}
        />
        {(delegations.data?.length ?? 0) === 0 ? (
          <EmptyState label={t("securite.aucune")} />
        ) : (
          <DataTable rows={delegations.data ?? []} columns={delegationColumns} caption={t("securite.delegations")} />
        )}
      </SectionCard>

      {admin ? (
        <SectionCard title={t("securite.journal")}>
          <p className="muted">{t("securite.journalIntro")}</p>
          <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.5rem", flexWrap: "wrap" }}>
            <select value={evenement} onChange={(e) => setEvenement(e.target.value)} aria-label={t("securite.col.evenement")}>
              <option value="">{t("securite.tous")}</option>
              {EVENEMENTS.map((e) => (
                <option key={e} value={e}>
                  {e}
                </option>
              ))}
            </select>
            <button
              type="button"
              className="btn ghost"
              onClick={() => void api.download(`/api/users/journal-acces/?export=csv${evenement ? `&evenement=${evenement}` : ""}`, "journal_acces.csv")}
            >
              {t("securite.exporter")}
            </button>
          </div>
          <DataTable rows={journal.data ?? []} columns={journalColumns} caption={t("securite.journal")} />
        </SectionCard>
      ) : null}
    </>
  );
}
