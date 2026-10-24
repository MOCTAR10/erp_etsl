import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate } from "../../lib/format";
import { describeError } from "../../lib/offlineQueue";
import type { AptitudeMedicale, ExigenceHabilitationHse, FormationSecurite, PasseportSecurite, PersonnelHse } from "../../types";
import { SectionActions } from "../sections/SectionActions";
import { ActionBar, Badge, DataTable, QuickForm, SectionCard } from "../ui";
import type { Column } from "../ui";
import { useListeHse } from "./listesHse";

const TYPES_EPI = ["casque", "lunettes", "ecran_facial", "protection_auditive", "gants", "chaussures", "veste_haute_visibilite", "harnais", "masque", "baudrier"];

function usePersonnel() {
  return useQuery({ queryKey: ["hse-personnel"], queryFn: () => api.listAll<PersonnelHse>("/api/hse/personnel/"), retry: 0 });
}

type LignePasseport = { id: string; element: ReactNode; debut: string | null; fin: ReactNode };

/** Personnel et sécurité : passeport sécurité, dotation EPI, aptitudes médicales. */
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
  const lignes: LignePasseport[] = p
    ? [
        ...p.qualifications.map((q) => ({
          id: `q-${q.intitule}-${q.obtention ?? ""}`,
          element: q.intitule,
          debut: q.obtention,
          fin: <Badge tone={q.valide ? "ok" : "err"}>{q.validite ? formatDate(q.validite) : t("m7e.perso.sansEcheance")}</Badge>,
        })),
        ...p.epi.map((e) => ({
          id: `e-${e.code}`,
          element: `EPI · ${t(`hse.epi_types.${e.type}`, { defaultValue: e.type })} — ${e.designation}`,
          debut: e.dotation,
          fin: e.renouvellement ? formatDate(e.renouvellement) : "—",
        })),
      ]
    : [];
  const colPasseport: Column<LignePasseport>[] = [
    { key: "element", header: t("tableaux.hse.element"), render: (l) => l.element },
    { key: "debut", header: t("tableaux.hse.obtention"), kind: "date", sortValue: (l) => l.debut, render: (l) => (l.debut ? formatDate(l.debut) : "—") },
    { key: "fin", header: t("tableaux.hse.validite"), render: (l) => l.fin },
  ];
  return (
    <SectionCard
      title={t("m7e.perso.title")}
      actions={
        <SectionActions>
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
        </SectionActions>
      }
    >
      <div data-testid="personnel-hse">
        <div className="field">
          <label htmlFor="passeport-salarie">{t("m7e.perso.salarie")}</label>
          <select id="passeport-salarie" className="control" aria-label={t("m7e.perso.passeportDe")} value={employe} onChange={(e) => setEmploye(e.target.value)} style={{ maxWidth: 420 }}>
            <option value="">{t("m7e.perso.choisir")}</option>
            {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </div>
        {employe && (
          <div className="action-bar-buttons">
            <button type="button" className="btn ghost" onClick={() => void api.download(`/api/hse/personnel/${employe}/passeport/?export=pdf`, "passeport-securite.pdf")}>
              {t("m7e.perso.passeportPdf")}
            </button>
            <button type="button" className="btn ghost" onClick={() => void api.download(`/api/hse/epis/fiche-dotation/?employe=${employe}&export=pdf`, "dotation-epi.pdf")}>
              {t("m7e.perso.dotationPdf")}
            </button>
          </div>
        )}
        {p && (
          <div data-testid="passeport-securite">
            <p>
              {p.aptitude ? (
                <Badge tone={p.aptitude.valide ? "ok" : "err"}>
                  {t("m7e.perso.aptitudeEtat", { resultat: t(`m7e.perso.resultats.${p.aptitude.resultat}`, { defaultValue: p.aptitude.resultat }) })}
                </Badge>
              ) : (
                <span className="muted">{t("m7e.perso.aptitudeInconnue")}</span>
              )}
            </p>
            <DataTable columns={colPasseport} rows={lignes} caption={t("m7e.perso.passeport")} emptyLabel={t("tableaux.hse.aucunePasseport")} />
          </div>
        )}
      </div>
    </SectionCard>
  );
}

