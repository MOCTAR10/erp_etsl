import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { describeError } from "../../lib/offlineQueue";
import { Badge, SectionCard } from "../ui";

interface OtGr {
  id: string;
  code: string;
  actif_code: string;
  statut: string;
  statut_label: string;
  est_gr: boolean;
  ecriture_numero: string | null;
  ecriture_statut: string | null;
  motif_ecriture: string;
  bc_gr: string | null;
  bc_gr_code: string | null;
}
interface BcGr {
  id: string;
  code: string;
  fournisseur: string;
  statut: string;
}

/** Lot correctif : une seule charge 618 — l'OT GR rattaché au BC GLOBAL RENTAL ne passe pas (ou extourne) son OD. */
export function LiaisonBcGrSection() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [choix, setChoix] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const ots = (useQuery({ queryKey: ["correctif", "ot-gr"], queryFn: () => api.listAll<OtGr>("/api/maintenance/ordres/"), retry: 0 }).data ?? [])
    .filter((o) => o.est_gr && o.statut !== "annule")
    .slice(0, 30);
  const bcs = useQuery({ queryKey: ["correctif", "bc-gr"], queryFn: () => api.get<BcGr[]>("/api/maintenance/ordres/bc-gr/"), retry: 0 }).data ?? [];
  const lier = useMutation({
    mutationFn: (v: { ot: string; bc: string }) => api.post(`/api/maintenance/ordres/${v.ot}/lier-bc-gr/`, { bc: v.bc }),
    onSuccess: () => {
      setError(null);
      void qc.invalidateQueries({ queryKey: ["correctif"] });
      void qc.invalidateQueries({ queryKey: ["m5m8"] });
    },
    onError: (e) => setError(describeError(e)),
  });

  return (
    <SectionCard title={t("ecarts_correctif.maint.title")}>
      <div data-testid="liaison-bc-gr">
        <p className="muted">{t("ecarts_correctif.maint.intro")}</p>
        {error && (
          <p className="action-error" role="alert">
            {error}
          </p>
        )}
        {ots.length === 0 ? (
          <p className="muted">{t("ecarts_correctif.maint.aucun")}</p>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>{t("ecarts_correctif.maint.ot")}</th>
                  <th>{t("ecarts_correctif.maint.actif")}</th>
                  <th>{t("ecarts_correctif.maint.statut")}</th>
                  <th>{t("ecarts_correctif.maint.ecriture")}</th>
                  <th>{t("ecarts_correctif.maint.bc")}</th>
                </tr>
              </thead>
              <tbody>
                {ots.map((o) => (
                  <tr key={o.id}>
                    <td>{o.code}</td>
                    <td>{o.actif_code}</td>
                    <td>{o.statut_label}</td>
                    <td title={o.motif_ecriture}>
                      {o.ecriture_numero ? (
                        <>
                          {o.ecriture_numero}{" "}
                          {o.ecriture_statut === "reversed" && <Badge tone="warn">{t("ecarts_correctif.maint.extournee")}</Badge>}
                        </>
                      ) : (
                        o.motif_ecriture || "—"
                      )}
                    </td>
                    <td>
                      {o.bc_gr_code ? (
                        <Badge tone="ok">{o.bc_gr_code}</Badge>
                      ) : (
                        <span className="action-bar-buttons">
                          <select
                            aria-label={t("ecarts_correctif.maint.choisirBc")}
                            value={choix[o.id] ?? ""}
                            onChange={(e) => setChoix({ ...choix, [o.id]: e.target.value })}
                          >
                            <option value="">{t("ecarts_correctif.maint.choisirBc")}</option>
                            {bcs.map((b) => (
                              <option key={b.id} value={b.id}>
                                {b.code} · {b.fournisseur}
                              </option>
                            ))}
                          </select>
                          <button
                            type="button"
                            className="btn ghost"
                            disabled={!choix[o.id] || lier.isPending}
                            onClick={() => {
                              if (window.confirm(t("ecarts_correctif.maint.confirm"))) lier.mutate({ ot: o.id, bc: choix[o.id] });
                            }}
                          >
                            {t("ecarts_correctif.maint.lier")}
                          </button>
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </SectionCard>
  );
}
