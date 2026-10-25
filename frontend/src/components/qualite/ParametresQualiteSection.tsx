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
 * Paramètres qualité (délai CAPA, escalade, alerte de péremption, comptes du coût de non-qualité) : provisoires jusqu'à
 * confirmation QA/QC. Extrait de `EcartsM6Section.tsx` (chantier « params ») : panneau compact replié, tableau partagé
 * (« Modifier » et « Confirmer » de même hauteur, B-28).
 */
export function ParametresQualiteSection() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const q = useQuery({ queryKey: ["qualite-parametres"], queryFn: () => api.listAll<ParametreStock>("/api/qualite/parametres/"), retry: 0 });
  const refresh = () => {
    setError(null);
    void qc.invalidateQueries({ queryKey: ["qualite-parametres"] });
  };
  const modifier = useMutation({
    mutationFn: (v: { id: string; valeur: string }) => api.patch(`/api/qualite/parametres/${v.id}/`, { valeur: v.valeur }),
    onSuccess: refresh,
    onError: (e) => setError(describeError(e)),
  });
  const confirmer = useMutation({
    mutationFn: (id: string) => api.post(`/api/qualite/parametres/${id}/confirmer/`),
    onSuccess: refresh,
    onError: (e) => setError(describeError(e)),
  });
  if (q.isError || !q.data) return null;
  const provisoires = q.data.filter((p) => p.est_provisoire).length;
  return (
    <ParamsPanel
      variant="card"
      module="qualite"
      title={t("m6e.params.title")}
      count={provisoires}
      total={q.data.length}
      testId="parametres-qualite"
    >
      {error && (
        <p className="action-error" role="alert">
          {error}
        </p>
      )}
      <ParamValueTable
        rows={q.data}
        caption={t("m6e.params.title")}
        // Compte comptable sans séparateur (« Compte 624000 »), interrupteur 0/1 en Oui / Non.
        valeur={(p) => (p.unite === "compte" ? t("revueR3.qualite.compte", { compte: formatParametre(p.valeur, "compte") }) : formatParametre(p.valeur, p.unite))}
        step="any"
        pending={modifier.isPending || confirmer.isPending}
        confirmMessage={t("m5e.params.confirmConfirmer")}
        onSave={(id, valeur) => modifier.mutateAsync({ id, valeur })}
        onConfirm={(id) => confirmer.mutate(id)}
      />
    </ParamsPanel>
  );
}
