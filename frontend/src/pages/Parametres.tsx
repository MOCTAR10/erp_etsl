import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, ChevronDown, CircleDashed, Download, ExternalLink, FileSpreadsheet, ListChecks, Pencil, SlidersHorizontal, X } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router-dom";

import { api } from "../api/client";
import { ParamStatusBadge } from "../components/parametres/ParamsPanel";
import { libelleParametre, ParamValue, valeurScalaire } from "../components/parametres/ParamValue";
import {
  DataGrid,
  EmptyState,
  ErrorState,
  Kpi,
  KpiGridSkeleton,
  notify,
  PageHeader,
  SearchField,
  Sheet,
} from "../components/ui";
import type { GridColumn } from "../components/ui";
import { formatDateTime } from "../lib/format";
import { describeError } from "../lib/offlineQueue";
import { corpsEdition, parModule, SaisieInvalide, type ParametreEtsl } from "../lib/parametres";

/** Nom de module sans code de lot (« M1 Commercial » → « Commercial »). */
const moduleLisible = (label: string) => label.replace(/^M\d{1,2}\s*[—–-]?\s*/u, "");
/** Identifiant unique d'une ligne : deux modèles peuvent servir le même `id` (idempotent : la grille reçoit déjà cette clé). */
const cle = (p: ParametreEtsl) => (String(p.id).startsWith(`${p.modele}-`) ? String(p.id) : `${p.modele}-${p.id}`);
/** Jamais d'e-mail affiché comme nom (A-03) : « finance@etls.local » → « Finance ». */
function nomLisible(qui: string): string {
  if (!qui.includes("@")) return qui;
  return qui
    .split("@")[0]
    .split(/[._-]+/)
    .filter(Boolean)
    .map((m) => m.charAt(0).toUpperCase() + m.slice(1))
    .join(" ");
}
/** Ancre DOM d'une section de module. */
const ancre = (module: string) => `param-mod-${module}`;

