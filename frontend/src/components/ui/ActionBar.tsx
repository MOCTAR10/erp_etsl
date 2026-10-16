import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../../api/client";
import { describeError } from "../../lib/offlineQueue";

export interface ActionDef {
  label: string;
  /** Chemin de l'action DRF (POST), ex. `/api/hse/permis/<id>/valider/`. */
  path: string;
  body?: unknown;
  tone?: "primary" | "ghost" | "danger";
  /** Demande de confirmation avant d'exécuter (actions engageantes : comptabiliser, clôturer…). */
  confirm?: string;
}

/**
 * Barre d'actions de workflow : chaque bouton appelle l'action dédiée du serveur (les rôles de validation et
 * les contrôles métier restent côté API) ; un refus s'affiche en clair sous la barre, les listes sont rechargées.
 */
export function ActionBar({ actions }: { actions: ActionDef[] }) {
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const run = useMutation({
    mutationFn: (a: ActionDef) => api.post<unknown>(a.path, a.body),
    onSuccess: () => {
      setError(null);
      void qc.invalidateQueries();
    },
    onError: (e) => setError(describeError(e)),
  });

  if (actions.length === 0) return null;
  return (
    <div className="action-bar">
      <div className="action-bar-buttons">
        {actions.map((a) => (
          <button
            key={a.label}
            type="button"
            className={`btn ${a.tone ?? "primary"}`}
            disabled={run.isPending}
            onClick={() => {
              if (a.confirm && !window.confirm(a.confirm)) return;
              run.mutate(a);
            }}
          >
            {a.label}
          </button>
        ))}
      </div>
      {error && (
        <p className="action-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
