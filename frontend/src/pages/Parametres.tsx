import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Download, ExternalLink, Pencil, X } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import { Badge, ErrorState, KpiGridSkeleton, PageHeader, SearchField, SectionCard } from "../components/ui";
import { formatDateTime } from "../lib/format";
import { describeError } from "../lib/offlineQueue";
import { corpsEdition, parModule, SaisieInvalide, type ParametreEtsl } from "../lib/parametres";

/** Une ligne : valeur modifiable sur place (endpoint de l'application) et confirmation par ETSL. */
function LigneParametre({ p }: { p: ParametreEtsl }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [edition, setEdition] = useState(false);
  const [saisie, setSaisie] = useState(p.valeur);
  const [erreur, setErreur] = useState<string | null>(null);
  const refresh = () => {
    setErreur(null);
    void qc.invalidateQueries();
  };

  const enregistrer = useMutation({
    mutationFn: () => {
      const corps = corpsEdition(p, saisie);
      return p.edition.method === "PATCH" ? api.patch<unknown>(p.edition.path, corps) : api.post<unknown>(p.edition.path, corps);
    },
    onSuccess: () => {
      setEdition(false);
      refresh();
    },
    onError: (e) => setErreur(e instanceof SaisieInvalide ? t("ecarts_tr.parametres.saisieInvalide", { type: e.message }) : describeError(e)),
  });
  const confirmer = useMutation({
    mutationFn: () => api.post<unknown>(p.confirmation),
    onSuccess: refresh,
    onError: (e) => setErreur(describeError(e)),
  });

  return (
    <tr data-testid="parametre-etsl">
      <td>
        <strong>{p.label}</strong>
        <div className="muted" style={{ fontSize: 12 }}>
          {p.code}
          {p.groupe ? ` · ${p.groupe}` : ""}
        </div>
      </td>
      <td>
        {edition ? (
          <form
            className="action-bar-buttons"
            onSubmit={(e) => {
              e.preventDefault();
              enregistrer.mutate();
            }}
          >
            <label className="sr-only" htmlFor={`param-${p.id}`}>
              {p.label}
            </label>
            {p.type_valeur === "json" ? (
              <textarea id={`param-${p.id}`} rows={3} value={saisie} onChange={(e) => setSaisie(e.target.value)} />
            ) : (
              <input
                id={`param-${p.id}`}
                value={saisie}
                inputMode={p.type_valeur === "texte" ? "text" : "decimal"}
                onChange={(e) => setSaisie(e.target.value)}
                autoFocus
              />
            )}
            <button type="submit" className="btn primary" disabled={enregistrer.isPending} aria-label={t("ecarts_tr.parametres.enregistrer")}>
              <Check size={14} aria-hidden="true" />
            </button>
            <button
              type="button"
              className="btn ghost"
              aria-label={t("actionBar.annuler")}
              onClick={() => {
                setEdition(false);
                setSaisie(p.valeur);
                setErreur(null);
              }}
            >
              <X size={14} aria-hidden="true" />
            </button>
          </form>
        ) : (
          <span className="num" style={{ wordBreak: "break-word" }}>
            {p.valeur || "—"} {p.unite && <span className="muted">{p.unite}</span>}
          </span>
        )}
        {erreur && (
          <p className="action-error" role="alert">
            {erreur}
          </p>
        )}
      </td>
      <td>
        {p.provisoire ? (
          <Badge tone="warn">{t("ecarts_tr.parametres.provisoire")}</Badge>
        ) : (
          <Badge tone="ok">{t("ecarts_tr.parametres.confirme")}</Badge>
        )}
        {!p.provisoire && p.confirme_par ? (
          <div className="muted" style={{ fontSize: 12 }}>
            {p.confirme_par}
            {p.confirme_le ? ` · ${formatDateTime(p.confirme_le)}` : ""}
          </div>
        ) : null}
      </td>
      <td>
        <div className="action-bar-buttons">
          {!edition && (
            <button type="button" className="btn ghost" onClick={() => setEdition(true)}>
              <Pencil size={14} aria-hidden="true" /> {t("ecarts_tr.parametres.modifier")}
            </button>
          )}
          {p.provisoire && (
            <button type="button" className="btn primary" disabled={confirmer.isPending} onClick={() => confirmer.mutate()}>
              {t("ecarts_tr.parametres.confirmer")}
            </button>
          )}
          <Link className="btn ghost" to={p.ecran} title={t("ecarts_tr.parametres.ecran")}>
            <ExternalLink size={14} aria-hidden="true" />
            <span className="sr-only">{t("ecarts_tr.parametres.ecran")}</span>
          </Link>
        </div>
      </td>
    </tr>
  );
}