/** Édition d'un paramètre dans un panneau latéral : appel à l'endpoint EXISTANT de l'application (droits du module). */
function EditionParametre({ p, onClose }: { p: ParametreEtsl | null; onClose: () => void }) {
  const { t, i18n } = useTranslation();
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
      notify.success(t("formulaires.parametres.enregistre"), { description: libelleParametre(t, param) });
      void qc.invalidateQueries();
      onClose();
    },
    onError: (e) => setErreur(e instanceof SaisieInvalide ? t("ecarts_tr.parametres.saisieInvalide", { type: e.message }) : describeError(e)),
  });
  const formId = `${uid}-form`;
  const groupe = p?.groupe ? t(`premiumParams.groupes.${p.groupe}`, { defaultValue: "" }) : "";
  return (
    <Sheet
      open={p !== null}
      onOpenChange={(o) => {
        if (!o) {
          setCourant(null);
          onClose();
        }
      }}
      title={p ? libelleParametre(t, p) : ""}
      description={p ? `${moduleLisible(p.module_label)}${groupe ? ` · ${groupe}` : ""}` : undefined}
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
          {libelleParametre(t, p) !== p.label ? <p className="param-edit-note">{p.label}</p> : null}
          <dl className="param-edit-meta">
            <div>
              <dt>{t("formulaires.parametres.code")}</dt>
              <dd>
                <code>{p.code}</code>
              </dd>
            </div>
            <div>
              <dt>{t("formulaires.parametres.actuelle")}</dt>
              <dd>{p.type_valeur === "json" ? <ParamValue p={p} /> : valeurScalaire(t, (k) => i18n.exists(k), p)}</dd>
            </div>
            <div>
              <dt>{t("ecarts_tr.parametres.statut")}</dt>
              <dd>
                <ParamStatusBadge provisoire={p.provisoire} />
              </dd>
            </div>
          </dl>
          <div className="field">
            <label htmlFor={`${uid}-v`}>
              {t("formulaires.parametres.nouvelle")}
              {p.unite && !["texte", "json"].includes(p.unite) ? ` (${p.unite})` : ""}
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

/**
 * « Paramètres ETSL » : tous les paramètres provisoires des modules, modifiables et confirmables au même endroit.
 * Sections par module repliables + sommaire collant (A-10), `?module=<app>` ouvre et fait défiler jusqu'au module,
 * action « Confirmer » révélée au survol / focus (toujours visible au toucher) et « Confirmer la sélection ».
 */
export function ParametresPage() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const cible = params.get("module") ?? "";
  const [aConfirmer, setAConfirmer] = useState(false);
  const [recherche, setRecherche] = useState("");
  const [edite, setEdite] = useState<ParametreEtsl | null>(null);
  /** Sections ouvertes ; null = état initial (module demandé par l'URL, sinon la première section). */
  const [ouverts, setOuverts] = useState<Set<string> | null>(null);
  const [selection, setSelection] = useState<Set<string>>(new Set());
  const defile = useRef<string | null>(null);

  const qs = new URLSearchParams();
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
      notify.success(t("formulaires.parametres.confirmeOk"), { description: libelleParametre(t, p) });
      setSelection((s) => {
        const n = new Set(s);
        n.delete(cle(p));
        return n;
      });
      void qc.invalidateQueries();
    },
    onError: (e, p) => notify.error(t("formulaires.parametres.confirmeKo"), { description: `${libelleParametre(t, p)} — ${describeError(e)}` }),
  });

  const resultats = useMemo(() => data?.results ?? [], [data]);
  const groupes = useMemo(() => parModule(resultats), [resultats]);
  const parCle = useMemo(() => new Map(resultats.map((r) => [cle(r), r])), [resultats]);
  const selectionnes = [...selection].map((k) => parCle.get(k)).filter((p): p is ParametreEtsl => Boolean(p?.provisoire));

  /** Confirmation groupée : chaque paramètre passe par l'endpoint de SON module (droits inchangés). */
  const confirmerSelection = useMutation({
    mutationFn: async (lot: ParametreEtsl[]) => {
      const res = await Promise.allSettled(lot.map((p) => api.post<unknown>(p.confirmation)));
      return { ok: res.filter((r) => r.status === "fulfilled").length, ko: res.filter((r) => r.status === "rejected").length };
    },
    onSuccess: ({ ok, ko }) => {
      if (ok) notify.success(t("premiumParams.page.lotOk", { count: ok }));
      if (ko) notify.error(t("premiumParams.page.lotKo", { count: ko }));
      setSelection(new Set());
      void qc.invalidateQueries();
    },
  });

  // Le registre renvoie toujours la liste complète (pas de pagination) : total et provisoires pour la synthèse.
  const total = data?.count ?? resultats.length;
  const provisoires = data?.provisoires ?? resultats.filter((r) => r.provisoire).length;

  const recherchant = recherche.trim() !== "";
  const estOuvert = (module: string) => {
    if (recherchant) return true; // résultats d'une recherche : tout est déplié
    if (ouverts) return ouverts.has(module);
    return cible ? module === cible : module === groupes[0]?.module;
  };
  const basculer = (module: string) =>
    setOuverts((prev) => {
      const base = prev ?? new Set(groupes.filter((g) => estOuvert(g.module)).map((g) => g.module));
      const n = new Set(base);
      if (n.has(module)) n.delete(module);
      else n.add(module);
      return n;
    });
  const allerA = (module: string) => {
    setOuverts((prev) => new Set([...(prev ?? groupes.filter((g) => estOuvert(g.module)).map((g) => g.module)), module]));
    defile.current = module;
  };

  // `?module=…` (lien « Gérer dans Paramètres ETSL » d'un écran métier) : la section s'ouvre et vient à l'écran.
  const cibleTraitee = useRef("");
  useEffect(() => {
    if (!cible || !data || cibleTraitee.current === cible) return;
    cibleTraitee.current = cible;
    defile.current = cible;
  }, [cible, data]);
  useEffect(() => {
    const m = defile.current;
    if (!m) return;
    const el = document.getElementById(ancre(m));
    if (!el) return;
    defile.current = null;
    const reduit = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    el.scrollIntoView({ behavior: reduit ? "auto" : "smooth", block: "start" });
    el.querySelector<HTMLButtonElement>(".param-group-toggle")?.focus({ preventScroll: true });
  });

  const basculerLigne = (p: ParametreEtsl) =>
    setSelection((s) => {
      const n = new Set(s);
      if (n.has(cle(p))) n.delete(cle(p));
      else n.add(cle(p));
      return n;
    });

  const colonnes = (rows: ParametreEtsl[], titre: string): GridColumn<ParametreEtsl>[] => {
    const aCocher = rows.filter((r) => r.provisoire);
    const tous = aCocher.length > 0 && aCocher.every((r) => selection.has(cle(r)));
    return [
      {
        key: "choix",
        width: 44,
        header: (
          <input
            type="checkbox"
            className="param-check"
            aria-label={t("premiumParams.page.toutSelectionner", { module: titre })}
            disabled={aCocher.length === 0}
            checked={tous}
            onChange={() =>
              setSelection((s) => {
                const n = new Set(s);
                for (const r of aCocher) {
                  if (tous) n.delete(cle(r));
                  else n.add(cle(r));
                }
                return n;
              })
            }
          />
        ),
        render: (p) =>
          p.provisoire ? (
            <input
              type="checkbox"
              className="param-check"
              aria-label={t("premiumParams.page.selectionner", { label: libelleParametre(t, p) })}
              checked={selection.has(cle(p))}
              onChange={() => basculerLigne(p)}
            />
          ) : null,
      },
      {
        key: "parametre",
        header: t("ecarts_tr.parametres.parametre"),
        sortValue: (p) => libelleParametre(t, p),
        render: (p) => (
          <div className="param-cell">
            <button type="button" className="param-link" title={p.label !== libelleParametre(t, p) ? p.label : undefined} onClick={() => setEdite(p)}>
              {libelleParametre(t, p)}
            </button>
          </div>
        ),
      },
      {
        key: "valeur",
        header: t("ecarts_tr.parametres.valeur"),
        width: "28%",
        render: (p) => (
          <span className={`param-value${p.type_valeur === "json" ? " is-json" : ""}`}>
            <ParamValue p={p} />
          </span>
        ),
      },
      {
        key: "statut",
        header: t("ecarts_tr.parametres.statut"),
        width: 150,
        sortValue: (p) => (p.provisoire ? 0 : 1),
        render: (p) =>
          p.provisoire ? (
            <ParamStatusBadge provisoire />
          ) : (
            <div className="param-status">
              <ParamStatusBadge provisoire={false} />
              {p.confirme_par ? (
                <span className="param-who">
                  {nomLisible(p.confirme_par)}
                  {p.confirme_le ? ` · ${formatDateTime(p.confirme_le)}` : ""}
                </span>
              ) : null}
            </div>
          ),
      },
      {
        key: "action",
        header: <span className="sr-only">{t("ecarts_tr.parametres.confirmer")}</span>,
        width: 124,
        render: (p) =>
          p.provisoire ? (
            <button
              type="button"
              className="btn ghost sm param-confirm"
              aria-label={`${t("ecarts_tr.parametres.confirmer")} — ${libelleParametre(t, p)}`}
              disabled={confirmer.isPending && confirmer.variables?.id === p.id}
              onClick={() => confirmer.mutate(p)}
            >
              <BadgeCheck size={14} aria-hidden="true" /> {t("ecarts_tr.parametres.confirmer")}
            </button>
          ) : null,
      },
    ];
  };

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

      <div className="param-toolbar" role="group" aria-label={t("ecarts_tr.parametres.filtres")}>
        <SearchField value={recherche} onChange={setRecherche} placeholder={t("ecarts_tr.parametres.rechercher")} />
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
        <div className="param-layout">
          <nav className="param-nav" aria-label={t("premiumParams.page.sommaire")}>
            <p className="param-nav-title">{t("premiumParams.page.sommaire")}</p>
            <ul>
              {groupes.map((g) => {
                const nb = g.rows.filter((r) => r.provisoire).length;
                return (
                  <li key={g.module}>
                    <a
                      href={`#${ancre(g.module)}`}
                      className={estOuvert(g.module) ? "is-open" : undefined}
                      onClick={(e) => {
                        e.preventDefault();
                        allerA(g.module);
                      }}
                    >
                      <span className="param-nav-label">{moduleLisible(g.label)}</span>
                      <span className={`param-nav-count${nb ? " is-pending" : ""}`} title={t("formulaires.parametres.compte", { count: g.rows.length, provisoires: nb })}>
                        {nb ? nb : <BadgeCheck size={13} aria-label={t("premiumParams.badge.confirme")} />}
                      </span>
                    </a>
                  </li>
                );
              })}
            </ul>
          </nav>

          <div className="param-sections">
            {groupes.map((g) => {
              const nbProv = g.rows.filter((r) => r.provisoire).length;
              const ecran = g.rows[0]?.ecran;
              const titre = moduleLisible(g.label);
              const ouvert = estOuvert(g.module);
              const corps = `${ancre(g.module)}-corps`;
              return (
                <section key={g.module} id={ancre(g.module)} className={`card param-group${ouvert ? " is-open" : ""}`} aria-labelledby={`${ancre(g.module)}-titre`}>
                  <div className="card-header param-group-header">
                    <h3 className="card-title param-group-title" id={`${ancre(g.module)}-titre`}>
                      <button type="button" className="param-group-toggle" aria-expanded={ouvert} aria-controls={corps} onClick={() => basculer(g.module)}>
                        <ChevronDown size={16} aria-hidden="true" className="param-group-chevron" />
                        <span>{titre}</span>
                      </button>
                    </h3>
                    <div className="param-group-side">
                      <span className="card-sub">{t("formulaires.parametres.compte", { count: g.rows.length, provisoires: nbProv })}</span>
                      {ecran && ecran !== "/parametres" ? (
                        <button type="button" className="btn ghost sm" onClick={() => navigate(ecran)}>
                          <ExternalLink size={14} aria-hidden="true" /> {t("formulaires.parametres.ouvrirModule")}
                        </button>
                      ) : null}
                    </div>
                  </div>
                  {ouvert ? (
                    <div className="card-body" id={corps}>
                      <DataGrid
                        rows={g.rows.map((r) => ({ ...r, id: cle(r) }))}
                        columns={colonnes(g.rows, titre)}
                        caption={titre}
                        density="compact"
                        maxHeight="none"
                        rowActions={(row) => {
                          const p = parCle.get(row.id) ?? row;
                          return [
                            { label: t("ecarts_tr.parametres.modifier"), icon: Pencil, onSelect: () => setEdite(p) },
                            p.provisoire && { label: t("ecarts_tr.parametres.confirmer"), icon: BadgeCheck, onSelect: () => confirmer.mutate(p) },
                            "separator",
                            { label: t("ecarts_tr.parametres.ecran"), icon: ExternalLink, onSelect: () => navigate(p.ecran) },
                          ];
                        }}
                      />
                    </div>
                  ) : (
                    <div id={corps} hidden />
                  )}
                </section>
              );
            })}
          </div>
        </div>
      )}

      {selectionnes.length > 0 ? (
        <div className="param-bulkbar" role="region" aria-label={t("premiumParams.page.selection")}>
          <span className="param-bulkbar-count">{t("premiumParams.page.selectionnes", { count: selectionnes.length })}</span>
          <button type="button" className="btn ghost sm" onClick={() => setSelection(new Set())}>
            <X size={14} aria-hidden="true" /> {t("premiumParams.page.effacer")}
          </button>
          <button
            type="button"
            className="btn primary sm"
            disabled={confirmerSelection.isPending}
            onClick={() => window.confirm(t("premiumParams.page.confirmerLotQ", { count: selectionnes.length })) && confirmerSelection.mutate(selectionnes)}
          >
            <BadgeCheck size={14} aria-hidden="true" /> {t("premiumParams.page.confirmerSelection")}
          </button>
        </div>
      ) : null}
      <EditionParametre p={edite} onClose={() => setEdite(null)} />
    </>
  );
}
