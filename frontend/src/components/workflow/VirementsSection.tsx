import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate, formatNumber } from "../../lib/format";
import { describeError } from "../../lib/offlineQueue";
import type { Employe } from "../../types";
import { SectionCard } from "../ui";

interface Compte {
  id: string;
  raison_sociale: string;
  numero_emetteur: string;
  code_banque: string;
  code_guichet: string;
  numero_compte: string;
  cle_rib: string;
}
interface Ordre {
  id: string;
  code: string;
  periode: string;
  compte_label: string;
  nb_virements: number;
  total: string;
  par_email: string | null;
}

const COMPTE_VIDE = { raison_sociale: "", numero_emetteur: "", code_banque: "", code_guichet: "", numero_compte: "", cle_rib: "" };
const RIB_VIDE = { employe: "", rib_banque: "", rib_guichet: "", rib_compte: "", rib_cle: "", banque_nom: "" };

/** Virement des salaires (CFONB 160) : compte émetteur, RIB des salariés, génération et téléchargement. */
export function VirementsSection() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const comptes = useQuery({
    queryKey: ["comptes-emetteurs"],
    queryFn: () => api.listAll<Compte>("/api/rh-paie/comptes-emetteurs/"),
    retry: 0,
  });
  const ordres = useQuery({
    queryKey: ["ordres-virement"],
    queryFn: () => api.listAll<Ordre>("/api/rh-paie/ordres-virement/"),
    retry: 0,
  });
  const employes = useQuery({
    queryKey: ["employes-rib"],
    queryFn: () => api.listAll<Employe>("/api/rh-paie/employes/"),
    retry: 0,
  });
  const [compte, setCompte] = useState(COMPTE_VIDE);
  const [rib, setRib] = useState(RIB_VIDE);
  const [gen, setGen] = useState({ periode: "", compte: "", date_execution: "" });
  const [error, setError] = useState<string | null>(null);
  const onError = (e: unknown) => setError(describeError(e));
  const refresh = (k: string) => () => {
    setError(null);
    void qc.invalidateQueries({ queryKey: [k] });
  };

  const addCompte = useMutation({
    mutationFn: () => api.post("/api/rh-paie/comptes-emetteurs/", compte),
    onSuccess: () => {
      setCompte(COMPTE_VIDE);
      refresh("comptes-emetteurs")();
    },
    onError,
  });
  const saveRib = useMutation({
    mutationFn: () => {
      const { employe, ...champs } = rib;
      return api.patch(`/api/rh-paie/employes/${employe}/`, champs);
    },
    onSuccess: () => {
      setRib(RIB_VIDE);
      refresh("employes-rib")();
    },
    onError,
  });
  const generer = useMutation({
    mutationFn: () => api.post("/api/rh-paie/ordres-virement/generer/", gen),
    onSuccess: refresh("ordres-virement"),
    onError,
  });

  if (comptes.isError) return null; // hors cercle paie : la section n'apparaît pas
  const f = (k: keyof typeof compte, label: string) => (
    <input required aria-label={label} placeholder={label} value={compte[k]} onChange={(e) => setCompte({ ...compte, [k]: e.target.value })} />
  );
  const r = (k: keyof typeof rib, label: string) => (
    <input aria-label={label} placeholder={label} value={rib[k]} onChange={(e) => setRib({ ...rib, [k]: e.target.value })} />
  );

  return (
    <SectionCard title={t("virements.title")}>
      <p className="muted">{t("virements.hint")}</p>

      <h4 className="subtitle">{t("virements.generer")}</h4>
      <form
        className="bareme-form"
        onSubmit={(e) => {
          e.preventDefault();
          generer.mutate();
        }}
      >
        <input required type="date" aria-label={t("virements.periode")} value={gen.periode} onChange={(e) => setGen({ ...gen, periode: e.target.value })} />
        <select required aria-label={t("virements.compte")} value={gen.compte} onChange={(e) => setGen({ ...gen, compte: e.target.value })}>
          <option value="">{t("virements.compte")}</option>
          {(comptes.data ?? []).map((c) => (
            <option key={c.id} value={c.id}>
              {c.raison_sociale} — {c.numero_compte}
            </option>
          ))}
        </select>
        <input required type="date" aria-label={t("virements.execution")} value={gen.date_execution} onChange={(e) => setGen({ ...gen, date_execution: e.target.value })} />
        <button className="btn" type="submit" disabled={generer.isPending}>
          {t("virements.generer")}
        </button>
      </form>
      {error && (
        <p className="action-error" role="alert">
          {error}
        </p>
      )}

      {(ordres.data ?? []).length > 0 && (
        <table className="table">
          <tbody>
            {(ordres.data ?? []).map((o) => (
              <tr key={o.id}>
                <td>
                  <strong>{o.code}</strong> · {formatDate(o.periode)}
                  <div className="muted">
                    {o.compte_label} · {o.par_email ?? "—"}
                  </div>
                </td>
                <td>
                  {o.nb_virements} · {formatNumber(o.total)} F
                </td>
                <td>
                  <button type="button" className="btn" onClick={() => void api.download(`/api/rh-paie/ordres-virement/${o.id}/fichier/`, `${o.code}.cfonb`)}>
                    {t("virements.telecharger")}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h4 className="subtitle">{t("virements.compteTitle")}</h4>
      <form
        className="bareme-form"
        onSubmit={(e) => {
          e.preventDefault();
          addCompte.mutate();
        }}
      >
        {f("raison_sociale", t("virements.raison"))}
        {f("numero_emetteur", t("virements.emetteur"))}
        {f("code_banque", t("virements.banque"))}
        {f("code_guichet", t("virements.guichet"))}
        {f("numero_compte", t("virements.numCompte"))}
        {f("cle_rib", t("virements.cle"))}
        <button className="btn" type="submit" disabled={addCompte.isPending}>
          {t("virements.ajouterCompte")}
        </button>
      </form>

      <h4 className="subtitle">{t("virements.ribTitle")}</h4>
      <form
        className="bareme-form"
        onSubmit={(e) => {
          e.preventDefault();
          saveRib.mutate();
        }}
      >
        <select required aria-label={t("virements.employe")} value={rib.employe} onChange={(e) => setRib({ ...rib, employe: e.target.value })}>
          <option value="">{t("virements.employe")}</option>
          {(employes.data ?? []).map((e) => (
            <option key={e.id} value={e.id}>
              {e.code} — {e.nom_complet}
            </option>
          ))}
        </select>
        {r("rib_banque", t("virements.banque"))}
        {r("rib_guichet", t("virements.guichet"))}
        {r("rib_compte", t("virements.numCompte"))}
        {r("rib_cle", t("virements.cle"))}
        {r("banque_nom", t("virements.domiciliation"))}
        <button className="btn" type="submit" disabled={saveRib.isPending}>
          {t("virements.majRib")}
        </button>
      </form>
    </SectionCard>
  );
}
