import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useId, useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { describeError } from "../../lib/offlineQueue";

export interface ActionDef {
  label: string;
  /** Chemin de l'action DRF (POST), ex. `/api/hse/permis/<id>/valider/`. */
  path: string;
  body?: unknown;
  /** Verbe HTTP : POST (action DRF, défaut) ou PATCH (modification d'un champ, ex. circuit à chaud). */
  method?: "POST" | "PATCH";
  tone?: "primary" | "ghost" | "danger";
  /** Demande de confirmation avant d'exécuter (actions engageantes : comptabiliser, clôturer…). */
  confirm?: string;
  /**
   * Valeur saisie avant l'action, envoyée dans le corps sous `name` (rapport, motif, relevé de compteur…).
   * Sans `options` : saisie libre ; avec `options` : liste de choix + bouton de confirmation. Annuler = pas d'appel.
   */
  prompt?: { name: string; label: string; options?: { value: string; label: string }[] };
}

/**
 * Barre d'actions de workflow : chaque bouton appelle l'action dédiée du serveur (les rôles de validation et
 * les contrôles métier restent côté API) ; un refus s'affiche en clair sous la barre, les listes sont rechargées.
 */
export function ActionBar({ actions }: { actions: ActionDef[] }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const uid = useId();
  const [error, setError] = useState<string | null>(null);
  const [choosing, setChoosing] = useState<ActionDef | null>(null);
  const [choice, setChoice] = useState("");
  const run = useMutation({
    mutationFn: (a: ActionDef) => (a.method === "PATCH" ? api.patch<unknown>(a.path, a.body ?? {}) : api.post<unknown>(a.path, a.body)),
    onSuccess: () => {
      setError(null);
      setChoosing(null);
      void qc.invalidateQueries();
    },
    onError: (e) => setError(describeError(e)),
  });
  const withValue = (a: ActionDef, value: string) =>
    run.mutate({ ...a, body: { ...((a.body as object) ?? {}), [a.prompt!.name]: value } });

  if (actions.length === 0) return null;
  return (
    <div className="action-bar">
      {choosing?.prompt?.options ? (
        <div className="action-bar-buttons">
          <label className="sr-only" htmlFor={`${uid}-choice`}>
            {choosing.prompt.label}
          </label>
          <select id={`${uid}-choice`} value={choice} onChange={(e) => setChoice(e.target.value)} autoFocus>
            <option value="">{choosing.prompt.label}</option>
            {choosing.prompt.options.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
          <button type="button" className="btn primary" disabled={!choice || run.isPending} onClick={() => withValue(choosing, choice)}>
            {t("actionBar.confirmer")}
          </button>
          <button type="button" className="btn ghost" onClick={() => setChoosing(null)}>
            {t("actionBar.annuler")}
          </button>
        </div>
      ) : (
        <div className="action-bar-buttons">
          {actions.map((a) => (
            <button
              key={a.label}
              type="button"
              className={`btn ${a.tone ?? "primary"}`}
              disabled={run.isPending}
              onClick={() => {
                if (a.confirm && !window.confirm(a.confirm)) return;
                if (a.prompt?.options) {
                  setChoice("");
                  setChoosing(a);
                  return;
                }
                if (a.prompt) {
                  const value = window.prompt(a.prompt.label);
                  if (value === null) return;
                  withValue(a, value);
                  return;
                }
                run.mutate(a);
              }}
            >
              {a.label}
            </button>
          ))}
        </div>
      )}
      {error && (
        <p className="action-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
