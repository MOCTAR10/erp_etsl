import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate, formatNumber } from "../../lib/format";
import type { ActionHse, RegistreOsha } from "../../types";
import { ActionBar, Badge, DataTable, SectionCard } from "../ui";
import type { Column } from "../ui";

type CasOsha = RegistreOsha["rows"][number] & { id: string };

/** Actions correctives / préventives HSE ouvertes : un incident ne se clôture qu'actions soldées. */
export function ActionsHseSection() {
  const { t } = useTranslation();
  const q = useQuery({ queryKey: ["hse-actions-ouvertes"], queryFn: () => api.listAll<ActionHse>("/api/hse/actions/?ouvertes=1"), retry: 0 });
  if (q.isError || !q.data) return null;
  const columns: Column<ActionHse>[] = [
    { key: "code", header: t("tableaux.hse.reference"), render: (a) => <strong>{a.code}</strong>, sortValue: (a) => a.code },
    { key: "description", header: t("tableaux.hse.action"), render: (a) => a.description },
    { key: "echeance", header: t("tableaux.hse.echeance"), kind: "date", render: (a) => (a.echeance ? formatDate(a.echeance) : "—"), sortValue: (a) => a.echeance },
    {
      key: "actions",
      header: <span className="sr-only">{t("ui.actions")}</span>,
      render: (a) => (
        <ActionBar
          actions={[{
            label: t("m7e.actions.solder"), path: `/api/hse/actions/${a.id}/cloturer/`,
            prompt: { name: "efficace", label: t("m7e.actions.efficace"), options: [{ value: "true", label: t("m7e.oui") }, { value: "false", label: t("m7e.non") }] },
          }]}
        />
      ),
    },
  ];
  return (
    <SectionCard title={`${t("m7e.actions.title")} · ${q.data.length}`}>
      <div data-testid="actions-hse">
        <DataTable columns={columns} rows={q.data} caption={t("m7e.actions.title")} emptyLabel={t("m7e.actions.aucune")} />
      </div>
    </SectionCard>
  );
}

/** Registre des cas enregistrables (modèle OSHA 300) et synthèse annuelle (OSHA 300A), export CSV. */
export function RegistreOshaSection() {
  const { t } = useTranslation();
  const [annee, setAnnee] = useState(String(new Date().getFullYear()));
  const q = useQuery({
    queryKey: ["hse-registre-osha", annee],
    queryFn: () => api.get<RegistreOsha>(`/api/hse/incidents/registre-osha/?annee=${annee}`),
    enabled: /^\d{4}$/.test(annee),
    retry: 0,
  });
  const rows: CasOsha[] = (q.data?.rows ?? []).map((r) => ({ ...r, id: r.cas }));
  const columns: Column<CasOsha>[] = [
    { key: "cas", header: t("tableaux.hse.cas"), render: (r) => r.cas, sortValue: (r) => r.cas },
    { key: "date", header: t("tableaux.hse.date"), kind: "date", render: (r) => formatDate(r.date), sortValue: (r) => r.date },
    { key: "lieu", header: t("tableaux.hse.lieu"), render: (r) => `${r.lieu}${r.zone ? ` · ${t(`m7e.zones.${r.zone}`, { defaultValue: r.zone })}` : ""}` },
    {
      key: "classification",
      header: t("tableaux.hse.classification"),
      render: (r) => <Badge tone={r.classification === "autre_enregistrable" ? "warn" : "err"}>{t(`m7e.osha.classes.${r.classification}`)}</Badge>,
    },
    { key: "jours", header: t("tableaux.hse.joursArret"), num: true, render: (r) => formatNumber(r.jours_arret), sortValue: (r) => r.jours_arret },
  ];
  return (
    <SectionCard
      title={t("m7e.osha.title")}
      actions={
        <button type="button" className="btn ghost" onClick={() => void api.download(`/api/hse/incidents/registre-osha/?annee=${annee}&export=csv`, `registre-osha-${annee}.csv`)}>
          {t("m7e.osha.export")}
        </button>
      }
    >
      <div data-testid="registre-osha">
        <div className="field">
          <label htmlFor="osha-annee">{t("m7e.osha.annee")}</label>
          <input id="osha-annee" className="control" type="number" min={2000} max={2100} value={annee} onChange={(e) => setAnnee(e.target.value)} style={{ maxWidth: 140 }} />
        </div>
        {q.data && (
          <>
            <p role="status">
              {t("m7e.osha.synthese", {
                cas: q.data.synthese.cas_enregistrables, arret: q.data.synthese.arret, restriction: q.data.synthese.restriction,
                deces: q.data.synthese.deces, jours: q.data.synthese.jours_arret,
              })}
            </p>
            {rows.length > 0 && <DataTable columns={columns} rows={rows} caption={t("m7e.osha.title")} />}
          </>
        )}
      </div>
    </SectionCard>
  );
}
