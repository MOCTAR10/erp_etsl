import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate, formatNumber } from "../../lib/format";
import { describeError } from "../../lib/offlineQueue";
import type { Lettrage, LettrageAnomalies, Paginated, ParametreCompta } from "../../types";
import { Badge, SectionCard } from "../ui";

interface CompteRef {
  id: string;
  code: string;
  label: string;
  reconcile: boolean;
}

/**
 * Lettrage automatique des comptes lettrables (411, 401…), anomalies et paramètres modifiables par ETSL.
 * Les écritures comptabilisées ne sont jamais modifiées : le lettrage vit dans ses propres tables.
 */
export function LettrageSection() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [compte, setCompte] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [edit, setEdit] = useState<{ id: string; valeur: string } | null>(null);

  const comptes = useQuery({
    queryKey: ["lettrage-comptes"],
    queryFn: () =>
      api.listAll<CompteRef>("/api/referentiels/accounts/").then((rows) => rows.filter((c) => c.reconcile)),
    retry: 0,
  });
  const params = useQuery({
    queryKey: ["compta-parametres"],
    queryFn: () => api.get<Paginated<ParametreCompta>>("/api/comptabilite/parametres/").then((p) => p.results),
    retry: 0,
  });
  const lettrages = useQuery({
    queryKey: ["lettrages", compte],
    queryFn: () => api.get<Paginated<Lettrage>>(`/api/comptabilite/lettrages/?compte=${compte}&page_size=20`).then((p) => p.results),
    enabled: !!compte,
    retry: 0,
  });
  const anomalies = useQuery({
    queryKey: ["lettrage-anomalies", compte],
    queryFn: () => api.get<LettrageAnomalies>(`/api/comptabilite/lettrages/anomalies/?compte=${compte}`),
    enabled: !!compte,
    retry: 0,
  });

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["lettrages"] });
    void qc.invalidateQueries({ queryKey: ["lettrage-anomalies"] });
    void qc.invalidateQueries({ queryKey: ["compta-parametres"] });
  };
  const lancer = useMutation({
    mutationFn: () => api.post<{ lettrages: number; non_lettrees: number }>("/api/comptabilite/lettrages/lettrer-auto/", { compte }),
    onSuccess: (r) => {
      setError(null);
      setMsg(t("lettrage.resultat", { n: r.lettrages, reste: r.non_lettrees }));
      refresh();
    },
    onError: (e) => setError(describeError(e)),
  });
  const delettrer = useMutation({
    mutationFn: (v: { id: string; motif: string }) => api.post(`/api/comptabilite/lettrages/${v.id}/delettrer/`, { motif: v.motif }),
    onSuccess: () => {
      setError(null);
      refresh();
    },
    onError: (e) => setError(describeError(e)),
  });
  const modifier = useMutation({
    mutationFn: (v: { id: string; valeur: string }) => api.patch(`/api/comptabilite/parametres/${v.id}/`, { valeur: v.valeur }),
    onSuccess: () => {
      setEdit(null);
      setError(null);
      refresh();
    },
    onError: (e) => setError(describeError(e)),
  });
  const confirmer = useMutation({
    mutationFn: (id: string) => api.post(`/api/comptabilite/parametres/${id}/confirmer/`),
    onSuccess: refresh,
    onError: (e) => setError(describeError(e)),
  });

  if (comptes.isError) return null; // pas de droit : la section n'apparaît pas
  const provisoires = (params.data ?? []).filter((p) => p.est_provisoire).length;

  return (
    <SectionCard title={t("lettrage.title")}>
      <p className="muted">{t("lettrage.hint")}</p>
      {provisoires > 0 && (
        <p className="action-error" role="note" data-testid="alerte-provisoire-compta">
          {t("lettrage.warnProvisoire", { count: provisoires })}
        </p>
      )}
      {error && <p className="action-error" role="alert">{error}</p>}

      <div className="row-actions">
        <select aria-label={t("lettrage.compte")} value={compte} onChange={(e) => { setCompte(e.target.value); setMsg(null); }}>
          <option value="">{t("lettrage.choisir")}</option>
          {(comptes.data ?? []).map((c) => (
            <option key={c.id} value={c.id}>{c.code} — {c.label}</option>
          ))}
        </select>
        <button type="button" className="btn" disabled={!compte || lancer.isPending} onClick={() => lancer.mutate()}>
          {t("lettrage.lancer")}
        </button>
      </div>
      {msg && <p role="status">{msg}</p>}

      {compte && anomalies.data && anomalies.data.anomalies.length > 0 && (
        <>
          <h4 className="section-heading">{t("lettrage.anomalies", { count: anomalies.data.anomalies.length, jours: anomalies.data.delai_jours })}</h4>
          <table className="table">
            <tbody>
              {anomalies.data.anomalies.map((a) => (
                <tr key={a.ligne}>
                  <td>{formatDate(a.date)}</td>
                  <td>{a.reference || "—"}</td>
                  <td className="num">{a.debit !== null && a.credit !== null ? formatNumber(Number(a.debit) - Number(a.credit)) : "••••••"}</td>
                  <td><Badge tone="warn">{t(`lettrage.motif.${a.motif}`)}</Badge></td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {compte && (lettrages.data ?? []).length > 0 && (
        <>
          <h4 className="section-heading">{t("lettrage.recents")}</h4>
          <table className="table">
            <tbody>
              {(lettrages.data ?? []).map((l) => (
                <tr key={l.id}>
                  <td><strong>{l.code}</strong></td>
                  <td>{l.automatique ? t("lettrage.auto") : t("lettrage.manuel")} · {l.lignes.length} {t("lettrage.lignes")}</td>
                  <td><Badge tone={l.statut === "actif" ? "ok" : "err"}>{t(`lettrage.statut.${l.statut}`)}</Badge></td>
                  <td>
                    {l.statut === "actif" && (
                      <button
                        type="button"
                        className="btn ghost"
                        onClick={() => {
                          const motif = window.prompt(t("lettrage.motifPrompt"));
                          if (motif) delettrer.mutate({ id: l.id, motif });
                        }}
                      >
                        {t("lettrage.delettrer")}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      <h4 className="section-heading">{t("lettrage.params")}</h4>
      <table className="table">
        <tbody>
          {(params.data ?? []).map((p) => (
            <tr key={p.id}>
              <td>{p.label}</td>
              <td>
                {edit?.id === p.id ? (
                  <input type="number" min="0" step="0.01" aria-label={p.label} value={edit.valeur} onChange={(e) => setEdit({ id: p.id, valeur: e.target.value })} />
                ) : (
                  `${p.valeur} ${p.unite}`
                )}
              </td>
              <td><Badge tone={p.est_provisoire ? "warn" : "ok"}>{t(`lettrage.${p.statut_valeur}`)}</Badge></td>
              <td>
                {edit?.id === p.id ? (
                  <>
                    <button type="button" className="btn" onClick={() => modifier.mutate(edit)}>{t("lettrage.valider")}</button>{" "}
                    <button type="button" className="btn ghost" onClick={() => setEdit(null)}>{t("lettrage.annuler")}</button>
                  </>
                ) : (
                  <>
                    <button type="button" className="btn ghost" onClick={() => setEdit({ id: p.id, valeur: p.valeur })}>{t("lettrage.modifier")}</button>{" "}
                    {p.est_provisoire && (
                      <button type="button" className="btn ghost" onClick={() => window.confirm(t("lettrage.confirmConfirmer")) && confirmer.mutate(p.id)}>
                        {t("lettrage.confirmer")}
                      </button>
                    )}
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </SectionCard>
  );
}
