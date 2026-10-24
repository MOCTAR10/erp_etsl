import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { describeError } from "../../lib/offlineQueue";
import { Badge, DataTable, SectionCard } from "../ui";
import type { Column } from "../ui";

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

  const columns: Column<OtGr>[] = [
    { key: "ot", header: t("ecarts_correctif.maint.ot"), render: (o) => o.code, sortValue: (o) => o.code },
    { key: "actif", header: t("ecarts_correctif.maint.actif"), render: (o) => o.actif_code, sortValue: (o) => o.actif_code },
    { key: "statut", header: t("ecarts_correctif.maint.statut"), render: (o) => String(t(`maintenance.ot_statut.${o.statut}`, { defaultValue: o.statut_label })) },
    {
      key: "ecriture",
      header: t("ecarts_correctif.maint.ecriture"),
      render: (o) =>
        o.ecriture_numero ? (
          <span title={o.motif_ecriture}>
            {o.ecriture_numero} {o.ecriture_statut === "reversed" && <Badge tone="warn">{t("ecarts_correctif.maint.extournee")}</Badge>}
          </span>
        ) : (
          o.motif_ecriture || "—"
        ),
    },
    {
      key: "bc",
      header: t("ecarts_correctif.maint.bc"),
      render: (o) =>
        o.bc_gr_code ? (
          <Badge tone="ok">{o.bc_gr_code}</Badge>
        ) : (
          <span className="action-bar-buttons">
            <select
              className="control"
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
              className="btn ghost sm"
              disabled={!choix[o.id] || lier.isPending}
              onClick={() => {
                if (window.confirm(t("ecarts_correctif.maint.confirm"))) lier.mutate({ ot: o.id, bc: choix[o.id] });
              }}
            >
              {t("ecarts_correctif.maint.lier")}
            </button>
          </span>
        ),
    },
  ];

  return (
    <SectionCard title={t("ecarts_correctif.maint.title")}>
      <div data-testid="liaison-bc-gr">
        <p className="muted">{t("ecarts_correctif.maint.intro")}</p>
        {error && (
          <p className="action-error" role="alert">
            {error}
          </p>
        )}
        <DataTable caption={t("ecarts_correctif.maint.title")} columns={columns} rows={ots} emptyLabel={t("ecarts_correctif.maint.aucun")} />
      </div>
    </SectionCard>
  );
}
