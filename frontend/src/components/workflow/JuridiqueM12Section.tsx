import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { describeError } from "../../lib/offlineQueue";
import type { DocumentTypeOfficiel, Paginated, RechercheJuridiqueResult } from "../../types";
import { Badge, SectionCard } from "../ui";

/** Types d'objets métier liables (M1-M11) : identique à la liste blanche du backend. */
const OBJETS_LIEABLES = [
  "commercial.affaire", "commercial.contract", "commercial.avenant", "commercial.estimate",
  "achats.purchaserequest", "achats.purchaseorder", "achats.litigefournisseur",
  "operations.ordrefabrication", "operations.dossieroperationnel", "logistique.locationgr",
  "stocks.lotmatiere", "qualite.nonconformite", "qualite.pvcontrole", "hse.permistravail", "hse.incident",
  "maintenance.ordretravail", "comptabilite.factureclient", "controle_gestion.budget",
] as const;
const MODULES = ["M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8", "M10", "M11"];

/** Recherche juridique interconnectée : documents GED retrouvés par leur texte ou par l'objet métier lié. */
export function RechercheJuridiqueSection() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [saisie, setSaisie] = useState("");
  const [q, setQ] = useState("");
  const [module, setModule] = useState("");
  const [document, setDocument] = useState("");
  const [objetType, setObjetType] = useState<string>(OBJETS_LIEABLES[0]);
  const [objetId, setObjetId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  const resultat = useQuery({
    queryKey: ["jur-recherche", q, module],
    queryFn: () =>
      api.get<RechercheJuridiqueResult>(`/api/juridique/recherche/?q=${encodeURIComponent(q)}${module ? `&module=${module}` : ""}`),
    enabled: q.length >= 2,
    retry: 0,
  });
  const lier = useMutation({
    mutationFn: () => api.post("/api/juridique/liens/", { document, objet_type: objetType, objet_id: objetId }),
    onSuccess: () => {
      setError(null);
      setInfo(t("rechercheJuridique.lie"));
      setObjetId("");
      void qc.invalidateQueries({ queryKey: ["jur-recherche"] });
    },
    onError: (e) => {
      setInfo(null);
      setError(describeError(e));
    },
  });

  return (
    <SectionCard title={t("rechercheJuridique.title")}>
      <div data-testid="recherche-juridique">
        <p className="muted">{t("rechercheJuridique.hint")}</p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setQ(saisie.trim());
          }}
          style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", alignItems: "center" }}
        >
          <input type="search" aria-label={t("rechercheJuridique.terme")} placeholder={t("rechercheJuridique.terme")} value={saisie} onChange={(e) => setSaisie(e.target.value)} />
          <select aria-label={t("rechercheJuridique.module")} value={module} onChange={(e) => setModule(e.target.value)}>
            <option value="">{t("rechercheJuridique.tousModules")}</option>
            {MODULES.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
          <button type="submit" className="btn" disabled={saisie.trim().length < 2}>{t("rechercheJuridique.chercher")}</button>
        </form>
        {resultat.isError && <p className="action-error" role="alert">{describeError(resultat.error)}</p>}
        {resultat.data && resultat.data.documents.length === 0 && <p className="muted">{t("rechercheJuridique.aucun")}</p>}
        {resultat.data && resultat.data.documents.length > 0 && (
          <table className="table" data-testid="resultats-recherche">
            <thead>
              <tr>
                <th>{t("rechercheJuridique.document")}</th>
                <th>{t("rechercheJuridique.liens")}</th>
              </tr>
            </thead>
            <tbody>
              {resultat.data.documents.map((d) => (
                <tr key={d.id}>
                  <td>{d.title}{d.reference ? ` · ${d.reference}` : ""}</td>
                  <td>
                    {d.liens.length === 0 ? "—" : d.liens.map((l) => (
                      <span key={`${l.objet_type}-${l.objet_id}`}><Badge tone="brand">{l.module}</Badge> {l.objet_label}{" "}</span>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {resultat.data && resultat.data.documents.length > 0 && (
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", alignItems: "center", marginTop: "0.5rem" }}>
            <select aria-label={t("rechercheJuridique.document")} value={document} onChange={(e) => setDocument(e.target.value)}>
              <option value="">{t("rechercheJuridique.document")}</option>
              {resultat.data.documents.map((d) => <option key={d.id} value={d.id}>{d.title}</option>)}
            </select>
            <select aria-label={t("rechercheJuridique.objetType")} value={objetType} onChange={(e) => setObjetType(e.target.value)}>
              {OBJETS_LIEABLES.map((o) => <option key={o} value={o}>{o}</option>)}
            </select>
            <input aria-label={t("rechercheJuridique.objetId")} placeholder={t("rechercheJuridique.objetId")} value={objetId} onChange={(e) => setObjetId(e.target.value)} />
            <button type="button" className="btn ghost" disabled={!document || !objetId || lier.isPending} onClick={() => lier.mutate()}>
              {t("rechercheJuridique.lier")}
            </button>
          </div>
        )}
        {error && <p className="action-error" role="alert">{error}</p>}
        {info && <p className="muted" role="status">{info}</p>}
      </div>
    </SectionCard>
  );
}

/** Types de documents officiels (signés et scellés) : liste paramétrable par ETSL, provisoire jusqu'à confirmation. */
export function DocumentsOfficielsSection() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const types = useQuery({
    queryKey: ["doc-types-officiels"],
    queryFn: () => api.get<Paginated<DocumentTypeOfficiel> | DocumentTypeOfficiel[]>("/api/documents/types/?page_size=100").then((p) => (Array.isArray(p) ? p : p.results)),
    retry: 0,
  });
  const refresh = () => void qc.invalidateQueries({ queryKey: ["doc-types-officiels"] });
  const definir = useMutation({
    mutationFn: (v: { id: string; officiel: boolean }) => api.post(`/api/documents/types/${v.id}/definir-officiel/`, { officiel: v.officiel }),
    onSuccess: () => {
      setError(null);
      refresh();
    },
    onError: (e) => setError(describeError(e)),
  });
  const confirmer = useMutation({
    mutationFn: (id: string) => api.post(`/api/documents/types/${id}/confirmer-officiel/`),
    onSuccess: () => {
      setError(null);
      refresh();
    },
    onError: (e) => setError(describeError(e)),
  });

  if (types.isError) return null;
  const rows = types.data ?? [];
  const provisoires = rows.filter((r) => r.officiel_provisoire).length;
  return (
    <SectionCard title={t("docsOfficiels.title")}>
      <div data-testid="documents-officiels">
        <p className="muted">{t("docsOfficiels.hint")}</p>
        {provisoires > 0 && (
          <p className="action-error" role="note" data-testid="alerte-provisoire-officiels">
            {t("docsOfficiels.warnProvisoire", { count: provisoires })}
          </p>
        )}
        {error && <p className="action-error" role="alert">{error}</p>}
        <table className="table">
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>{r.label}</td>
                <td>{r.officiel ? <Badge tone={r.officiel_provisoire ? "warn" : "ok"}>{r.officiel_provisoire ? t("docsOfficiels.provisoire") : t("docsOfficiels.confirme")}</Badge> : "—"}</td>
                <td>
                  <button type="button" className="btn ghost" onClick={() => definir.mutate({ id: r.id, officiel: !r.officiel })}>
                    {r.officiel ? t("docsOfficiels.retirer") : t("docsOfficiels.marquer")}
                  </button>{" "}
                  {r.officiel_provisoire && (
                    <button type="button" className="btn ghost" onClick={() => window.confirm(t("docsOfficiels.confirmConfirmer")) && confirmer.mutate(r.id)}>
                      {t("docsOfficiels.confirmer")}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </SectionCard>
  );
}
