import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatParametre } from "../../lib/format";
import { describeError } from "../../lib/offlineQueue";
import type { ParametreStock } from "../../types";
import { ParamsPanel } from "../parametres/ParamsPanel";
import { ParamValueTable } from "../parametres/ParamValueTable";

/**
 * Paramètres HSE (délais d'alerte EPI et aptitude, seuils de cotation) : provisoires jusqu'à confirmation par le HSE.
 * Extrait de `HsePersonnelSection.tsx` (chantier « params ») : panneau compact replié, tableau partagé.
 */
export function ParametresHseSection() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const q = useQuery({ queryKey: ["hse-parametres"], queryFn: () => api.listAll<ParametreStock>("/api/hse/parametres/"), retry: 0 });
  const refresh = () => {
    setError(null);
    void qc.invalidateQueries({ queryKey: ["hse-parametres"] });
  };
  const modifier = useMutation({
    mutationFn: (v: { id: string; valeur: string }) => api.patch(`/api/hse/parametres/${v.id}/`, { valeur: v.valeur }),
    onSuccess: refresh,
    onError: (e) => setError(describeError(e)),
  });
  const confirmer = useMutation({
    mutationFn: (id: string) => api.post(`/api/hse/parametres/${id}/confirmer/`),
    onSuccess: refresh,
    onError: (e) => setError(describeError(e)),
  });
  if (q.isError || !q.data) return null;
  const provisoires = q.data.filter((p) => p.est_provisoire).length;
  return (
    <ParamsPanel
      variant="card"
      module="hse"
      title={t("m7e.params.title")}
      count={provisoires}
      total={q.data.length}
      testId="parametres-hse"
    >
      {error && (
        <p className="action-error" role="alert">
          {error}
        </p>
      )}
      <ParamValueTable
        rows={q.data}
        caption={t("m7e.params.title")}
        // « 15 » plutôt que « 15 score » : l'unité technique d'une cotation n'est pas affichée (A-12).
        valeur={(p) => (["score", "choix"].includes(p.unite) ? formatParametre(p.valeur) : formatParametre(p.valeur, p.unite))}
        step="any"
        pending={modifier.isPending || confirmer.isPending}
        confirmMessage={t("m5e.params.confirmConfirmer")}
        onSave={(id, valeur) => modifier.mutateAsync({ id, valeur })}
        onConfirm={(id) => confirmer.mutate(id)}
      />
    </ParamsPanel>
  );
}
