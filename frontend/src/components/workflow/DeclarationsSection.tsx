import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate, formatMoney } from "../../lib/format";
import { describeError } from "../../lib/offlineQueue";
import { SectionCard } from "../ui";

interface Declaration {
  id: string;
  code: string;
  type: string;
  type_label: string;
  periode_debut: string;
  periode_fin: string;
  nb_salaries: number;
  total_brut: string;
  total_salarial: string;
  total_patronal: string;
  provisoire: boolean;
  avertissement: string;
}
interface Reporting {
  annee: number;
  effectif_fin: number;
  entrees: number;
  sorties: number;
  turnover_pct: string | null;
  jours_absence: number;
  absenteisme_pct: string | null;
}

/** Déclarations CNSS / CNAMGS / IRPP (2460) / DADS générées depuis les bulletins + indicateurs RH. */
export function DeclarationsSection() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const decls = useQuery({
    queryKey: ["declarations"],
    queryFn: () => api.listAll<Declaration>("/api/rh-paie/declarations/"),
    retry: 0,
  });
  const annee = new Date().getFullYear();
  const reporting = useQuery({
    queryKey: ["reporting-rh", annee],
    queryFn: () => api.get<Reporting>(`/api/rh-paie/reporting/?annee=${annee}`),
    retry: 0,
  });
  const [form, setForm] = useState({ type: "cnss", periode_debut: "", periode_fin: "" });
  const [error, setError] = useState<string | null>(null);
  const generer = useMutation({
    mutationFn: () => api.post("/api/rh-paie/declarations/generer/", form),
    onSuccess: () => {
      setError(null);
      void qc.invalidateQueries({ queryKey: ["declarations"] });
    },
    onError: (e) => setError(describeError(e)),
  });

  if (decls.isError) return null; // hors cercle paie : la section n'apparaît pas
  const r = reporting.data;

  return (
    <SectionCard title={t("declarations.title")}>
      <p className="muted">{t("declarations.hint")}</p>
      {r && (
        <p className="muted" data-testid="reporting-rh">
          {t("declarations.reporting", {
            annee: r.annee, effectif: r.effectif_fin, entrees: r.entrees, sorties: r.sorties,
            turnover: r.turnover_pct ?? "—", absence: r.jours_absence, absenteisme: r.absenteisme_pct ?? "—",
          })}
        </p>
      )}
      <form
        className="bareme-form"
        onSubmit={(e) => {
          e.preventDefault();
          generer.mutate();
        }}
      >
        <select aria-label={t("declarations.type")} value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}>
          <option value="cnss">CNSS</option>
          <option value="cnamgs">CNAMGS</option>
          <option value="irpp">IRPP (2460)</option>
          <option value="dads">DADS</option>
          <option value="fnh">FNH</option>
          <option value="cfp">CFP</option>
        </select>
        <input required type="date" aria-label={t("declarations.du")} value={form.periode_debut} onChange={(e) => setForm({ ...form, periode_debut: e.target.value })} />
        <input required type="date" aria-label={t("declarations.au")} value={form.periode_fin} onChange={(e) => setForm({ ...form, periode_fin: e.target.value })} />
        <button className="btn" type="submit" disabled={generer.isPending}>
          {t("declarations.generer")}
        </button>
      </form>
      {error && (
        <p className="action-error" role="alert">
          {error}
        </p>
      )}
      {(decls.data ?? []).length > 0 && (
        <table className="table">
          <tbody>
            {(decls.data ?? []).map((d) => (
              <tr key={d.id}>
                <td>
                  <strong>{d.code}</strong> · {d.type_label}
                  <div className="muted">
                    {formatDate(d.periode_debut)} → {formatDate(d.periode_fin)} · {d.nb_salaries}
                  </div>
                  {d.provisoire && (
                    <div className="action-error" role="note">
                      {d.avertissement}
                    </div>
                  )}
                </td>
                <td>
                  {formatMoney(d.total_brut)} · {formatMoney(d.total_salarial)} / {formatMoney(d.total_patronal)}
                </td>
                <td>
                  <button type="button" className="btn" onClick={() => void api.download(`/api/rh-paie/declarations/${d.id}/fichier/`, `${d.code}_${d.type}.csv`)}>
                    {t("virements.telecharger")}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </SectionCard>
  );
}