/** « Paramètres ETSL » : tous les paramètres provisoires des modules, modifiables et confirmables au même endroit. */
export function ParametresPage() {
  const { t } = useTranslation();
  const [module, setModule] = useState("");
  const [aConfirmer, setAConfirmer] = useState(false);
  const [recherche, setRecherche] = useState("");
  const qs = new URLSearchParams();
  if (module) qs.set("module", module);
  if (aConfirmer) qs.set("statut", "provisoire");
  if (recherche.trim()) qs.set("search", recherche.trim());
  const filtre = qs.toString();
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["parametres-etsl", filtre],
    queryFn: () => api.parametresEtsl(filtre ? `?${filtre}` : ""),
  });
  const exporter = (fmt: "xlsx" | "pdf") =>
    void api.download(`/api/parametres-etsl/?export=${fmt}${filtre ? `&${filtre}` : ""}`, `parametres_etsl.${fmt}`);

  return (
    <>
      <PageHeader title={t("ecarts_tr.parametres.title")} subtitle={t("ecarts_tr.parametres.subtitle")} />
      <p className="action-error" role="note" data-testid="alerte-provisoire-parametres">
        {t("ecarts_tr.parametres.bandeau", { count: data?.provisoires ?? 0 })}
      </p>
      <SectionCard
        title={t("ecarts_tr.parametres.filtres")}
        actions={
          <div className="action-bar-buttons">
            <button type="button" className="btn ghost" onClick={() => exporter("xlsx")}>
              <Download size={14} aria-hidden="true" /> Excel
            </button>
            <button type="button" className="btn ghost" onClick={() => exporter("pdf")}>
              <Download size={14} aria-hidden="true" /> PDF
            </button>
          </div>
        }
      >
        <div className="quick-form-grid">
          <div className="field">
            <label htmlFor="param-module">{t("ecarts_tr.parametres.module")}</label>
            <select id="param-module" value={module} onChange={(e) => setModule(e.target.value)}>
              <option value="">{t("ecarts_tr.parametres.tous")}</option>
              {(data?.modules ?? []).map((m) => (
                <option key={m.module} value={m.module}>
                  {m.label}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="param-statut">{t("ecarts_tr.parametres.statut")}</label>
            <select id="param-statut" value={aConfirmer ? "provisoire" : ""} onChange={(e) => setAConfirmer(e.target.value === "provisoire")}>
              <option value="">{t("ecarts_tr.parametres.tous")}</option>
              <option value="provisoire">{t("ecarts_tr.parametres.aConfirmer")}</option>
            </select>
          </div>
        </div>
        <SearchField value={recherche} onChange={setRecherche} placeholder={t("ecarts_tr.parametres.rechercher")} />
      </SectionCard>

      {isLoading ? (
        <KpiGridSkeleton count={3} />
      ) : isError || !data ? (
        <ErrorState message={t("common.error")} onRetry={() => void refetch()} retryLabel={t("common.retry")} />
      ) : data.results.length === 0 ? (
        <p className="muted">{t("common.empty")}</p>
      ) : (
        parModule(data.results).map((g) => (
          <SectionCard
            key={g.module}
            title={g.label}
            subtitle={t("ecarts_tr.parametres.compteModule", {
              total: g.rows.length,
              provisoires: g.rows.filter((r) => r.provisoire).length,
            })}
          >
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th scope="col">{t("ecarts_tr.parametres.parametre")}</th>
                    <th scope="col">{t("ecarts_tr.parametres.valeur")}</th>
                    <th scope="col">{t("ecarts_tr.parametres.statut")}</th>
                    <th scope="col">{t("ecarts_tr.parametres.actions")}</th>
                  </tr>
                </thead>
                <tbody>
                  {g.rows.map((p) => (
                    <LigneParametre key={`${p.modele}-${p.id}-${p.valeur}-${p.provisoire}`} p={p} />
                  ))}
                </tbody>
              </table>
            </div>
          </SectionCard>
        ))
      )}
    </>
  );
}
