import { useMutation, useQueries, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { describeError } from "../../lib/offlineQueue";
import { libelleParametre, referenceKpi, valeurScalaire } from "../parametres/ParamValue";
import { ParamsPanel } from "../parametres/ParamsPanel";
import { ParamValueTable } from "../parametres/ParamValueTable";

interface Param {
  id: string;
  code: string;
  label: string;
  valeur: string;
  unite: string;
  est_provisoire: boolean;
}

const BASE = "/api/controle-gestion";
/** Tables RGM et cibles des KPI KP-M11-01 à 12 (mêmes clés de requête que l'écran M11 : aucun appel en double). */
const TABLES = [
  ["RGM_PARAM_STRUCTURE", "ecarts_m11.tables.param"],
  ["RGM_TAUX_STRUCTURE", "ecarts_m11.tables.taux"],
  ["RGM_POND_PROSPECT", "ecarts_m11.tables.pond"],
  ["KPI_CIBLES", "ecarts_m11.tables.kpi"],
] as const;

/**
 * Tables de paramétrage M11 (structure, taux, pondérations, cibles des KPI) : valeurs ETSL modifiables et confirmables,
 * provisoires par défaut. Extrait de `EcartsM11Section.tsx` (chantier « params ») : un panneau compact replié
 * « N paramètres provisoires à confirmer · Afficher » remplace le mur de 4 tableaux (B-05) ; les cibles KPI portent le
 * nom de l'indicateur, la référence KP-M11-xx passe en secondaire (B-06).
 */
export function ParametresRgmM11() {
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const tables = useQueries({
    queries: TABLES.map(([table]) => ({
      queryKey: ["m11e", "params", table],
      queryFn: () => api.listAll<Param>(`${BASE}/parametres/?table=${table}`),
      retry: 0,
    })),
  });
  const done = {
    onSuccess: () => {
      setError(null);
      void qc.invalidateQueries();
    },
    onError: (e: unknown) => setError(describeError(e)),
  };
  const save = useMutation({ mutationFn: (v: { id: string; valeur: string }) => api.patch(`${BASE}/parametres/${v.id}/`, { valeur: v.valeur }), ...done });
  const confirm = useMutation({ mutationFn: (id: string) => api.post(`${BASE}/parametres/${id}/confirmer/`), ...done });
  const charge = tables.every((q) => q.data !== undefined || q.isError);
  const lignes = tables.flatMap((q) => q.data ?? []);
  const exists = (k: string) => i18n.exists(k);
  return (
    <ParamsPanel
      variant="card"
      module="controle_gestion"
      title={t("ecarts_m11.tables.title")}
      count={charge ? lignes.filter((p) => p.est_provisoire).length : undefined}
      total={charge ? lignes.length : undefined}
      testId="parametres-rgm-m11"
    >
      <p className="muted">{t("ecarts_m11.bandeau")}</p>
      {error && (
        <p className="action-error" role="alert">
          {error}
        </p>
      )}
      {TABLES.map(([table, titre], i) => (
        <div key={table} data-testid={`table-${table}`}>
          <h4 className="section-heading">{t(titre)}</h4>
          <ParamValueTable
            rows={tables[i]?.data ?? []}
            caption={t(titre)}
            libelle={(p) => libelleParametre(t, { ...p, module: "controle_gestion" })}
            secondaire={(p) => referenceKpi(p.code)}
            valeur={(p) => valeurScalaire(t, exists, { ...p, type_valeur: "decimal" })}
            step="0.01"
            pending={save.isPending || confirm.isPending}
            onSave={(id, valeur) => save.mutateAsync({ id, valeur })}
            onConfirm={(id) => confirm.mutate(id)}
          />
        </div>
      ))}
    </ParamsPanel>
  );
}
