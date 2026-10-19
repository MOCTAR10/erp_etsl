import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate, formatNumber } from "../../lib/format";
import { describeError } from "../../lib/offlineQueue";
import type { AptitudeMedicale, ExigenceHabilitationHse, FormationSecurite, ParametreStock, PasseportSecurite, PersonnelHse } from "../../types";
import { ActionBar, Badge, QuickForm, SectionCard } from "../ui";

const TYPES_EPI = ["casque", "lunettes", "ecran_facial", "protection_auditive", "gants", "chaussures", "veste_haute_visibilite", "harnais", "masque", "baudrier"];
const TYPES_PERMIS = ["chaud", "hauteur", "levage", "confine", "atex", "froid", "electrique", "fouille", "chimique"];

function usePersonnel() {
  return useQuery({ queryKey: ["hse-personnel"], queryFn: () => api.listAll<PersonnelHse>("/api/hse/personnel/"), retry: 0 });
}

/** Personnel et sécurité (CDC M7-04 / M7-05 / §9.6) : passeport sécurité, dotation EPI, aptitudes médicales. */
export function PersonnelHseSection() {
  const { t } = useTranslation();
  const personnel = usePersonnel();
  const [employe, setEmploye] = useState("");
  const passeport = useQuery({
    queryKey: ["hse-passeport", employe],
    queryFn: () => api.get<PasseportSecurite>(`/api/hse/personnel/${employe}/passeport/`),
    enabled: Boolean(employe),
    retry: 0,
  });
  if (personnel.isError) return null;
  const options = (personnel.data ?? []).map((p) => ({ value: p.id, label: `${p.code} · ${p.nom_complet}` }));
  const p = passeport.data;
  return (
    <SectionCard title={t("m7e.perso.title")}>
      <div data-testid="personnel-hse">
        <div className="action-bar-buttons">
          <QuickForm
            title={t("m7e.perso.doterEpi")}
            endpoint="/api/hse/epis/"
            fields={[
              { name: "employe", label: t("m7e.perso.salarie"), type: "select", required: true, options },
              { name: "type_epi", label: t("m7e.perso.typeEpi"), type: "select", required: true, defaultValue: "casque", options: TYPES_EPI.map((v) => ({ value: v, label: t(`hse.epi_types.${v}`) })) },
              { name: "designation", label: t("m7e.perso.designation"), required: true },
              { name: "taille", label: t("m7e.perso.taille") },
              { name: "date_renouvellement", label: t("m7e.perso.renouvellement"), type: "date" },
            ]}
          />
          <QuickForm
            title={t("m7e.perso.aptitude")}
            endpoint="/api/hse/aptitudes/"
            fields={[
              { name: "employe", label: t("m7e.perso.salarie"), type: "select", required: true, options },
              { name: "date_visite", label: t("m7e.perso.visite"), type: "date", required: true },
              { name: "date_validite", label: t("m7e.perso.validite"), type: "date" },
              {
                name: "resultat", label: t("m7e.perso.resultat"), type: "select", required: true, defaultValue: "apte",
                options: ["apte", "apte_restrictions", "inapte"].map((v) => ({ value: v, label: t(`m7e.perso.resultats.${v}`) })),
              },
              { name: "restrictions", label: t("m7e.perso.restrictions"), type: "textarea" },
              { name: "medecin", label: t("m7e.perso.medecin") },
            ]}
          />
        </div>
        <label>
          {t("m7e.perso.salarie")}{" "}
          <select aria-label={t("m7e.perso.passeportDe")} value={employe} onChange={(e) => setEmploye(e.target.value)}>
            <option value="">{t("m7e.perso.choisir")}</option>
            {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </label>
        {employe && (
          <>
            {" "}
            <button type="button" className="btn ghost" onClick={() => void api.download(`/api/hse/personnel/${employe}/passeport/?export=pdf`, "passeport-securite.pdf")}>
              {t("m7e.perso.passeportPdf")}
            </button>{" "}
            <button type="button" className="btn ghost" onClick={() => void api.download(`/api/hse/epis/fiche-dotation/?employe=${employe}&export=pdf`, "dotation-epi.pdf")}>
              {t("m7e.perso.dotationPdf")}
            </button>
          </>
        )}
        {p && (
          <div data-testid="passeport-securite">
            <p>
              {p.aptitude ? (
                <Badge tone={p.aptitude.valide ? "ok" : "err"}>{t("m7e.perso.aptitudeEtat", { resultat: p.aptitude.resultat })}</Badge>
              ) : (
                <span className="muted">{t("m7e.perso.aptitudeInconnue")}</span>
              )}
            </p>
            <table className="table">
              <caption className="sr-only">{t("m7e.perso.passeport")}</caption>
              <tbody>
                {p.qualifications.map((q) => (
                  <tr key={`${q.intitule}-${q.obtention}`}>
                    <td>{q.intitule}</td>
                    <td>{q.obtention ? formatDate(q.obtention) : "—"}</td>
                    <td><Badge tone={q.valide ? "ok" : "err"}>{q.validite ? formatDate(q.validite) : t("m7e.perso.sansEcheance")}</Badge></td>
                  </tr>
                ))}
                {p.epi.map((e) => (
                  <tr key={e.code}>
                    <td>EPI · {e.type} — {e.designation}</td>
                    <td>{formatDate(e.dotation)}</td>
                    <td>{e.renouvellement ? formatDate(e.renouvellement) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </SectionCard>
  );
}

/** Formations HSE nominatives (CDC M7-05) : participants, validation de la session → qualification RH (recyclage). */
export function FormationsNominativesSection() {
  const { t } = useTranslation();
  const personnel = usePersonnel();
  const q = useQuery({ queryKey: ["hse-formations-nominatives"], queryFn: () => api.listAll<FormationSecurite>("/api/hse/formations/"), retry: 0 });
  if (q.isError) return null;
  const options = (personnel.data ?? []).map((p) => ({ value: p.id, label: `${p.code} · ${p.nom_complet}` }));
  const rows = (q.data ?? []).filter((f) => f.statut !== "annulee");
  return (
    <SectionCard title={t("m7e.form.title")}>
      <div data-testid="formations-nominatives">
        <p className="muted">{t("m7e.form.hint")}</p>
        <QuickForm
          title={t("m7e.form.nouvelle")}
          endpoint="/api/hse/formations/"
          fields={[
            {
              name: "type_session", label: t("m7e.form.type"), type: "select", required: true, defaultValue: "formation",
              options: ["formation", "demonstration", "causerie", "exercice", "campagne", "recyclage"].map((v) => ({ value: v, label: t(`m7e.form.types.${v}`) })),
            },
            { name: "theme", label: t("m7e.form.theme"), required: true },
            { name: "date_session", label: t("m7e.form.date"), type: "date", required: true },
            { name: "validite_mois", label: t("m7e.form.validite"), type: "number", min: 1, step: "1" },
            { name: "organisme", label: t("m7e.form.organisme") },
          ]}
        />
        {rows.length > 0 && (
          <table className="table">
            <caption className="sr-only">{t("m7e.form.title")}</caption>
            <tbody>
              {rows.map((f) => (
                <tr key={f.id}>
                  <td><strong>{f.code}</strong> · {f.theme}</td>
                  <td>{formatDate(f.date_session)}{f.validite_mois ? ` · ${t("m7e.form.recyclage", { n: f.validite_mois })}` : ""}</td>
                  <td>{(f.participants_noms ?? []).join(", ") || "—"}</td>
                  <td>
                    <ActionBar
                      actions={[
                        { label: t("m7e.form.ajouter"), path: `/api/hse/formations/${f.id}/ajouter-participant/`, tone: "ghost", prompt: { name: "employe", label: t("m7e.form.participant"), options } },
                        ...(f.statut !== "realisee" ? [{ label: t("m7e.form.realiser"), path: `/api/hse/formations/${f.id}/realiser/` }] : []),
                      ]}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </SectionCard>
  );
}

/** Habilitations exigées par type de permis (CDC M7-09) : donnée ETSL, contrôlée au démarrage du permis. */
export function ExigencesPermisSection() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const q = useQuery({ queryKey: ["hse-exigences"], queryFn: () => api.listAll<ExigenceHabilitationHse>("/api/hse/exigences-habilitation/"), retry: 0 });
  const supprimer = useMutation({
    mutationFn: (id: string) => api.remove(`/api/hse/exigences-habilitation/${id}/`),
    onSuccess: () => {
      setError(null);
      void qc.invalidateQueries({ queryKey: ["hse-exigences"] });
    },
    onError: (e) => setError(describeError(e)),
  });
  if (q.isError) return null;
  const rows = q.data ?? [];
  return (
    <SectionCard title={`${t("m7e.exig.title")} · ${rows.length}`}>
      <div data-testid="exigences-permis">
        <p className="muted">{t("m7e.exig.hint")}</p>
        <QuickForm
          title={t("m7e.exig.nouvelle")}
          endpoint="/api/hse/exigences-habilitation/"
          fields={[
            { name: "type_permis", label: t("m7e.exig.typePermis"), type: "select", required: true, options: TYPES_PERMIS.map((v) => ({ value: v, label: t(`hse.permis_types.${v}`) })) },
            { name: "mot_cle", label: t("m7e.exig.motCle"), required: true },
          ]}
        />
        {error && <p className="action-error" role="alert">{error}</p>}
        {rows.length === 0 ? (
          <p className="muted">{t("m7e.exig.aucune")}</p>
        ) : (
          <table className="table">
            <caption className="sr-only">{t("m7e.exig.title")}</caption>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td>{t(`hse.permis_types.${r.type_permis}`)}</td>
                  <td><strong>{r.mot_cle}</strong></td>
                  <td>
                    <button type="button" className="btn ghost" onClick={() => window.confirm(t("m7e.exig.confirmSupprimer")) && supprimer.mutate(r.id)}>
                      {t("m7e.exig.supprimer")}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </SectionCard>
  );
}

/** Aptitudes médicales récentes (cercle HSE / RH / direction ; la section n'apparaît pas aux autres rôles). */
export function AptitudesSection() {
  const { t } = useTranslation();
  const q = useQuery({ queryKey: ["hse-aptitudes"], queryFn: () => api.listAll<AptitudeMedicale>("/api/hse/aptitudes/"), retry: 0 });
  if (q.isError || !q.data || q.data.length === 0) return null;
  return (
    <SectionCard title={`${t("m7e.perso.aptitudes")} · ${q.data.length}`}>
      <table className="table" data-testid="aptitudes">
        <caption className="sr-only">{t("m7e.perso.aptitudes")}</caption>
        <tbody>
          {q.data.map((a) => (
            <tr key={a.id}>
              <td>{a.employe_nom}</td>
              <td>{formatDate(a.date_visite)}</td>
              <td><Badge tone={a.resultat === "inapte" ? "err" : a.resultat === "apte" ? "ok" : "warn"}>{a.resultat_label}</Badge></td>
              <td>{a.date_validite ? formatDate(a.date_validite) : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </SectionCard>
  );
}

/** Paramètres HSE (délais d'alerte EPI et aptitude) : provisoires jusqu'à confirmation par le HSE. */
export function ParametresHseSection() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const q = useQuery({ queryKey: ["hse-parametres"], queryFn: () => api.listAll<ParametreStock>("/api/hse/parametres/"), retry: 0 });
  const modifier = useMutation({
    mutationFn: (v: { id: string; valeur: string }) => api.patch(`/api/hse/parametres/${v.id}/`, { valeur: v.valeur }),
    onSuccess: () => {
      setError(null);
      void qc.invalidateQueries({ queryKey: ["hse-parametres"] });
    },
    onError: (e) => setError(describeError(e)),
  });
  if (q.isError || !q.data) return null;
  return (
    <SectionCard title={t("m7e.params.title")}>
      <table className="table" data-testid="parametres-hse">
        <caption className="sr-only">{t("m7e.params.title")}</caption>
        <tbody>
          {q.data.map((p) => (
            <tr key={p.id}>
              <td>{p.label}</td>
              <td className="num">{formatNumber(Number(p.valeur))} {p.unite}</td>
              <td><Badge tone={p.est_provisoire ? "warn" : "ok"}>{p.est_provisoire ? t("m5e.params.provisoire") : t("m5e.params.confirme")}</Badge></td>
              <td>
                <button
                  type="button"
                  className="btn ghost"
                  onClick={() => {
                    const v = window.prompt(p.label, p.valeur);
                    if (v !== null) modifier.mutate({ id: p.id, valeur: v });
                  }}
                >
                  {t("m5e.params.modifier")}
                </button>{" "}
                {p.est_provisoire && (
                  <ActionBar actions={[{ label: t("m5e.params.confirmer"), path: `/api/hse/parametres/${p.id}/confirmer/`, confirm: t("m5e.params.confirmConfirmer") }]} />
                )}
                {error && <span className="action-error" role="alert"> {error}</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </SectionCard>
  );
}
