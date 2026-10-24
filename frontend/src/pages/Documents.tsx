import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, Download, FileText, Send, ShieldCheck, Upload } from "lucide-react";
import { useId, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import { ParamsPanel } from "../components/parametres/ParamsPanel";
import { cleanLabel } from "../components/workflow/libelle";
import {
  Badge,
  DataGrid,
  DatePicker,
  FilterBar,
  filtersToQuery,
  Kpi,
  notify,
  PagedDataGrid,
  PageHeader,
  SearchField,
  SectionCard,
  Sheet,
} from "../components/ui";
import type { BadgeTone, FilterDef, FilterValues, GridColumn } from "../components/ui";
import { formatDate, formatPercent } from "../lib/format";
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
  pdfa_statut?: string;
  pdfa_norme?: string;
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

const TON: Record<string, BadgeTone> = { draft: "neutral", in_validation: "warn", rejected: "err", archived: "ok" };

/**
 * Titre de liste sans redite (A-15) : retire la référence en tête (« PV00007 — … », déjà en méta)
 * et le suffixe technique « — archivage (receptionne) ». Le titre complet reste en infobulle.
 */
function titreLisible(titre: string, reference?: string | null): string {
  let s = titre.replace(/\s+[—-]\s+archivage\s*\([^)]*\)\s*$/i, "");
  if (reference && s.startsWith(reference)) {
    const reste = s.slice(reference.length).replace(/^\s*[—:·-]\s*/, "");
    if (reste) s = reste;
  }
  return s;
}

