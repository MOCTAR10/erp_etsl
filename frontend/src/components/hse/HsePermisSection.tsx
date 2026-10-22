import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState, type ChangeEvent } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatNumber } from "../../lib/format";
import { describeError } from "../../lib/offlineQueue";
import type { CoutsHseResult, PermisTravail, PersonnelHse } from "../../types";
import { ActionBar, QuickForm, SectionCard } from "../ui";
import { useListeHse } from "./listesHse";

const FIGES = ["cloture", "refuse", "annule", "expire"];

/** Demande de permis de travail à l'écran (CDC M7-11) : le demandeur est l'utilisateur connecté. */
export function DemandePermisForm() {
  const { t } = useTranslation();
  const types = useListeHse("type_permis");
  // Plans de prévention validés (site GR : exigés au démarrage, écarts M7) ; liste vide si non lisible.
  const plans = useQuery({
    queryKey: ["ecarts-m6m7", "plans-valides"],
    queryFn: () => api.listAll<{ id: string; code: string; site: string }>("/api/hse/plans-prevention/?statut=valide"),
    retry: 0,
  }).data ?? [];
  return (
    <QuickForm
      title={t("m7e.permisEcran.demander")}
      endpoint="/api/hse/permis/"
      transform={(v) => ({ ...v, site_gr: v.site_gr === "true" })}
      fields={[
        { name: "type_permis", label: t("m7e.permisEcran.type"), type: "select", required: true, defaultValue: "chaud", options: types },
        { name: "emplacement", label: t("m7e.permisEcran.emplacement"), required: true },
        { name: "description", label: t("m7e.permisEcran.description"), type: "textarea", required: true },
        { name: "mesures", label: t("m7e.permisEcran.mesures"), type: "textarea" },
        { name: "date_debut", label: t("m7e.permisEcran.debut"), type: "date", required: true },
        { name: "date_fin", label: t("m7e.permisEcran.fin"), type: "date" },
        { name: "site_gr", label: t("ecarts_m6m7.gr.siteGr"), type: "select", defaultValue: "false", options: [{ value: "false", label: t("ecarts_m6m7.non") }, { value: "true", label: t("ecarts_m6m7.oui") }] },
        { name: "plan_prevention", label: t("ecarts_m6m7.gr.planPrevention"), type: "select", options: plans.map((p) => ({ value: p.id, label: `${p.code} · ${p.site}` })) },
      ]}
    />
  );
}

/** Intervenants et pièces jointes (photo de la zone, plan) d'un permis encore ouvert. */
export function PermisPieces({ permis }: { permis: PermisTravail }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const photo = useRef<HTMLInputElement>(null);
  const plan = useRef<HTMLInputElement>(null);
  const ouvert = !FIGES.includes(permis.statut);
  const personnel = useQuery({
    queryKey: ["hse-personnel"],
    queryFn: () => api.listAll<PersonnelHse>("/api/hse/personnel/"),
    enabled: ouvert,
    retry: 0,
  });
  const joindre = useMutation({
    mutationFn: (v: { piece: "photo" | "plan"; fichier: File }) => api.upload(`/api/hse/permis/${permis.id}/joindre-${v.piece}/`, v.fichier),
    onSuccess: () => {
      setError(null);
      void qc.invalidateQueries();
    },
    onError: (e) => setError(describeError(e)),
  });
  const options = (personnel.data ?? []).map((p) => ({ value: p.id, label: `${p.code} · ${p.nom_complet}` }));
  const fichier = (piece: "photo" | "plan") => (e: ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) joindre.mutate({ piece, fichier: f });
    e.target.value = "";
  };
  return (
    <div className="permis-pieces">
      {(permis.intervenants_noms ?? []).length > 0 && (
        <p className="muted">{t("m7e.permisEcran.intervenants")} : {(permis.intervenants_noms ?? []).join(", ")}</p>
      )}
      {permis.photo && <a href={permis.photo} target="_blank" rel="noreferrer">{t("m7e.permisEcran.voirPhoto")}</a>}{" "}
      {permis.plan && <a href={permis.plan} target="_blank" rel="noreferrer">{t("m7e.permisEcran.voirPlan")}</a>}
      {ouvert && (
        <div className="action-bar-buttons">
          {options.length > 0 && (
            <ActionBar
              actions={[{
                label: t("m7e.permisEcran.intervenant"), path: `/api/hse/permis/${permis.id}/ajouter-intervenant/`, tone: "ghost",
                prompt: { name: "employe", label: t("m7e.permisEcran.salarie"), options },
              }]}
            />
          )}
          <button type="button" className="btn ghost" onClick={() => photo.current?.click()}>{t("m7e.permisEcran.photo")}</button>
          <button type="button" className="btn ghost" onClick={() => plan.current?.click()}>{t("m7e.permisEcran.plan")}</button>
          <input ref={photo} type="file" accept="image/*" capture="environment" hidden aria-label={t("m7e.permisEcran.photo")} onChange={fichier("photo")} />
          <input ref={plan} type="file" accept="application/pdf,image/*" hidden aria-label={t("m7e.permisEcran.plan")} onChange={fichier("plan")} />
        </div>
      )}
      {error && <p className="action-error" role="alert">{error}</p>}
    </div>
  );
}

const montant = (v: string | null) => (v === null ? "—" : formatNumber(Number(v)));

/** Coûts HSE par centre analytique (CDC M7 → M11) : lus dans la comptabilité, masqués hors cercle des montants. */
export function CoutsHseSection() {
  const { t } = useTranslation();
  const [annee, setAnnee] = useState(String(new Date().getFullYear()));
  const q = useQuery({
    queryKey: ["cg-couts-hse", annee],
    queryFn: () => api.get<CoutsHseResult>(`/api/controle-gestion/couts-hse/?annee=${annee}`),
    enabled: /^\d{4}$/.test(annee),
    retry: 0,
  });
  if (q.isError && !q.data) return null;
  const rows = (q.data?.rows ?? []).filter((r) => r.total === null || Number(r.total) !== 0);
  return (
    <SectionCard title={t("m7e.couts.title")}>
      <div data-testid="couts-hse">
        <p className="muted">{t("m7e.couts.hint")}</p>
        <label>
          {t("m7e.couts.annee")}{" "}
          <input type="number" min={2000} max={2100} value={annee} onChange={(e) => setAnnee(e.target.value)} aria-label={t("m7e.couts.annee")} />
        </label>
        {q.data && rows.length === 0 ? (
          <p className="muted">{t("m7e.couts.aucun")}</p>
        ) : (
          <table className="table">
            <thead>
              <tr><th>{t("m7e.couts.centre")}</th><th className="num">{t("m7e.couts.total")}</th></tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.centre}>
                  <td>{r.centre} — {r.libelle}</td>
                  <td className="num">{montant(r.total)}</td>
                </tr>
              ))}
              {q.data && (
                <tr>
                  <td><strong>{t("m7e.couts.total")}</strong></td>
                  <td className="num"><strong>{montant(q.data.total)}</strong></td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>
    </SectionCard>
  );
}