/** Formations HSE nominatives : participants, validation de la session → qualification RH (recyclage). */
export function FormationsNominativesSection() {
  const { t } = useTranslation();
  const personnel = usePersonnel();
  const q = useQuery({ queryKey: ["hse-formations-nominatives"], queryFn: () => api.listAll<FormationSecurite>("/api/hse/formations/"), retry: 0 });
  if (q.isError) return null;
  const options = (personnel.data ?? []).map((p) => ({ value: p.id, label: `${p.code} · ${p.nom_complet}` }));
  const rows = (q.data ?? []).filter((f) => f.statut !== "annulee");
  const columns: Column<FormationSecurite>[] = [
    { key: "session", header: t("tableaux.hse.session"), sortValue: (f) => f.code, render: (f) => <><strong>{f.code}</strong> · {f.theme}</> },
    {
      key: "date",
      header: t("tableaux.hse.date"),
      sortValue: (f) => f.date_session,
      render: (f) => `${formatDate(f.date_session)}${f.validite_mois ? ` · ${t("m7e.form.recyclage", { n: f.validite_mois })}` : ""}`,
    },
    { key: "participants", header: t("tableaux.hse.participants"), render: (f) => (f.participants_noms ?? []).join(", ") || "—" },
    {
      key: "actions",
      header: <span className="sr-only">{t("ui.actions")}</span>,
      render: (f) => (
        <ActionBar
          actions={[
            ...(f.statut !== "realisee" ? [{ label: t("m7e.form.realiser"), path: `/api/hse/formations/${f.id}/realiser/` }] : []),
            { label: t("m7e.form.ajouter"), path: `/api/hse/formations/${f.id}/ajouter-participant/`, tone: "ghost" as const, prompt: { name: "employe", label: t("m7e.form.participant"), options } },
          ]}
        />
      ),
    },
  ];
  return (
    <SectionCard
      title={t("m7e.form.title")}
      actions={
        <SectionActions>
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
        </SectionActions>
      }
    >
      <div data-testid="formations-nominatives">
        <p className="muted">{t("m7e.form.hint")}</p>
        {rows.length > 0 && <DataTable columns={columns} rows={rows} caption={t("m7e.form.title")} />}
      </div>
    </SectionCard>
  );
}

/** Habilitations exigées par type de permis : donnée ETSL, contrôlée au démarrage du permis. */
export function ExigencesPermisSection() {
  const { t } = useTranslation();
  const typesPermis = useListeHse("type_permis");
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
  const columns: Column<ExigenceHabilitationHse>[] = [
    { key: "type", header: t("m7e.exig.typePermis"), render: (r) => t(`hse.permis_types.${r.type_permis}`) },
    { key: "motCle", header: t("m7e.exig.motCle"), sortValue: (r) => r.mot_cle, render: (r) => <strong>{r.mot_cle}</strong> },
    {
      key: "actions",
      header: <span className="sr-only">{t("ui.actions")}</span>,
      render: (r) => (
        <button type="button" className="btn ghost sm" onClick={() => window.confirm(t("m7e.exig.confirmSupprimer")) && supprimer.mutate(r.id)}>
          {t("m7e.exig.supprimer")}
        </button>
      ),
    },
  ];
  return (
    <SectionCard
      title={`${t("m7e.exig.title")} · ${rows.length}`}
      actions={
        <SectionActions>
          <QuickForm
            title={t("m7e.exig.nouvelle")}
            endpoint="/api/hse/exigences-habilitation/"
            fields={[
              { name: "type_permis", label: t("m7e.exig.typePermis"), type: "select", required: true, options: typesPermis },
              { name: "mot_cle", label: t("m7e.exig.motCle"), required: true },
            ]}
          />
        </SectionActions>
      }
    >
      <div data-testid="exigences-permis">
        <p className="muted">{t("m7e.exig.hint")}</p>
        {error && <p className="action-error" role="alert">{error}</p>}
        <DataTable columns={columns} rows={rows} caption={t("m7e.exig.title")} emptyLabel={t("m7e.exig.aucune")} />
      </div>
    </SectionCard>
  );
}

/** Aptitudes médicales récentes (cercle HSE / RH / direction ; la section n'apparaît pas aux autres rôles). */
export function AptitudesSection() {
  const { t } = useTranslation();
  const q = useQuery({ queryKey: ["hse-aptitudes"], queryFn: () => api.listAll<AptitudeMedicale>("/api/hse/aptitudes/"), retry: 0 });
  if (q.isError || !q.data || q.data.length === 0) return null;
  const columns: Column<AptitudeMedicale>[] = [
    { key: "salarie", header: t("m7e.perso.salarie"), sortValue: (a) => a.employe_nom, render: (a) => a.employe_nom },
    { key: "visite", header: t("m7e.perso.visite"), kind: "date", sortValue: (a) => a.date_visite, render: (a) => formatDate(a.date_visite) },
    {
      key: "resultat",
      header: t("m7e.perso.resultat"),
      render: (a) => <Badge tone={a.resultat === "inapte" ? "err" : a.resultat === "apte" ? "ok" : "warn"}>{a.resultat_label}</Badge>,
    },
    { key: "validite", header: t("m7e.perso.validite"), kind: "date", sortValue: (a) => a.date_validite, render: (a) => (a.date_validite ? formatDate(a.date_validite) : "—") },
  ];
  return (
    <SectionCard title={`${t("m7e.perso.aptitudes")} · ${q.data.length}`}>
      <div data-testid="aptitudes">
        <DataTable columns={columns} rows={q.data} caption={t("m7e.perso.aptitudes")} />
      </div>
    </SectionCard>
  );
}


/** Paramètres HSE : déplacés dans leur propre fichier (chantier « params »), réexportés pour les imports existants. */
export { ParametresHseSection } from "./ParametresHseSection";