/** Ajout d'un document (fichier + métadonnées) dans un panneau latéral : POST multipart sur l'API GED existante. */
function AjoutDocument({ types }: { types: DocType[] }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const uid = useId();
  const [ouvert, setOuvert] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);
  const titre = t("ecarts_tr.ged.ajouter");
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
      const nom = String(new FormData(form).get("title") ?? "");
      form.reset();
      setOuvert(false);
      notify.success(t("formulaires.ged.ajoute"), { description: nom || undefined });
      void qc.invalidateQueries();
    },
    onError: (e) => {
      const text = e instanceof Error && !("status" in e) ? e.message : describeError(e);
      setErreur(text);
      notify.error(t("formulaires.quickForm.toastErr"), { description: text });
    },
  });
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setErreur(null);
    envoi.mutate(e.currentTarget);
  };
  const id = (n: string) => `${uid}-${n}`;
  return (
    <Sheet
      open={ouvert}
      onOpenChange={(o) => {
        setOuvert(o);
        if (o) setErreur(null);
      }}
      title={titre}
      description={t("formulaires.ged.ajoutAide")}
      width={480}
      preventOutsideClose={envoi.isPending}
      className="quick-form-sheet"
      trigger={
        <button type="button" className="btn primary">
          <Upload size={16} aria-hidden="true" /> {titre}
        </button>
      }
    >
      <form className="quick-form" onSubmit={submit} aria-label={titre}>
        <div className="quick-form-fields">
          <div className="field wide">
            <label htmlFor={id("file")}>{t("ecarts_tr.ged.fichier")} *</label>
            <input id={id("file")} name="file" type="file" required className="ged-file" />
          </div>
          <div className="field wide">
            <label htmlFor={id("title")}>{t("ecarts_tr.ged.titre")} *</label>
            <input id={id("title")} name="title" required />
          </div>
          <div className="field">
            <label htmlFor={id("type")}>{t("ecarts_tr.ged.type")}</label>
            <select id={id("type")} name="type">
              <option value="">—</option>
              {types.map((ty) => (
                <option key={ty.id} value={ty.id}>
                  {ty.label}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor={id("date")}>{t("ecarts_tr.ged.date")}</label>
            <DatePicker id={id("date")} name="document_date" />
          </div>
          <div className="field">
            <label htmlFor={id("ref")}>{t("ecarts_tr.ged.reference")}</label>
            <input id={id("ref")} name="reference" />
          </div>
          <div className="field">
            <label htmlFor={id("tiers")}>{t("ecarts_tr.ged.tiers")}</label>
            <input id={id("tiers")} name="counterparty" />
          </div>
          <div className="field wide">
            <label htmlFor={id("projet")}>{t("ecarts_tr.ged.projet")}</label>
            <input id={id("projet")} name="project" />
          </div>
        </div>
        <div className="quick-form-foot">
          <div className="quick-form-feedback">
            {erreur ? (
              <p className="action-error" role="alert">
                {erreur}
              </p>
            ) : (
              <p className="quick-form-hint">{t("formulaires.quickForm.requis")}</p>
            )}
          </div>
          <button type="button" className="btn ghost" onClick={() => setOuvert(false)}>
            {t("actionBar.annuler")}
          </button>
          <button type="submit" className="btn primary" disabled={envoi.isPending}>
            {envoi.isPending ? t("common.loading") : t("quickForm.save")}
          </button>
        </div>
      </form>
    </Sheet>
  );
}

/** GED autonome (flux M12 → tous) : recherche plein texte, filtres, ajout, téléchargement, intégrité, circuit. */
export function DocumentsPage() {
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const [criteres, setCriteres] = useState<FilterValues>({});
  const [verif, setVerif] = useState<Record<string, Verification | string>>({});
  // EX-G-09 : critères multicritères décrits par l'API (libellés traduits côté serveur) + année (4 chiffres).
  const filtres = new URLSearchParams(filtersToQuery(criteres));
  if (!/^\d{4}$/.test(filtres.get("year") ?? "")) filtres.delete("year");
  const extra = filtres.toString();

  const types = useQuery({ queryKey: ["ged-types"], queryFn: () => api.listAll<DocType>("/api/documents/types/"), retry: 0 }).data ?? [];
  const defs =
    useQuery({
      queryKey: ["ged-filtres", i18n.language],
      queryFn: () => api.get<{ results: FilterDef[] }>("/api/documents/documents/filtres/"),
      retry: 0,
    }).data?.results ?? [];
  const facets = useQuery({
    queryKey: ["ged-facets", extra],
    queryFn: () => api.get<Facets>(`/api/documents/documents/facets/${extra ? `?${extra}` : ""}`),
    retry: 0,
  }).data;
  const list = usePagedList<DocRow>("ged-documents", (q) => api.get<Paginated<DocRow>>(`/api/documents/documents/${q}`), {
    pageSize: 20,
    extra,
  });

  // Validations en retard (indice du KPI « En validation », A-18).
  const taches = useQuery({ queryKey: ["tasks"], queryFn: api.tasks, staleTime: 60_000, retry: 0 });
  const enRetard = (taches.data ?? []).filter(
    (tk) => (tk.status === "pending" || tk.status === "delegated") && new Date(tk.due_date) < new Date(),
  ).length;

  const verifier = async (d: DocRow) => {
    try {
      const r = await api.get<Verification>(`/api/documents/documents/${d.id}/verify/`);
      setVerif((v) => ({ ...v, [d.id]: r }));
      if (r.ok) notify.success(t("ecarts_tr.ged.integre"), { description: d.title });
      else notify.error(t("ecarts_tr.ged.altere"), { description: d.title });
    } catch (e) {
      setVerif((v) => ({ ...v, [d.id]: describeError(e) }));
      notify.error(t("formulaires.quickForm.toastErr"), { description: describeError(e) });
    }
  };
  const soumettre = async (d: DocRow) => {
    try {
      await api.post<unknown>("/api/workflow/tasks/submit/", { document: d.id });
      notify.success(t("formulaires.ged.soumis"), { description: d.title });
      void qc.invalidateQueries();
    } catch (e) {
      notify.error(t("formulaires.quickForm.toastErr"), { description: describeError(e) });
    }
  };

  const columns: GridColumn<DocRow>[] = [
    {
      key: "titre",
      header: t("ecarts_tr.ged.titre"),
      sortValue: (d) => d.title,
      render: (d) => {
        const meta = [d.reference, d.counterparty, d.project, d.dossier_path].filter(Boolean).join(" · ");
        const titre = titreLisible(d.title, d.reference);
        return (
          <div className="ged-title">
            <span className="ged-title-main">
              <strong className="ged-title-text" title={d.title}>
                {titre}
              </strong>
              {d.pdfa_statut === "converti" ? <Badge tone="ok">PDF/A-{d.pdfa_norme}</Badge> : null}
            </span>
            {meta ? <span className="ged-title-meta">{meta}</span> : null}
          </div>
        );
      },
    },
    { key: "type", header: t("ecarts_tr.ged.type"), sortValue: (d) => d.type_label, render: (d) => (d.type_label ? cleanLabel(d.type_label) : "—") },
    {
      key: "statut",
      header: t("ecarts_tr.ged.statut"),
      sortValue: (d) => d.status,
      render: (d) => <Badge tone={TON[d.status] ?? "neutral"}>{t(`ecarts_tr.ged.statuts.${d.status}`)}</Badge>,
    },
    {
      key: "date",
      header: t("ecarts_tr.ged.date"),
      sortValue: (d) => d.document_date ?? d.created_at,
      render: (d) => <span className="num">{formatDate(d.document_date ?? d.created_at)}</span>,
    },
    {
      key: "sha",
      header: t("formulaires.ged.integrite"),
      render: (d) => {
        const v = verif[d.id];
        if (v && typeof v !== "string")
          return <Badge tone={v.ok ? "ok" : "err"}>{v.ok ? t("ecarts_tr.ged.integre") : t("ecarts_tr.ged.altere")}</Badge>;
        // Empreinte scellée : badge lisible, le SHA-256 complet reste en infobulle (A-16).
        return d.sha256 ? (
          <Badge tone="ok" icon={ShieldCheck} title={t("premiumPilotage.ged.empreinte", { sha: d.sha256 })}>
            {t("premiumPilotage.ged.integre")}
          </Badge>
        ) : (
          <span className="muted">—</span>
        );
      },
    },
  ];

  const typeColumns: GridColumn<DocType>[] = [
    { key: "type", header: t("ecarts_tr.ged.type"), sortValue: (ty) => ty.label, render: (ty) => <strong>{cleanLabel(ty.label)}</strong> },
    {
      key: "retention",
      header: t("ecarts_tr.ged.retention"),
      num: true,
      sortValue: (ty) => ty.retention_years,
      render: (ty) => (ty.retention_years ? t("revueR1.ans", { count: ty.retention_years }) : "—"),
    },
    {
      key: "statut",
      header: t("ecarts_tr.parametres.statut"),
      render: (ty) =>
        ty.retention_provisoire ? (
          <Badge tone="warn">{t("formulaires.parametres.provisoire")}</Badge>
        ) : (
          <Badge tone="ok">{t("ecarts_tr.parametres.confirme")}</Badge>
        ),
    },
  ];

  const exporter = () => void api.download(`/api/reports/export/?export=xlsx${extra ? `&${extra}` : ""}`, "documents.xlsx");
  const soumettable = (d: DocRow) => d.status === "draft" || d.status === "rejected";

  return (
    <>
      <PageHeader
        title={t("ecarts_tr.ged.title")}
        subtitle={t("ecarts_tr.ged.subtitle")}
        actions={
          <>
            <button type="button" className="btn ghost" onClick={exporter}>
              <Download size={15} aria-hidden="true" /> Excel
            </button>
            <AjoutDocument types={types} />
          </>
        }
      />
      <div className="kpi-grid">
        <Kpi
          label={t("ecarts_tr.ged.total")}
          value={facets?.total ?? 0}
          hint={t("premiumPilotage.ged.brouillons", { count: facets?.by_status?.draft ?? 0 })}
          icon={FileText}
          tone="brand"
        />
        <Kpi
          label={t("ecarts_tr.ged.statuts.in_validation")}
          value={facets?.by_status?.in_validation ?? 0}
          hint={enRetard ? t("premiumPilotage.ged.enRetard", { count: enRetard }) : t("premiumPilotage.ged.aucunRetard")}
          icon={FileText}
          tone="warn"
          delay={0.05}
        />
        <Kpi
          label={t("revueR1.ged.archives")}
          value={facets?.by_status?.archived ?? 0}
          hint={
            facets?.total
              ? t("premiumPilotage.ged.partFonds", { pct: formatPercent(((facets.by_status?.archived ?? 0) / facets.total) * 100) })
              : undefined
          }
          icon={Archive}
          tone="accent"
          delay={0.1}
        />
      </div>
      <SectionCard title={t("ecarts_tr.ged.documents")} className="ged-card">
        <FilterBar
          defs={defs}
          value={criteres}
          onChange={setCriteres}
          idPrefix="ged-f"
          primary={["status", "type", "document_date"]}
          options={{ type: types.map((ty) => ({ valeur: String(ty.id), libelle: cleanLabel(ty.label) })) }}
          search={<SearchField value={list.search} onChange={list.setSearch} placeholder={t("ecarts_tr.ged.rechercher")} />}
          moreKeys={["year"]}
          more={
            <div className="field">
              <label htmlFor="ged-f-annee">{t("ecarts_tr.ged.annee")}</label>
              <input
                id="ged-f-annee"
                inputMode="numeric"
                maxLength={4}
                placeholder="2026"
                value={criteres.year ?? ""}
                onChange={(e) => setCriteres({ ...criteres, year: e.target.value.replace(/\D/g, "") })}
              />
            </div>
          }
        />
        <PagedDataGrid
          list={list}
          columns={columns}
          caption={t("ecarts_tr.ged.documents")}
          emptyLabel={t("common.empty")}
          rowActions={(d) => [
            { label: t("ecarts_tr.ged.telecharger"), icon: Download, onSelect: () => void api.download(`/api/documents/documents/${d.id}/download/`, d.title) },
            { label: t("ecarts_tr.ged.verifier"), icon: ShieldCheck, onSelect: () => void verifier(d) },
            soumettable(d) && "separator",
            soumettable(d) && { label: t("ecarts_tr.ged.soumettre"), icon: Send, onSelect: () => void soumettre(d) },
          ]}
        />
      </SectionCard>
      {/* Durées de conservation : doublon de « Paramètres ETSL › GED » replié en un panneau compact (A-17, chantier « params »). */}
      <ParamsPanel
        variant="card"
        module="documents"
        title={t("ecarts_tr.ged.types")}
        count={types.filter((ty) => ty.retention_provisoire).length}
        total={types.length}
        testId="ged-durees-conservation"
      >
        <p className="muted">{t("ecarts_tr.ged.typesAide")}</p>
        <DataGrid rows={types} columns={typeColumns} caption={t("ecarts_tr.ged.types")} density="compact" maxHeight="none" emptyLabel={t("common.empty")} />
      </ParamsPanel>
    </>
  );
}
