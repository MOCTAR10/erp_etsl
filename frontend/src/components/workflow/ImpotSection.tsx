import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatMoney } from "../../lib/format";
import { describeError } from "../../lib/offlineQueue";
import type { BaremeImpot } from "../../types";
import { Badge } from "../ui";

type Tranche = { plafond: string; taux: string };

/** Barème IRPP : tranches modifiables par ETSL (cercle paie), sans développeur. */
export function ImpotSection({ onChanged }: { onChanged: () => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const impots = useQuery({
    queryKey: ["baremes-impot"],
    queryFn: () => api.listAll<BaremeImpot>("/api/rh-paie/baremes-impot/"),
    retry: 0,
  });
  const [editId, setEditId] = useState<string | null>(null);
  const [tranches, setTranches] = useState<Tranche[]>([]);
  const [abattement, setAbattement] = useState("0");
  const [error, setError] = useState<string | null>(null);

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["baremes-impot"] });
    onChanged();
  };
  const save = useMutation({
    mutationFn: (id: string) =>
      api.patch(`/api/rh-paie/baremes-impot/${id}/`, {
        abattement_pct: abattement,
        tranches: tranches.map((tr) => ({ plafond: tr.plafond === "" ? null : Number(tr.plafond), taux: Number(tr.taux) })),
      }),
    onSuccess: () => {
      setEditId(null);
      setError(null);
      refresh();
    },
    onError: (e) => setError(describeError(e)),
  });
  const confirmer = useMutation({
    mutationFn: (id: string) => api.post(`/api/rh-paie/baremes-impot/${id}/confirmer/`),
    onSuccess: refresh,
    onError: (e) => setError(describeError(e)),
  });

  const rows = impots.data ?? [];
  if (impots.isError || rows.length === 0) return null;

  const start = (b: BaremeImpot) => {
    setEditId(b.id);
    setAbattement(b.abattement_pct);
    setTranches(b.tranches.map((tr) => ({ plafond: tr.plafond === null ? "" : String(tr.plafond), taux: String(tr.taux) })));
  };
  const setTr = (i: number, patch: Partial<Tranche>) => setTranches(tranches.map((tr, j) => (j === i ? { ...tr, ...patch } : tr)));

  return (
    <div data-testid="bareme-impot">
      <h4 className="subtitle">{t("baremes.impotTitle")}</h4>
      {rows.map((b) => (
        <div key={b.id} className="card">
          <strong>{b.code}</strong> <span className="muted">{b.label}</span>{" "}
          <Badge tone={b.statut_valeur === "confirme" ? "ok" : "warn"}>{t(`baremes.${b.statut_valeur}`)}</Badge>
          {editId === b.id ? (
            <div>
              {tranches.map((tr, i) => (
                <div key={i}>
                  <input
                    type="number"
                    min="0"
                    aria-label={`${t("baremes.tranche")} ${i + 1}`}
                    placeholder={i === tranches.length - 1 ? t("baremes.derniere") : t("baremes.tranche")}
                    disabled={i === tranches.length - 1}
                    value={i === tranches.length - 1 ? "" : tr.plafond}
                    onChange={(e) => setTr(i, { plafond: e.target.value })}
                  />{" "}
                  <input type="number" min="0" max="100" step="0.1" aria-label={`${t("baremes.taux")} ${i + 1}`} value={tr.taux} onChange={(e) => setTr(i, { taux: e.target.value })} />
                </div>
              ))}
              <label>
                {t("baremes.abattement")}{" "}
                <input type="number" min="0" max="100" step="0.1" value={abattement} onChange={(e) => setAbattement(e.target.value)} />
              </label>{" "}
              <button
                type="button"
                className="btn"
                onClick={() => {
                  // la dernière tranche (sans plafond) reste en queue : on insère avant elle
                  const last = tranches[tranches.length - 1];
                  setTranches([...tranches.slice(0, -1), { plafond: "", taux: "0" }, last]);
                }}
              >
                {t("baremes.addTranche")}
              </button>{" "}
              <button type="button" className="btn" onClick={() => save.mutate(b.id)}>
                {t("baremes.save")}
              </button>{" "}
              <button type="button" className="btn" onClick={() => setEditId(null)}>
                {t("baremes.annuler")}
              </button>
            </div>
          ) : (
            <div>
              <table className="table">
                <tbody>
                  {b.tranches.map((tr, i) => (
                    <tr key={i}>
                      <td>{tr.plafond === null ? t("baremes.derniere") : `≤ ${formatMoney(tr.plafond)}`}</td>
                      <td>{tr.taux} %</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <span className="muted">
                {t("baremes.abattement")} : {b.abattement_pct}
              </span>{" "}
              <button type="button" className="btn" onClick={() => start(b)}>
                {t("baremes.modifier")}
              </button>{" "}
              {b.statut_valeur !== "confirme" && (
                <button type="button" className="btn" onClick={() => window.confirm(t("baremes.confirmConfirmer")) && confirmer.mutate(b.id)}>
                  {t("baremes.confirmer")}
                </button>
              )}
            </div>
          )}
        </div>
      ))}
      {error && (
        <p className="action-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
