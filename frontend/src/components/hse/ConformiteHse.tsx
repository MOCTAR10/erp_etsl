import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { ActionBar, Badge, PagedDataGrid, QuickForm, SectionCard } from "../ui";
import type { ActionDef } from "../ui";
import type { Column } from "../ui";
import { formatDate } from "../../lib/format";
import { usePagedList } from "../../lib/usePagedList";
import type { AuditHse, Duer, PlanUrgence } from "../../types";

/** M7 — clôture : audits & inspections, DUER formel, plans d'urgence et exercices (ISO 14001 / 45001). */
export function ConformiteHse() {
  const { t } = useTranslation();
  const audits = usePagedList<AuditHse>("hse-audits", (q) => api.auditsHse(q));
  const duers = usePagedList<Duer>("hse-duer", (q) => api.duerHse(q));
  const plans = usePagedList<PlanUrgence>("hse-plans-urgence", (q) => api.plansUrgence(q));
  // Choix du plan dans le formulaire d'exercice : tous les plans, pas seulement la page affichée.
  const plansTous = useQuery({ queryKey: ["hse-plans-urgence-choix"], queryFn: () => api.listAll<PlanUrgence>("/api/hse/plans-urgence/") });

  const auditCols: Column<AuditHse>[] = [
    { key: "code", header: t("hse.m7.code"), render: (a) => a.code },
    { key: "zone", header: t("hse.m7.zone"), render: (a) => a.zone },
    { key: "date", header: t("hse.m7.datePrevue"), render: (a) => formatDate(a.date_prevue) },
    { key: "score", header: t("hse.m7.score"), num: true, render: (a) => (a.score == null ? "—" : `${a.score} %`) },
    { key: "ecarts", header: t("hse.m7.ecarts"), num: true, render: (a) => a.nb_ecarts_ouverts },
    {
      key: "statut",
      header: t("hse.m7.statut"),
      render: (a) => <Badge tone={a.statut === "cloture" ? "ok" : "brand"}>{t(`hse.m7.statuts.${a.statut}`)}</Badge>,
    },
    {
      key: "actions",
      header: "",
      render: (a) => {
        const actions: ActionDef[] = [];
        if (a.statut === "planifie")
          actions.push({
            label: t("hse.m7.realiser"),
            path: `/api/hse/audits/${a.id}/realiser/`,
            prompt: { name: "score", label: t("hse.m7.scoreLabel") },
          });
        if (a.statut === "realise")
          actions.push({ label: t("hse.m7.cloturer"), path: `/api/hse/audits/${a.id}/cloturer/`, confirm: t("hse.m7.cloturer") });
        return actions.length ? <ActionBar actions={actions} /> : null;
      },
    },
  ];

  const duerCols: Column<Duer>[] = [
    { key: "code", header: t("hse.m7.code"), render: (d) => d.code },
    { key: "perimetre", header: t("hse.m7.perimetre"), render: (d) => `${d.perimetre} ${d.annee}` },
    { key: "version", header: t("hse.m7.version"), num: true, render: (d) => `v${d.version}` },
    { key: "risques", header: t("hse.m7.risques"), num: true, render: (d) => d.nb_risques },
    {
      key: "statut",
      header: t("hse.m7.statut"),
      render: (d) => (
        <>
          <Badge tone={d.statut === "approuve" ? "ok" : "brand"}>{t(`hse.m7.statuts.${d.statut}`)}</Badge>
          {d.a_revoir ? <Badge tone="warn">{t("hse.m7.aRevoir")}</Badge> : null}
        </>
      ),
    },
    {
      key: "actions",
      header: "",
      render: (d) =>
        d.statut === "brouillon" ? (
          <ActionBar actions={[{ label: t("hse.m7.approuver"), path: `/api/hse/duer/${d.id}/approuver/`, confirm: t("hse.m7.approuver") }]} />
        ) : null,
    },
  ];

  const planCols: Column<PlanUrgence>[] = [
    { key: "code", header: t("hse.m7.code"), render: (p) => p.code },
    { key: "intitule", header: t("hse.m7.intitule"), render: (p) => `${p.intitule} · ${p.type_label}` },
    { key: "dernier", header: t("hse.m7.dernier"), render: (p) => (p.dernier_exercice ? formatDate(p.dernier_exercice) : t("hse.m7.jamais")) },
    { key: "prochain", header: t("hse.m7.prochain"), render: (p) => (p.prochain_exercice ? formatDate(p.prochain_exercice) : "—") },
    {
      key: "statut",
      header: t("hse.m7.statut"),
      render: (p) => <Badge tone={p.en_retard ? "err" : "ok"}>{p.en_retard ? t("hse.m7.enRetard") : t("hse.m7.aJour")}</Badge>,
    },
  ];

  const planOptions = (plansTous.data ?? []).map((p) => ({ value: p.id, label: `${p.code} — ${p.intitule}` }));

  return (
    <>
      <SectionCard title={`${t("hse.m7.audits")} · ${audits.count}`}>
        <QuickForm
          title={t("hse.m7.newAudit")}
          endpoint="/api/hse/audits/"
          fields={[
            {
              name: "type_audit",
              label: t("hse.m7.typeAudit"),
              type: "select",
              required: true,
              defaultValue: "audit",
              options: [
                { value: "audit", label: t("hse.m7.audit") },
                { value: "inspection", label: t("hse.m7.inspection") },
              ],
            },
            { name: "zone", label: t("hse.m7.zone"), required: true },
            { name: "date_prevue", label: t("hse.m7.datePrevue"), type: "date", required: true },
          ]}
        />
        <PagedDataGrid list={audits} columns={auditCols} caption={t("hse.m7.audits")} searchPlaceholder={t("hse.m7.searchAudits")} />
      </SectionCard>

      <SectionCard title={`${t("hse.m7.duer")} · ${duers.count}`}>
        <QuickForm
          title={t("hse.m7.newDuer")}
          endpoint="/api/hse/duer/"
          fields={[
            { name: "annee", label: t("hse.m7.annee"), type: "number", required: true, defaultValue: String(new Date().getFullYear()) },
            { name: "perimetre", label: t("hse.m7.perimetre"), required: true },
          ]}
        />
        <PagedDataGrid list={duers} columns={duerCols} caption={t("hse.m7.duer")} searchPlaceholder={t("hse.m7.searchDuer")} />
      </SectionCard>

      <SectionCard title={`${t("hse.m7.plans")} · ${plans.count}`}>
        <QuickForm
          title={t("hse.m7.newPlan")}
          endpoint="/api/hse/plans-urgence/"
          fields={[
            { name: "intitule", label: t("hse.m7.intitule"), required: true },
            { name: "periodicite_mois", label: t("hse.m7.periodicite"), type: "number", required: true, defaultValue: "12", min: 1 },
          ]}
        />
        {planOptions.length > 0 ? (
          <QuickForm
            title={t("hse.m7.newExercice")}
            endpoint="/api/hse/exercices-urgence/"
            fields={[
              { name: "plan", label: t("hse.m7.plan"), type: "select", required: true, options: planOptions },
              { name: "date_exercice", label: t("hse.m7.dateExercice"), type: "date", required: true },
              { name: "participants", label: t("hse.m7.participants"), type: "number", defaultValue: "0", min: 0 },
              {
                name: "resultat",
                label: t("hse.m7.resultat"),
                type: "select",
                required: true,
                defaultValue: "satisfaisant",
                options: [
                  { value: "satisfaisant", label: t("hse.m7.satisfaisant") },
                  { value: "insuffisant", label: t("hse.m7.insuffisant") },
                ],
              },
              { name: "observations", label: t("hse.m7.observations"), type: "textarea" },
            ]}
          />
        ) : null}
        <PagedDataGrid list={plans} columns={planCols} caption={t("hse.m7.plans")} searchPlaceholder={t("hse.m7.searchPlans")} />
      </SectionCard>
    </>
  );
}
