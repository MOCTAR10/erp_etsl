import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { ParamStatusBadge } from "./ParamsPanel";

/** Paramètre simple (code, libellé, valeur numérique, unité) servi par les endpoints `…/parametres/` des modules. */
export interface ParamLigne {
  id: string;
  code?: string;
  label: string;
  valeur: string;
  unite?: string;
  est_provisoire: boolean;
}

/**
 * Tableau de paramètres d'un écran métier (motif de ligne partagé, A-36) : libellé en premier (code en secondaire),
 * valeur lisible, statut court, et « Modifier » → « Valider » / « Annuler » puis « Confirmer » (même taille, B-28).
 * Les rôles et intitulés de boutons sont ceux des parcours E2E (« Modifier », « Valider », « Confirmer »).
 */
export function ParamValueTable<P extends ParamLigne>({
  rows,
  caption,
  libelle,
  valeur,
  showCode = false,
  secondaire,
  onSave,
  onConfirm,
  confirmMessage,
  pending = false,
  min = "0",
  step = "1",
}: {
  rows: P[];
  caption: string;
  /** Libellé humain (i18n) ; par défaut `label` du serveur. */
  libelle?: (p: P) => string;
  /** Valeur affichée (« 30 jours », « 5 % ») ; par défaut la valeur brute. */
  valeur?: (p: P) => ReactNode;
  showCode?: boolean;
  /** Mention secondaire sous le libellé (remplace le code quand elle est fournie). */
  secondaire?: (p: P) => string | undefined;
  /** Enregistre la valeur ; la promesse résolue referme l'éditeur. */
  onSave: (id: string, valeur: string) => Promise<unknown>;
  onConfirm: (id: string) => void;
  /** Question posée avant la confirmation (window.confirm) ; aucune si omise. */
  confirmMessage?: string;
  pending?: boolean;
  min?: string;
  step?: string;
}) {
  const { t } = useTranslation();
  const [edit, setEdit] = useState<{ id: string; valeur: string } | null>(null);
  const nom = (p: P) => (libelle ? libelle(p) : p.label);
  return (
    <div className="table-wrap">
      <table className="table">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            <th>{t("revueKit.ops.param.parametre")}</th>
            <th className="num">{t("revueKit.ops.param.valeur")}</th>
            <th>{t("revueKit.ops.param.statut")}</th>
            <th>
              <span className="sr-only">{t("revueKit.ops.param.actions")}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((p) => (
            <tr key={p.id}>
              <td>
                <div className="param-row-label">
                  <strong>{nom(p)}</strong>
                  {secondaire?.(p) ? (
                    <span className="param-code">{secondaire(p)}</span>
                  ) : showCode && p.code ? (
                    <span className="param-code">{p.code}</span>
                  ) : null}
                </div>
              </td>
              <td className="num cell-nowrap">
                {edit?.id === p.id ? (
                  <input
                    type="number"
                    className="control"
                    min={min}
                    step={step}
                    aria-label={nom(p)}
                    value={edit.valeur}
                    onChange={(e) => setEdit({ id: p.id, valeur: e.target.value })}
                  />
                ) : valeur ? (
                  valeur(p)
                ) : (
                  p.valeur
                )}
              </td>
              <td>
                <ParamStatusBadge provisoire={p.est_provisoire} />
              </td>
              <td>
                <div className="card-actions card-actions--end">
                  {edit?.id === p.id ? (
                    <>
                      <button
                        type="button"
                        className="btn primary sm"
                        disabled={pending}
                        onClick={() => void onSave(edit.id, edit.valeur).then(() => setEdit(null), () => undefined)}
                      >
                        {t("pilotageGestion.valider")}
                      </button>
                      <button type="button" className="btn ghost sm" onClick={() => setEdit(null)}>
                        {t("pilotageGestion.annuler")}
                      </button>
                    </>
                  ) : (
                    <>
                      <button type="button" className="btn ghost sm" onClick={() => setEdit({ id: p.id, valeur: p.valeur })}>
                        {t("pilotageGestion.modifier")}
                      </button>
                      {p.est_provisoire && (
                        <button
                          type="button"
                          className="btn ghost sm"
                          disabled={pending}
                          onClick={() => (!confirmMessage || window.confirm(confirmMessage)) && onConfirm(p.id)}
                        >
                          {t("pilotageGestion.confirmer")}
                        </button>
                      )}
                    </>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
