import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate, formatMoney } from "../../lib/format";
import { describeError } from "../../lib/offlineQueue";
import type { BaremeCotisation, HistoriqueBareme, ParametrePaie } from "../../types";
import { Badge, SectionCard } from "../ui";
import { ImpotSection } from "./ImpotSection";

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
    queryFn: () => api.listAll<BaremeCotisation>("/api/rh-paie/baremes/"),
    retry: 0,
  });
  const params = useQuery({
    queryKey: ["parametres-paie"],
    queryFn: () => api.listAll<ParametrePaie>("/api/rh-paie/parametres-paie/"),
    retry: 0,
  });
  const [histoire, setHistoire] = useState<{ code: string; rows: HistoriqueBareme[] } | null>(null);
  const [edit, setEdit] = useState<{ url: string; valeur: string; plafond?: string; source: string } | null>(null);
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

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["baremes"] });
    void qc.invalidateQueries({ queryKey: ["parametres-paie"] });
  };
  const confirmer = useMutation({
    mutationFn: (url: string) => api.post(`${url}confirmer/`),
    onSuccess: refresh,
    onError: (e) => setError(describeError(e)),
  });
  const enregistrer = useMutation({
    mutationFn: (e: NonNullable<typeof edit>) =>
      api.patch(e.url, {
        ...(e.plafond !== undefined ? { taux: e.valeur, plafond: e.plafond || null } : { valeur: e.valeur }),
        source: e.source,
      }),
    onSuccess: () => {
      setEdit(null);
      setError(null);
      refresh();
    },
    onError: (e) => setError(describeError(e)),
  });
  const reviser = useMutation({
    mutationFn: (v: { id: string; date_effet: string; taux: string }) =>
      api.post(`/api/rh-paie/baremes/${v.id}/reviser/`, { date_effet: v.date_effet, taux: v.taux }),
    onSuccess: () => {
      setError(null);
      refresh();
    },
    onError: (e) => setError(describeError(e)),
  });

  if (baremes.isError) return null; // pas de droit sur la paie : la section n'apparaît pas
  const rows = baremes.data ?? [];
  const provisoires = rows.filter((b) => b.statut_valeur !== "confirme").length + (params.data ?? []).filter((p) => p.statut_valeur !== "confirme").length;
  const proposerRevision = (b: BaremeCotisation) => {
    const date_effet = window.prompt(t("baremes.revisionDate"));
    const taux = date_effet ? window.prompt(t("baremes.revisionTaux"), b.taux) : null;
    if (date_effet && taux) reviser.mutate({ id: b.id, date_effet, taux });
  };
  const voirHistorique = async (b: BaremeCotisation) => {
    const rowsH = await api.get<HistoriqueBareme[]>(`/api/rh-paie/baremes/${b.id}/historique/`);
    setHistoire({ code: b.code, rows: rowsH });
  };

  return (
    <SectionCard title={t("baremes.title")}>
      <p className="muted">{t("baremes.hint")}</p>
      {provisoires > 0 && (
        <p className="action-error" role="note" data-testid="alerte-provisoire">
          {t("baremes.warnProvisoire", { count: provisoires })}
        </p>
      )}
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
              <th>{t("baremes.statut")}</th>
              <th />
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
                {edit?.url === `/api/rh-paie/baremes/${b.id}/` ? (
                  <>
                    <td>
                      <input type="number" step="0.001" min="0" aria-label={t("baremes.taux")} value={edit.valeur} onChange={(e) => setEdit({ ...edit, valeur: e.target.value })} />
                    </td>
                    <td>
                      <input type="number" step="1" min="0" aria-label={t("baremes.plafond")} value={edit.plafond ?? ""} onChange={(e) => setEdit({ ...edit, plafond: e.target.value })} />
                    </td>
                  </>
                ) : (
                  <>
                    <td>{b.taux} %</td>
                    <td>{b.plafond ? formatMoney(b.plafond) : "—"}</td>
                  </>
                )}
                <td>
                  {formatDate(b.date_effet)}
                  {b.date_fin ? ` → ${formatDate(b.date_fin)}` : ""}
                </td>
                <td title={`${b.source} ${b.reference_texte}`.trim()}>
                  <Badge tone={b.statut_valeur === "confirme" ? "ok" : "warn"}>{t(`baremes.${b.statut_valeur}`)}</Badge>
                </td>
                <td>
                  {b.statut_valeur !== "confirme" && (
                    <button
                      type="button"
                      className="btn"
                      onClick={() => window.confirm(t("baremes.confirmConfirmer")) && confirmer.mutate(`/api/rh-paie/baremes/${b.id}/`)}
                    >
                      {t("baremes.confirmer")}
                    </button>
                  )}{" "}
                  {edit?.url === `/api/rh-paie/baremes/${b.id}/` ? (
                    <>
                      <button type="button" className="btn" onClick={() => enregistrer.mutate(edit)}>
                        {t("baremes.save")}
                      </button>{" "}
                      <button type="button" className="btn" onClick={() => setEdit(null)}>
                        {t("baremes.annuler")}
                      </button>{" "}
                    </>
                  ) : (
                    <>
                      <button
                        type="button"
                        className="btn"
                        onClick={() => setEdit({ url: `/api/rh-paie/baremes/${b.id}/`, valeur: b.taux, plafond: b.plafond ?? "", source: b.source })}
                      >
                        {t("baremes.modifier")}
                      </button>{" "}
                    </>
                  )}
                  <button type="button" className="btn" onClick={() => proposerRevision(b)}>
                    {t("baremes.reviser")}
                  </button>{" "}
                  <button type="button" className="btn" onClick={() => void voirHistorique(b)}>
                    {t("baremes.historique")}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {histoire && (
        <div>
          <h4 className="subtitle">
            {t("baremes.history")} — {histoire.code}
          </h4>
          <ul className="muted">
            {histoire.rows.map((h) => (
              <li key={h.id}>
                {formatDate(h.le)} · {h.action} · {h.par_email ?? "—"}
              </li>
            ))}
          </ul>
        </div>
      )}

      <h4 className="subtitle">{t("baremes.paramsTitle")}</h4>
      <table className="table">
        <tbody>
          {(params.data ?? []).map((p) => (
            <tr key={p.id}>
              <td>
                <strong>{p.code}</strong>
                <div className="muted">{p.label}</div>
              </td>
              <td>
                {edit?.url === `/api/rh-paie/parametres-paie/${p.id}/` ? (
                  <input type="number" step="0.001" aria-label={t("baremes.valeur")} value={edit.valeur} onChange={(e) => setEdit({ ...edit, valeur: e.target.value })} />
                ) : (
                  <>
                    {p.valeur} {p.unite}
                  </>
                )}
              </td>
              <td title={`${p.source} ${p.reference_texte}`.trim()}>
                <Badge tone={p.statut_valeur === "confirme" ? "ok" : "warn"}>{t(`baremes.${p.statut_valeur}`)}</Badge>
              </td>
              <td>
                {edit?.url === `/api/rh-paie/parametres-paie/${p.id}/` ? (
                  <>
                    <button type="button" className="btn" onClick={() => enregistrer.mutate(edit)}>
                      {t("baremes.save")}
                    </button>{" "}
                    <button type="button" className="btn" onClick={() => setEdit(null)}>
                      {t("baremes.annuler")}
                    </button>
                  </>
                ) : (
                  <button
                    type="button"
                    className="btn"
                    onClick={() => setEdit({ url: `/api/rh-paie/parametres-paie/${p.id}/`, valeur: p.valeur, source: p.source })}
                  >
                    {t("baremes.modifier")}
                  </button>
                )}{" "}
                {p.statut_valeur !== "confirme" && (
                  <button
                    type="button"
                    className="btn"
                    onClick={() => window.confirm(t("baremes.confirmConfirmer")) && confirmer.mutate(`/api/rh-paie/parametres-paie/${p.id}/`)}
                  >
                    {t("baremes.confirmer")}
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <p className="muted">{t("baremes.editHint")}</p>
      {error && (
        <p className="action-error" role="alert">
          {error}
        </p>
      )}
      <ImpotSection onChanged={refresh} />

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
