import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate } from "../../lib/format";
import type { ActionHse, RegistreOsha } from "../../types";
import { ActionBar, Badge, SectionCard } from "../ui";

/** Actions correctives / préventives HSE ouvertes (CDC M7-01) : un incident ne se clôture qu'actions soldées. */
export function ActionsHseSection() {
  const { t } = useTranslation();
  const q = useQuery({ queryKey: ["hse-actions-ouvertes"], queryFn: () => api.listAll<ActionHse>("/api/hse/actions/?ouvertes=1"), retry: 0 });
  if (q.isError || !q.data) return null;
  return (
    <SectionCard title={`${t("m7e.actions.title")} · ${q.data.length}`}>
      <div data-testid="actions-hse">
        {q.data.length === 0 ? (
          <p className="muted">{t("m7e.actions.aucune")}</p>
        ) : (
          <table className="table">
            <caption className="sr-only">{t("m7e.actions.title")}</caption>
            <tbody>
              {q.data.map((a) => (
                <tr key={a.id}>
                  <td><strong>{a.code}</strong></td>
                  <td>{a.description}</td>
                  <td>{a.echeance ? formatDate(a.echeance) : "—"}</td>
                  <td>
                    <ActionBar
                      actions={[{
                        label: t("m7e.actions.solder"), path: `/api/hse/actions/${a.id}/cloturer/`,
                        prompt: { name: "efficace", label: t("m7e.actions.efficace"), options: [{ value: "true", label: t("m7e.oui") }, { value: "false", label: t("m7e.non") }] },
                      }]}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
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
  return (
    <SectionCard title={t("m7e.osha.title")}>
      <div data-testid="registre-osha">
        <label>
          {t("m7e.osha.annee")}{" "}
          <input type="number" min={2000} max={2100} value={annee} onChange={(e) => setAnnee(e.target.value)} aria-label={t("m7e.osha.annee")} />
        </label>{" "}
        <button type="button" className="btn ghost" onClick={() => void api.download(`/api/hse/incidents/registre-osha/?annee=${annee}&export=csv`, `registre-osha-${annee}.csv`)}>
          {t("m7e.osha.export")}
        </button>
        {q.data && (
          <>
            <p role="status">
              {t("m7e.osha.synthese", {
                cas: q.data.synthese.cas_enregistrables, arret: q.data.synthese.arret, restriction: q.data.synthese.restriction,
                deces: q.data.synthese.deces, jours: q.data.synthese.jours_arret,
              })}
            </p>
            {q.data.rows.length > 0 && (
              <table className="table">
                <caption className="sr-only">{t("m7e.osha.title")}</caption>
                <tbody>
                  {q.data.rows.map((r) => (
                    <tr key={r.cas}>
                      <td>{r.cas}</td>
                      <td>{formatDate(r.date)}</td>
                      <td>{r.lieu}{r.zone ? ` · ${r.zone}` : ""}</td>
                      <td><Badge tone={r.classification === "autre_enregistrable" ? "warn" : "err"}>{t(`m7e.osha.classes.${r.classification}`)}</Badge></td>
                      <td className="num">{r.jours_arret}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </>
        )}
      </div>
    </SectionCard>
  );
}
