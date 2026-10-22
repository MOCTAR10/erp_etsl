import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, Download, FileText, ShieldCheck, Upload } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import { ActionBar, Badge, Kpi, PageHeader, PagedDataTable, SectionCard } from "../components/ui";
import type { BadgeTone, Column } from "../components/ui";
import { formatDate } from "../lib/format";
import { describeError } from "../lib/offlineQueue";
import { usePagedList } from "../lib/usePagedList";
import type { Paginated } from "../types";

interface DocType {
  id: number;
  code: string;
  label: string;
  retention_years: number | null;
  retention_provisoire: boolean;
  officiel: boolean;
}
interface DocRow {
  id: string;
  title: string;
  status: string;
  type: number | null;
  type_label: string | null;
  dossier_path: string | null;
  document_date: string | null;
  counterparty: string;
  project: string;
  reference: string;
  sha256: string;
  created_at: string;
}
interface Facets {
  total: number;
  by_status: Record<string, number>;
}
interface Verification {
  ok: boolean;
  expected_sha256: string;
  actual_sha256: string;
}

const STATUTS = ["draft", "in_validation", "rejected", "archived"] as const;
const TON: Record<string, BadgeTone> = { draft: "neutral", in_validation: "warn", rejected: "err", archived: "ok" };

/** Formulaire d'ajout d'un document (fichier + métadonnées) : POST multipart sur l'API GED existante. */
function AjoutDocument({ types }: { types: DocType[] }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [ouvert, setOuvert] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const envoi = useMutation({
    mutationFn: (form: HTMLFormElement) => {
      const data = new FormData(form);
      const fichier = data.get("file");
      if (!(fichier instanceof File) || fichier.size === 0) throw new Error(t("ecarts_tr.ged.fichierRequis"));
      const extra: Record<string, string> = {};
      for (const champ of ["title", "type", "document_date", "reference", "counterparty", "project"]) {
        const v = String(data.get(champ) ?? "").trim();
        if (v) extra[champ] = v;
      }
      return api.upload<unknown>("/api/documents/documents/", fichier, "file", extra);
    },
    onSuccess: (_d, form) => {
      form.reset();
      setMessage({ ok: true, text: t("quickForm.created") });
      void qc.invalidateQueries();
    },
    onError: (e) => setMessage({ ok: false, text: e instanceof Error && !("status" in e) ? e.message : describeError(e) }),
  });
  if (!ouvert)
    return (
      <button type="button" className="btn primary" onClick={() => setOuvert(true)}>
        <Upload size={16} aria-hidden="true" /> {t("ecarts_tr.ged.ajouter")}
      </button>
    );
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setMessage(null);
    envoi.mutate(e.currentTarget);
  };
  return (
    <form className="card quick-form" onSubmit={submit} aria-label={t("ecarts_tr.ged.ajouter")}>
      <div className="quick-form-head">
        <strong>{t("ecarts_tr.ged.ajouter")}</strong>
        <button type="button" className="icon-btn" aria-label={t("quickForm.close")} onClick={() => setOuvert(false)}>
          ×
        </button>
      </div>
      <div className="quick-form-grid">
        <div className="field">
          <label htmlFor="ged-title">{t("ecarts_tr.ged.titre")} *</label>
          <input id="ged-title" name="title" required />
        </div>
        <div className="field">
          <label htmlFor="ged-type">{t("ecarts_tr.ged.type")}</label>
          <select id="ged-type" name="type">
            <option value="">—</option>
            {types.map((ty) => (
              <option key={ty.id} value={ty.id}>
                {ty.label}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="ged-date">{t("ecarts_tr.ged.date")}</label>
          <input id="ged-date" name="document_date" type="date" />
        </div>
        <div className="field">
          <label htmlFor="ged-ref">{t("ecarts_tr.ged.reference")}</label>
          <input id="ged-ref" name="reference" />
        </div>
        <div className="field">
          <label htmlFor="ged-tiers">{t("ecarts_tr.ged.tiers")}</label>
          <input id="ged-tiers" name="counterparty" />
        </div>
        <div className="field">
          <label htmlFor="ged-projet">{t("ecarts_tr.ged.projet")}</label>
          <input id="ged-projet" name="project" />
        </div>
        <div className="field wide">
          <label htmlFor="ged-file">{t("ecarts_tr.ged.fichier")} *</label>
          <input id="ged-file" name="file" type="file" required />
        </div>
      </div>
      <div className="quick-form-actions">
        <button type="submit" className="btn primary" disabled={envoi.isPending}>
          {envoi.isPending ? t("common.loading") : t("quickForm.save")}
        </button>
        {message && (
          <p className={message.ok ? "quick-form-ok" : "action-error"} role={message.ok ? "status" : "alert"}>
            {message.text}
          </p>
        )}
      </div>
    </form>
  );
}

/** GED autonome (flux M12 → tous) : recherche plein texte, filtres, ajout, téléchargement, intégrité, circuit. */
export function DocumentsPage() {
  const { t } = useTranslation();
  const [statut, setStatut] = useState("");
  const [type, setType] = useState("");
  const [annee, setAnnee] = useState("");
  const [verif, setVerif] = useState<Record<string, Verification | string>>({});
  const filtres = new URLSearchParams();
  if (statut) filtres.set("status", statut);
  if (type) filtres.set("type", type);
  if (/^\d{4}$/.test(annee)) filtres.set("year", annee);
  const extra = filtres.toString();

  const types = useQuery({ queryKey: ["ged-types"], queryFn: () => api.listAll<DocType>("/api/documents/types/"), retry: 0 }).data ?? [];
  const facets = useQuery({
    queryKey: ["ged-facets", extra],
    queryFn: () => api.get<Facets>(`/api/documents/documents/facets/${extra ? `?${extra}` : ""}`),
    retry: 0,
  }).data;
  const list = usePagedList<DocRow>("ged-documents", (q) => api.get<Paginated<DocRow>>(`/api/documents/documents/${q}`), {
    pageSize: 20,
    extra,
  });

  const verifier = async (d: DocRow) => {
    try {
      const r = await api.get<Verification>(`/api/documents/documents/${d.id}/verify/`);
      setVerif((v) => ({ ...v, [d.id]: r }));
    } catch (e) {
      setVerif((v) => ({ ...v, [d.id]: describeError(e) }));
    }
  };

  const columns: Column<DocRow>[] = [
    {
      key: "titre",
      header: t("ecarts_tr.ged.titre"),
      render: (d) => (
        <>
          <strong>{d.title}</strong>
          <div className="muted" style={{ fontSize: 12 }}>
            {[d.reference, d.counterparty, d.project, d.dossier_path].filter(Boolean).join(" · ")}
          </div>
        </>
      ),
    },
    { key: "type", header: t("ecarts_tr.ged.type"), render: (d) => d.type_label ?? "—" },
    { key: "statut", header: t("ecarts_tr.ged.statut"), render: (d) => <Badge tone={TON[d.status] ?? "neutral"}>{t(`ecarts_tr.ged.statuts.${d.status}`)}</Badge> },
    { key: "date", header: t("ecarts_tr.ged.date"), render: (d) => formatDate(d.document_date ?? d.created_at) },
    {
      key: "sha",
      header: "SHA-256",
      render: (d) => {
        const v = verif[d.id];
        return (
          <>
            <code style={{ fontSize: 11 }}>{d.sha256 ? `${d.sha256.slice(0, 12)}…` : "—"}</code>
            {v ? (
              typeof v === "string" ? (
                <div className="action-error">{v}</div>
              ) : (
                <div>
                  <Badge tone={v.ok ? "ok" : "err"}>{v.ok ? t("ecarts_tr.ged.integre") : t("ecarts_tr.ged.altere")}</Badge>
                </div>
              )
            ) : null}
          </>
        );
      },
    },
    {
      key: "actions",
      header: "",
      render: (d) => (
        <div className="action-bar-buttons">
          <button type="button" className="btn ghost" onClick={() => void api.download(`/api/documents/documents/${d.id}/download/`, d.title)}>
            <Download size={14} aria-hidden="true" /> {t("ecarts_tr.ged.telecharger")}
          </button>
          <button type="button" className="btn ghost" onClick={() => void verifier(d)}>
            <ShieldCheck size={14} aria-hidden="true" /> {t("ecarts_tr.ged.verifier")}
          </button>
          {d.status === "draft" || d.status === "rejected" ? (
            <ActionBar actions={[{ label: t("ecarts_tr.ged.soumettre"), path: "/api/workflow/tasks/submit/", body: { document: d.id }, tone: "primary" }]} />
          ) : null}
        </div>
      ),
    },
  ];

  return (
    <>
      <PageHeader title={t("ecarts_tr.ged.title")} subtitle={t("ecarts_tr.ged.subtitle")} />
      <div className="kpi-grid">
        <Kpi label={t("ecarts_tr.ged.total")} value={facets?.total ?? 0} icon={FileText} tone="brand" />
        <Kpi label={t("ecarts_tr.ged.statuts.in_validation")} value={facets?.by_status?.in_validation ?? 0} icon={FileText} tone="warn" delay={0.05} />
        <Kpi label={t("ecarts_tr.ged.statuts.archived")} value={facets?.by_status?.archived ?? 0} icon={Archive} tone="accent" delay={0.1} />
      </div>
      <SectionCard
        title={t("ecarts_tr.ged.documents")}
        actions={
          <div className="action-bar-buttons">
            <AjoutDocument types={types} />
            <button type="button" className="btn ghost" onClick={() => void api.download(`/api/reports/export/?export=xlsx${extra ? `&${extra}` : ""}`, "documents.xlsx")}>
              <Download size={14} aria-hidden="true" /> Excel
            </button>
          </div>
        }
      >
        <div className="quick-form-grid">
          <div className="field">
            <label htmlFor="ged-f-statut">{t("ecarts_tr.ged.statut")}</label>
            <select id="ged-f-statut" value={statut} onChange={(e) => setStatut(e.target.value)}>
              <option value="">{t("ecarts_tr.parametres.tous")}</option>
              {STATUTS.map((s) => (
                <option key={s} value={s}>
                  {t(`ecarts_tr.ged.statuts.${s}`)}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="ged-f-type">{t("ecarts_tr.ged.type")}</label>
            <select id="ged-f-type" value={type} onChange={(e) => setType(e.target.value)}>
              <option value="">{t("ecarts_tr.parametres.tous")}</option>
              {types.map((ty) => (
                <option key={ty.id} value={ty.id}>
                  {ty.label}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="ged-f-annee">{t("ecarts_tr.ged.annee")}</label>
            <input id="ged-f-annee" inputMode="numeric" maxLength={4} value={annee} onChange={(e) => setAnnee(e.target.value)} />
          </div>
        </div>
        <PagedDataTable list={list} columns={columns} caption={t("ecarts_tr.ged.documents")} searchPlaceholder={t("ecarts_tr.ged.rechercher")} />
      </SectionCard>
      <SectionCard title={t("ecarts_tr.ged.types")} subtitle={t("ecarts_tr.ged.typesAide")}>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">{t("ecarts_tr.ged.type")}</th>
                <th scope="col">{t("ecarts_tr.ged.retention")}</th>
                <th scope="col">{t("ecarts_tr.parametres.statut")}</th>
              </tr>
            </thead>
            <tbody>
              {types.map((ty) => (
                <tr key={ty.id}>
                  <td>
                    {ty.label} <span className="muted">({ty.code})</span>
                  </td>
                  <td>{ty.retention_years ? `${ty.retention_years} ${t("ecarts_tr.ged.ans")}` : "—"}</td>
                  <td>
                    {ty.retention_provisoire ? (
                      <Badge tone="warn">{t("ecarts_tr.parametres.provisoire")}</Badge>
                    ) : (
                      <Badge tone="ok">{t("ecarts_tr.parametres.confirme")}</Badge>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Link className="btn ghost" to="/parametres">
          {t("ecarts_tr.ged.modifierRetention")}
        </Link>
      </SectionCard>
    </>
  );
}
