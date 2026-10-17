import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate, formatNumber } from "../../lib/format";
import { describeError } from "../../lib/offlineQueue";
import type { BaremeCotisation, Paginated } from "../../types";
import { Badge, SectionCard } from "../ui";

const EMPTY = { code: "", label: "", organisme: "", nature: "salariale", base: "brut", taux: "", plafond: "", date_effet: "" };

/**
 * Barèmes de cotisation (taux, plafonds, date d'effet). Les taux sont des DONNÉES à saisir et valider avec
 * ETSL / CNSSG / CNAMGS : aucune valeur légale n'est codée en dur.
 */
export function BaremesSection() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const baremes = useQuery({
    queryKey: ["baremes"],
    queryFn: () => api.get<Paginated<BaremeCotisation>>("/api/rh-paie/baremes/").then((p) => p.results),
    retry: 0,
  });
  const [form, setForm] = useState(EMPTY);
  const [error, setError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: () =>
      api.post("/api/rh-paie/baremes/", { ...form, plafond: form.plafond || null, ordre: 0 }),
    onSuccess: () => {
      setForm(EMPTY);
      setError(null);
      void qc.invalidateQueries({ queryKey: ["baremes"] });
    },
    onError: (e) => setError(describeError(e)),
  });

  if (baremes.isError) return null; // pas de droit sur la paie : la section n'apparaît pas
  const rows = baremes.data ?? [];

  return (
    <SectionCard title={t("baremes.title")}>
      <p className="muted">{t("baremes.hint")}</p>
      {rows.length === 0 ? (
        <p className="muted">{t("baremes.none")}</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>{t("baremes.code")}</th>
              <th>{t("baremes.nature")}</th>
              <th>{t("baremes.taux")}</th>
              <th>{t("baremes.plafond")}</th>
              <th>{t("baremes.effet")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((b) => (
              <tr key={b.id}>
                <td>
                  <strong>{b.code}</strong>
                  <div className="muted">
                    {b.label}
                    {b.organisme ? ` · ${b.organisme}` : ""}
                  </div>
                </td>
                <td>
                  <Badge tone={b.nature === "salariale" ? "brand" : "warn"}>{b.nature_label}</Badge>
                </td>
                <td>{b.taux} %</td>
                <td>{b.plafond ? `${formatNumber(b.plafond)} F` : "—"}</td>
                <td>
                  {formatDate(b.date_effet)}
                  {b.date_fin ? ` → ${formatDate(b.date_fin)}` : ""}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h4 className="subtitle">{t("baremes.add")}</h4>
      <form
        className="bareme-form"
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate();
        }}
      >
        <input required aria-label={t("baremes.code")} placeholder={t("baremes.code")} value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} />
        <input required aria-label={t("baremes.label")} placeholder={t("baremes.label")} value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} />
        <input aria-label={t("baremes.organisme")} placeholder={t("baremes.organisme")} value={form.organisme} onChange={(e) => setForm({ ...form, organisme: e.target.value })} />
        <select aria-label={t("baremes.nature")} value={form.nature} onChange={(e) => setForm({ ...form, nature: e.target.value })}>
          <option value="salariale">{t("baremes.salariale")}</option>
          <option value="patronale">{t("baremes.patronale")}</option>
        </select>
        <select aria-label={t("baremes.base")} value={form.base} onChange={(e) => setForm({ ...form, base: e.target.value })}>
          <option value="brut">{t("baremes.baseBrut")}</option>
          <option value="salaire">{t("baremes.baseSalaire")}</option>
        </select>
        <input required type="number" step="0.001" min="0" aria-label={t("baremes.taux")} placeholder={t("baremes.taux")} value={form.taux} onChange={(e) => setForm({ ...form, taux: e.target.value })} />
        <input type="number" step="1" min="0" aria-label={t("baremes.plafond")} placeholder={t("baremes.plafond")} value={form.plafond} onChange={(e) => setForm({ ...form, plafond: e.target.value })} />
        <input required type="date" aria-label={t("baremes.effet")} value={form.date_effet} onChange={(e) => setForm({ ...form, date_effet: e.target.value })} />
        <button className="btn" type="submit" disabled={create.isPending}>
          {t("baremes.save")}
        </button>
        {error && (
          <p className="action-error" role="alert">
            {error}
          </p>
        )}
      </form>
    </SectionCard>
  );
}
