import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, CircleDashed, Download, ExternalLink, FileSpreadsheet, ListChecks, Pencil, SlidersHorizontal } from "lucide-react";
import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { api } from "../api/client";
import {
  Badge,
  DataGrid,
  EmptyState,
  ErrorState,
  Kpi,
  KpiGridSkeleton,
  notify,
  PageHeader,
  ProgressBar,
  SearchField,
  SectionCard,
  Sheet,
} from "../components/ui";
import type { GridColumn } from "../components/ui";
import { formatDateTime, formatNumber } from "../lib/format";
import { describeError } from "../lib/offlineQueue";
import { corpsEdition, parModule, SaisieInvalide, type ParametreEtsl } from "../lib/parametres";

/** Valeur lisible : nombres au format français (« 5 » plutôt que « 5.00 »), texte tel quel. */
function valeurLisible(p: ParametreEtsl): string {
  if (!p.valeur) return "—";
  if ((p.type_valeur === "decimal" || p.type_valeur === "entier") && !Number.isNaN(Number(p.valeur))) {
    const n = Number(p.valeur);
    return formatNumber(n, { decimals: Number.isInteger(n) ? 0 : 2 });
  }
  return p.valeur;
}

/** Édition d'un paramètre dans un panneau latéral : appel à l'endpoint EXISTANT de l'application (droits du module). */
function EditionParametre({ p, onClose }: { p: ParametreEtsl | null; onClose: () => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const uid = useId();
  const [saisie, setSaisie] = useState("");
  const [erreur, setErreur] = useState<string | null>(null);
  const [courant, setCourant] = useState<string | null>(null);
  // Nouveau paramètre ouvert : la saisie repart de sa valeur actuelle.
  if (p && courant !== p.id + p.modele) {
    setCourant(p.id + p.modele);
    setSaisie(p.valeur);
    setErreur(null);
  }
  const enregistrer = useMutation({
    mutationFn: (param: ParametreEtsl) => {
      const corps = corpsEdition(param, saisie);
      return param.edition.method === "PATCH" ? api.patch<unknown>(param.edition.path, corps) : api.post<unknown>(param.edition.path, corps);
    },
    onSuccess: (_d, param) => {
      notify.success(t("formulaires.parametres.enregistre"), { description: param.label });
      void qc.invalidateQueries();
      onClose();
    },
    onError: (e) => setErreur(e instanceof SaisieInvalide ? t("ecarts_tr.parametres.saisieInvalide", { type: e.message }) : describeError(e)),
  });
  const formId = `${uid}-form`;
  return (
    <Sheet
      open={p !== null}
      onOpenChange={(o) => {
        if (!o) {
          setCourant(null);
          onClose();
        }
      }}
      title={p?.label ?? ""}
      description={p ? `${p.module_label}${p.groupe ? ` · ${p.groupe}` : ""}` : undefined}
      width={480}
      preventOutsideClose={enregistrer.isPending}
      footer={
        <>
          <button type="button" className="btn ghost" onClick={onClose}>
            {t("actionBar.annuler")}
          </button>
          <button type="submit" form={formId} className="btn primary" disabled={enregistrer.isPending}>
            {enregistrer.isPending ? t("common.loading") : t("ecarts_tr.parametres.enregistrer")}
          </button>
        </>
      }
    >
      {p ? (
        <form
          id={formId}
          className="param-edit"
          onSubmit={(e) => {
            e.preventDefault();
            setErreur(null);
            enregistrer.mutate(p);
          }}
        >
          <dl className="param-edit-meta">
            <div>
              <dt>{t("formulaires.parametres.code")}</dt>
              <dd>
                <code>{p.code}</code>
              </dd>
            </div>
            <div>
              <dt>{t("formulaires.parametres.actuelle")}</dt>
              <dd className="num">
                {valeurLisible(p)} {p.unite ? <span className="muted">{p.unite}</span> : null}
              </dd>
            </div>
            <div>
              <dt>{t("ecarts_tr.parametres.statut")}</dt>
              <dd>
                {p.provisoire ? (
                  <Badge tone="warn">{t("formulaires.parametres.provisoire")}</Badge>
                ) : (
                  <Badge tone="ok">{t("ecarts_tr.parametres.confirme")}</Badge>
                )}
              </dd>
            </div>
          </dl>
          <div className="field">
            <label htmlFor={`${uid}-v`}>
              {t("formulaires.parametres.nouvelle")}
              {p.unite ? ` (${p.unite})` : ""}
            </label>
            {p.type_valeur === "json" ? (
              <textarea id={`${uid}-v`} rows={8} className="param-json" value={saisie} onChange={(e) => setSaisie(e.target.value)} />
            ) : (
              <input
                id={`${uid}-v`}
                value={saisie}
                inputMode={p.type_valeur === "texte" ? "text" : "decimal"}
                onChange={(e) => setSaisie(e.target.value)}
                autoFocus
              />
            )}
            <span className="hint">{t(`formulaires.parametres.aide.${p.type_valeur}`)}</span>
          </div>
          <p className="param-edit-note">{t("formulaires.parametres.noteProvisoire")}</p>
          {erreur ? (
            <p className="action-error" role="alert">
              {erreur}
            </p>
          ) : null}
        </form>
      ) : null}
    </Sheet>
  );
}

/** « Paramètres ETSL » : tous les paramètres provisoires des modules, modifiables et confirmables au même endroit. */
export function ParametresPage() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [module, setModule] = useState("");
  const [aConfirmer, setAConfirmer] = useState(false);
  const [recherche, setRecherche] = useState("");
  const [edite, setEdite] = useState<ParametreEtsl | null>(null);
  const qs = new URLSearchParams();
  if (module) qs.set("module", module);
  if (aConfirmer) qs.set("statut", "provisoire");
  if (recherche.trim()) qs.set("search", recherche.trim());
  const filtre = qs.toString();
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["parametres-etsl", filtre],
    queryFn: () => api.parametresEtsl(filtre ? `?${filtre}` : ""),
  });
  const exporter = (fmt: "xlsx" | "pdf") =>
    void api.download(`/api/parametres-etsl/?export=${fmt}${filtre ? `&${filtre}` : ""}`, `parametres_etsl.${fmt}`);

  const confirmer = useMutation({
    mutationFn: (p: ParametreEtsl) => api.post<unknown>(p.confirmation),
    onSuccess: (_d, p) => {
      notify.success(t("formulaires.parametres.confirmeOk"), { description: p.label });
      void qc.invalidateQueries();
    },
    onError: (e, p) => notify.error(t("formulaires.parametres.confirmeKo"), { description: `${p.label} — ${describeError(e)}` }),
  });

  // Le registre renvoie toujours la liste complète (pas de pagination) : total et provisoires pour la synthèse.
  const resultats = data?.results ?? [];
  const total = data?.count ?? resultats.length;
  const provisoires = data?.provisoires ?? resultats.filter((r) => r.provisoire).length;

  const columns: GridColumn<ParametreEtsl>[] = [
    {
      key: "parametre",
      header: t("ecarts_tr.parametres.parametre"),
      sortValue: (p) => p.label,
      render: (p) => (
        <div className="param-cell">
          <button type="button" className="param-link" onClick={() => setEdite(p)}>
            {p.label}
          </button>
          <span className="param-code">
            {p.code}
            {p.groupe ? ` · ${p.groupe}` : ""}
          </span>
        </div>
      ),
    },
    {
      key: "valeur",
      header: t("ecarts_tr.parametres.valeur"),
      width: "26%",
      render: (p) => (
        <span className={`param-value${p.type_valeur === "json" ? " is-json" : ""}`}>
          <span className="num">{valeurLisible(p)}</span>
          {p.unite ? <span className="muted"> {p.unite}</span> : null}
        </span>
      ),
    },
    {
      key: "statut",
      header: t("ecarts_tr.parametres.statut"),
      width: 200,
      sortValue: (p) => (p.provisoire ? 0 : 1),
      render: (p) =>
        p.provisoire ? (
          <Badge tone="warn">{t("formulaires.parametres.provisoire")}</Badge>
        ) : (
          <div className="param-status">
            <Badge tone="ok">{t("ecarts_tr.parametres.confirme")}</Badge>
            {p.confirme_par ? (
              <span className="param-who">
                {p.confirme_par}
                {p.confirme_le ? ` · ${formatDateTime(p.confirme_le)}` : ""}
              </span>
            ) : null}
          </div>
        ),
    },
    {
      key: "action",
      header: <span className="sr-only">{t("ecarts_tr.parametres.confirmer")}</span>,
      width: 120,
      render: (p) =>
        p.provisoire ? (
          <button
            type="button"
            className="btn sm param-confirm"
            disabled={confirmer.isPending && confirmer.variables?.id === p.id}
            onClick={() => confirmer.mutate(p)}
          >
            <BadgeCheck size={14} aria-hidden="true" /> {t("ecarts_tr.parametres.confirmer")}
          </button>
        ) : null,
    },
  ];

  return (
    <>
      <PageHeader
        title={t("ecarts_tr.parametres.title")}
        subtitle={t("ecarts_tr.parametres.subtitle")}
        actions={
          <>
            <button type="button" className="btn ghost" onClick={() => exporter("xlsx")}>
              <FileSpreadsheet size={15} aria-hidden="true" /> Excel
            </button>
            <button type="button" className="btn ghost" onClick={() => exporter("pdf")}>
              <Download size={15} aria-hidden="true" /> PDF
            </button>
          </>
        }
      />

      {isLoading ? (
        <KpiGridSkeleton count={3} />
      ) : data ? (
        <div className="kpi-grid">
          <Kpi label={t("formulaires.parametres.total")} value={total} icon={SlidersHorizontal} tone="brand" />
          <Kpi label={t("formulaires.parametres.aConfirmer")} value={provisoires} icon={CircleDashed} tone="warn" delay={0.05} />
          <Kpi label={t("formulaires.parametres.confirmes")} value={Math.max(total - provisoires, 0)} icon={ListChecks} tone="ok" delay={0.1} />
        </div>
      ) : null}

      {data && provisoires > 0 ? (
        <div className="banner warn param-banner" role="note" data-testid="alerte-provisoire-parametres">
          <CircleDashed size={18} aria-hidden="true" />
          <div className="banner-body">
            <p className="banner-title">{t("ecarts_tr.parametres.bandeau", { count: provisoires })}</p>
            <p className="banner-text">{t("formulaires.parametres.bandeauAide")}</p>
          </div>
          {!aConfirmer ? (
            <button type="button" className="btn sm banner-action" onClick={() => setAConfirmer(true)}>
              {t("formulaires.parametres.voirAConfirmer")}
            </button>
          ) : null}
        </div>
      ) : null}

      <div className="param-toolbar" role="group" aria-label={t("ecarts_tr.parametres.filtres")}>
        <SearchField value={recherche} onChange={setRecherche} placeholder={t("ecarts_tr.parametres.rechercher")} />
        <label className="sr-only" htmlFor="param-module">
          {t("ecarts_tr.parametres.module")}
        </label>
        <select id="param-module" className="filter-control" value={module} onChange={(e) => setModule(e.target.value)}>
          <option value="">{t("formulaires.parametres.tousModules")}</option>
          {(data?.modules ?? []).map((m) => (
            <option key={m.module} value={m.module}>
              {m.label}
            </option>
          ))}
        </select>
        <div className="segmented" role="radiogroup" aria-label={t("ecarts_tr.parametres.statut")}>
          <button type="button" role="radio" aria-checked={!aConfirmer} className={!aConfirmer ? "is-on" : ""} onClick={() => setAConfirmer(false)}>
            {t("ecarts_tr.parametres.tous")}
          </button>
          <button type="button" role="radio" aria-checked={aConfirmer} className={aConfirmer ? "is-on" : ""} onClick={() => setAConfirmer(true)}>
            {t("formulaires.parametres.aConfirmer")}
          </button>
        </div>
      </div>

      {isLoading ? null : isError || !data ? (
        <ErrorState
          message={`${t("formulaires.parametres.erreur")}${error ? ` — ${describeError(error)}` : ""}`}
          onRetry={() => void refetch()}
          retryLabel={t("common.retry")}
        />
      ) : resultats.length === 0 ? (
        <EmptyState icon={SlidersHorizontal} label={t("formulaires.parametres.aucun")} />
      ) : (
        parModule(resultats).map((g) => {
          const nbProv = g.rows.filter((r) => r.provisoire).length;
          const ecran = g.rows[0]?.ecran;
          return (
            <SectionCard
              key={g.module}
              className="param-group"
              title={g.label}
              subtitle={t("formulaires.parametres.compte", { count: g.rows.length, provisoires: nbProv })}
              actions={
                <div className="param-group-side">
                  <ProgressBar
                    value={g.rows.length - nbProv}
                    max={g.rows.length}
                    tone={nbProv ? "warn" : "ok"}
                    label={t("formulaires.parametres.avancement", { label: g.label })}
                    className="param-progress"
                  />
                  {ecran ? (
                    <button type="button" className="btn ghost sm" onClick={() => navigate(ecran)}>
                      <ExternalLink size={14} aria-hidden="true" /> {t("formulaires.parametres.ouvrirModule")}
                    </button>
                  ) : null}
                </div>
              }
            >
              <DataGrid
                rows={g.rows.map((r) => ({ ...r, id: `${r.modele}-${r.id}` }))}
                columns={columns}
                caption={g.label}
                density="compact"
                maxHeight="none"
                rowActions={(p) => [
                  { label: t("ecarts_tr.parametres.modifier"), icon: Pencil, onSelect: () => setEdite(p) },
                  p.provisoire && { label: t("ecarts_tr.parametres.confirmer"), icon: BadgeCheck, onSelect: () => confirmer.mutate(p) },
                  "separator",
                  { label: t("ecarts_tr.parametres.ecran"), icon: ExternalLink, onSelect: () => navigate(p.ecran) },
                ]}
              />
            </SectionCard>
          );
        })
      )}
      <EditionParametre p={edite} onClose={() => setEdite(null)} />
    </>
  );
}
