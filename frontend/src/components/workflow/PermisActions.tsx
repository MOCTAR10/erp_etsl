import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { describeError } from "../../lib/offlineQueue";
import type { PermisTravail } from "../../types";
import { ActionBar, type ActionDef } from "../ui";

/** Actions de workflow d'un permis de travail + saisie du test gaz (CL-OM-07). */
export function PermisActions({ permis }: { permis: PermisTravail }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [resultat, setResultat] = useState<"conforme" | "non_conforme">("conforme");
  const [valeur, setValeur] = useState("");
  const [error, setError] = useState<string | null>(null);

  const base = `/api/hse/permis/${permis.id}`;
  const testGaz = useMutation({
    mutationFn: () => api.post(`${base}/test-gaz/`, { resultat, valeur }),
    onSuccess: () => {
      setOpen(false);
      setValeur("");
      setError(null);
      void qc.invalidateQueries();
    },
    onError: (e) => setError(describeError(e)),
  });

  const actions: ActionDef[] = [];
  if (permis.statut === "demande") actions.push({ label: t("actions.valider"), path: `${base}/valider/` });
  if (permis.statut === "demande")
    actions.push({ label: t("actions.refuser"), path: `${base}/valider/`, body: { accept: false, motif: "Refusé" }, tone: "danger" });
  if (permis.statut === "valide") actions.push({ label: t("actions.demarrer"), path: `${base}/demarrer/` });
  if (permis.statut === "valide" || permis.statut === "actif")
    actions.push({ label: t("actions.cloturer"), path: `${base}/cloturer/`, tone: "ghost", confirm: t("actions.confirmCloturer") });

  const gazPossible = permis.gaz_obligatoire && (permis.statut === "valide" || permis.statut === "actif");

  return (
    <div className="permis-actions">
      <ActionBar actions={actions} />
      {gazPossible && (
        <>
          <button type="button" className="btn ghost" onClick={() => setOpen((o) => !o)}>
            {t("actions.testGaz")}
          </button>
          {open && (
            <form
              className="gaz-form"
              onSubmit={(e) => {
                e.preventDefault();
                testGaz.mutate();
              }}
            >
              <select aria-label={t("terrain.fields.resultat")} value={resultat} onChange={(e) => setResultat(e.target.value as typeof resultat)}>
                <option value="conforme">{t("terrain.conforme")}</option>
                <option value="non_conforme">{t("terrain.nonConforme")}</option>
              </select>
              <input
                value={valeur}
                onChange={(e) => setValeur(e.target.value)}
                placeholder="LIE 0 %, O2 20,9 %, H2S 0 ppm"
                aria-label={t("terrain.fields.mesures")}
              />
              <button type="submit" className="btn" disabled={testGaz.isPending}>
                {t("terrain.save")}
              </button>
              {error && (
                <p className="action-error" role="alert">
                  {error}
                </p>
              )}
            </form>
          )}
        </>
      )}
    </div>
  );
}
