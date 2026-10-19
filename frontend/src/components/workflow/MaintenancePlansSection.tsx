import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate } from "../../lib/format";
import { describeError } from "../../lib/offlineQueue";
import type { Actif, CalendrierPreventif, ExigenceHabilitationMaintenance, HistoriqueStatutOT, OrdreTravail, PlanPreventif } from "../../types";
import { Badge, QuickForm, SectionCard } from "../ui";

const moisCourant = () => new Date().toISOString().slice(0, 7);

/**
 * Plans préventifs M8 (CDC M8.2 / §13.4) : saisie par machine ou composant (périodicité et / ou intervalle
 * compteur), pré-alerte paramétrable avant l'échéance, déclenchement des plans échus et calendrier mensuel.
 */
export function PlansPreventifsSection({ actifs }: { actifs: Actif[] }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [mois, setMois] = useState(moisCourant());
  const [info, setInfo] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const plans = useQuery({ queryKey: ["maintenance-plans"], queryFn: () => api.listAll<PlanPreventif>("/api/maintenance/plans/"), retry: 0 });
  const calendrier = useQuery({
    queryKey: ["maintenance-calendrier", mois],
    queryFn: () => api.get<CalendrierPreventif>(`/api/maintenance/plans/calendrier/?mois=${mois}`),
    enabled: /^\d{4}-\d{2}$/.test(mois),
    retry: 0,
  });
  const declencher = useMutation({
    mutationFn: () => api.post<{ ot_generes: string[] }>("/api/maintenance/plans/declencher/"),
    onSuccess: (r) => {
      setError(null);
      setInfo(r.ot_generes.length ? t("m8e.plans.generes", { codes: r.ot_generes.join(", ") }) : t("m8e.plans.aucunEchu"));
      void qc.invalidateQueries();
    },
    onError: (e) => setError(describeError(e)),
  });

  if (plans.isError) return null; // pas de droit de lecture M8 : la section n'apparaît pas
  const rows = plans.data ?? [];
  const cal = calendrier.data;

  return (
    <SectionCard title={`${t("m8e.plans.title")} · ${rows.length}`}>
      <div data-testid="plans-preventifs">
        <p className="muted">{t("m8e.plans.hint")}</p>
        <div className="action-bar-buttons">
          <QuickForm
            title={t("m8e.plans.nouveau")}
            endpoint="/api/maintenance/plans/"
            fields={[
              {
                name: "actif", label: t("m8e.plans.actif"), type: "select", required: true,
                options: actifs.map((a) => ({ value: a.id, label: `${a.code} · ${a.designation}` })),
              },
              { name: "libelle", label: t("m8e.plans.libelle"), required: true },
              { name: "composant", label: t("m8e.plans.composant") },
              { name: "periodicite_jours", label: t("m8e.plans.periodicite"), type: "number", min: 1, step: "1" },
              { name: "intervalle_compteur", label: t("m8e.plans.intervalle"), type: "number", min: 0, step: "0.01" },
              { name: "derniere_date", label: t("m8e.plans.derniereDate"), type: "date" },
              {
                name: "priorite", label: t("m8e.plans.priorite"), type: "select", required: true, defaultValue: "moyenne",
                options: ["basse", "moyenne", "haute", "critique"].map((v) => ({ value: v, label: t(`maintenance.ot_priorites.${v}`) })),
              },
            ]}
          />
          <button type="button" className="btn" onClick={() => declencher.mutate()} disabled={declencher.isPending}>
            {t("m8e.plans.declencher")}
          </button>
        </div>
        {info && <p className="muted" role="status" data-testid="plans-info">{info}</p>}
        {error && <p className="action-error" role="alert">{error}</p>}
        {rows.length === 0 ? (
          <p className="muted">{t("m8e.plans.aucun")}</p>
        ) : (
          <table className="table">
            <caption className="sr-only">{t("m8e.plans.title")}</caption>
            <thead>
              <tr>
                <th>{t("m8e.plans.code")}</th>
                <th>{t("m8e.plans.actif")}</th>
                <th>{t("m8e.plans.libelle")}</th>
                <th>{t("m8e.plans.declencheur")}</th>
                <th>{t("m8e.plans.prochaine")}</th>
                <th>{t("m8e.plans.etat")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((p) => (
                <tr key={p.id}>
                  <td><strong>{p.code}</strong></td>
                  <td>{p.actif_code}</td>
                  <td>{p.libelle}{p.composant ? <span className="muted"> · {p.composant}</span> : null}</td>
                  <td>
                    {[
                      p.periodicite_jours ? t("m8e.plans.tousLes", { n: p.periodicite_jours }) : null,
                      p.intervalle_compteur ? t("m8e.plans.toutesLes", { n: p.intervalle_compteur }) : null,
                    ].filter(Boolean).join(" · ")}
                  </td>
                  <td>
                    {[
                      p.prochaine_date ? formatDate(p.prochaine_date) : null,
                      p.prochain_compteur ? `${p.compteur_actuel} / ${p.prochain_compteur}` : null,
                    ].filter(Boolean).join(" · ")}
                  </td>
                  <td>
                    {p.echeance ? <Badge tone="err">{t("m8e.plans.echu")}</Badge> : p.prealerte ? <Badge tone="warn">{t("m8e.plans.prealerte")}</Badge> : <Badge tone="ok">{t("m8e.plans.aJour")}</Badge>}
                    {p.ot_ouvert ? <span className="muted"> · {p.ot_ouvert}</span> : null}
                    {(p.echeance || p.prealerte) && <div className="muted">{p.echeance ?? p.prealerte}</div>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <h4 className="section-heading">{t("m8e.cal.title")}</h4>
        <label>
          {t("m8e.cal.mois")}{" "}
          <input type="month" value={mois} onChange={(e) => setMois(e.target.value)} aria-label={t("m8e.cal.mois")} />
        </label>
        {cal?.provisoire && (
          <p className="action-error" role="note" data-testid="alerte-provisoire-prealerte">
            {t("m8e.cal.warnProvisoire", { jours: cal.prealerte_jours, pct: cal.prealerte_pct })}
          </p>
        )}
        {cal && cal.occurrences.length === 0 && <p className="muted">{t("m8e.cal.aucune")}</p>}
        {cal && cal.occurrences.length > 0 && (
          <table className="table" data-testid="calendrier-preventif">
            <caption className="sr-only">{t("m8e.cal.title")}</caption>
            <thead>
              <tr>
                <th>{t("m8e.cal.date")}</th>
                <th>{t("m8e.plans.actif")}</th>
                <th>{t("m8e.plans.libelle")}</th>
                <th>{t("m8e.plans.etat")}</th>
              </tr>
            </thead>
            <tbody>
              {cal.occurrences.map((o) => (
                <tr key={`${o.plan}-${o.date}`}>
                  <td><time dateTime={o.date}>{formatDate(o.date)}</time></td>
                  <td>{o.actif} <span className="muted">· {o.designation}</span></td>
                  <td>{o.plan} — {o.libelle}{o.composant ? ` (${o.composant})` : ""}</td>
                  <td>{o.echu ? <Badge tone="err">{t("m8e.plans.echu")}</Badge> : <Badge tone="brand">{t("m8e.cal.prevu")}</Badge>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {cal && cal.compteurs.length > 0 && (
          <p className="muted">
            {t("m8e.cal.compteurs")}{" "}
            {cal.compteurs.map((c) => `${c.plan} ${c.actif} ${c.compteur_actuel} / ${c.prochain_compteur}`).join(" · ")}
          </p>
        )}
      </div>
    </SectionCard>
  );
}

/** Détail d'un OT (CDC M8 §13.5 / M8.4) : historique horodaté des statuts et saisie de la main-d'œuvre. */
export function OtDetails({ ot }: { ot: OrdreTravail }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [heures, setHeures] = useState(ot.heures_mo ?? "");
  const [tarif, setTarif] = useState(ot.tarif_horaire ?? "");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const historique = useQuery({
    queryKey: ["maintenance-ot-historique", ot.id],
    queryFn: () => api.get<HistoriqueStatutOT[]>(`/api/maintenance/ordres/${ot.id}/historique/`),
    enabled: open,
    retry: 0,
  });
  const enregistrer = useMutation({
    mutationFn: () => api.patch(`/api/maintenance/ordres/${ot.id}/`, { heures_mo: heures || "0", tarif_horaire: tarif || "0" }),
    onSuccess: () => {
      setMsg({ ok: true, text: t("quickForm.created") });
      void qc.invalidateQueries({ queryKey: ["maintenance-ordres"] });
    },
    onError: (e) => setMsg({ ok: false, text: describeError(e) }),
  });
  const modifiable = ot.has_amount_access && !["cloture", "archive", "annule"].includes(ot.statut);

  return (
    <details className="ot-details" onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}>
      <summary>{t("m8e.ot.details")}</summary>
      {ot.document_titre && <p className="muted">{t("m8e.ot.archiveGed", { titre: ot.document_titre })}</p>}
      {ot.qualifie_par_name && (
        <p className="muted">{t("m8e.ot.qualifiePar", { nom: ot.qualifie_par_name })} · {ot.cause}</p>
      )}
      {modifiable && (
        <form
          className="inline-form"
          aria-label={t("m8e.ot.mainOeuvre")}
          onSubmit={(e) => {
            e.preventDefault();
            setMsg(null);
            enregistrer.mutate();
          }}
        >
          <label>
            {t("m8e.ot.heures")}{" "}
            <input type="number" min={0} step="0.25" value={heures} onChange={(e) => setHeures(e.target.value)} />
          </label>{" "}
          <label>
            {t("m8e.ot.tarif")}{" "}
            <input type="number" min={0} step="1" value={tarif} onChange={(e) => setTarif(e.target.value)} />
          </label>{" "}
          <button type="submit" className="btn" disabled={enregistrer.isPending}>{t("quickForm.save")}</button>
          {msg && <span className={msg.ok ? "quick-form-ok" : "action-error"} role={msg.ok ? "status" : "alert"}> {msg.text}</span>}
        </form>
      )}
      {open && (
        <ol className="ot-historique" aria-label={t("m8e.ot.historique")}>
          {(historique.data ?? []).map((h) => (
            <li key={h.id}>
              <time dateTime={h.le}>{formatDate(h.le)}</time> · {h.de ? `${t(`maintenance.ot_statut.${h.de}`)} → ` : ""}
              {t(`maintenance.ot_statut.${h.vers}`)}
              {h.par_name ? ` · ${h.par_name}` : ""}
              {h.commentaire ? ` · ${h.commentaire}` : ""}
            </li>
          ))}
        </ol>
      )}
    </details>
  );
}

/** Habilitations exigées du technicien (CDC M8 §13.10, amont M9) : donnée ETSL saisie ici, contrôlée à la
 * planification et au démarrage de l'OT (qualification RH valide dont l'intitulé contient le mot-clé). */
export function ExigencesHabilitationSection() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const q = useQuery({
    queryKey: ["maintenance-exigences"],
    queryFn: () => api.listAll<ExigenceHabilitationMaintenance>("/api/maintenance/exigences-habilitation/"),
    retry: 0,
  });
  const supprimer = useMutation({
    mutationFn: (id: string) => api.remove(`/api/maintenance/exigences-habilitation/${id}/`),
    onSuccess: () => {
      setError(null);
      void qc.invalidateQueries({ queryKey: ["maintenance-exigences"] });
    },
    onError: (e) => setError(describeError(e)),
  });
  if (q.isError) return null;
  const rows = q.data ?? [];
  return (
    <SectionCard title={`${t("m8e.hab.title")} · ${rows.length}`}>
      <div data-testid="exigences-habilitation">
        <p className="muted">{t("m8e.hab.hint")}</p>
        <QuickForm
          title={t("m8e.hab.nouvelle")}
          endpoint="/api/maintenance/exigences-habilitation/"
          fields={[
            {
              name: "categorie_actif", label: t("m8e.hab.categorie"), type: "select",
              options: ["machine", "engin", "levage", "atelier", "chantier", "outillage"].map((v) => ({ value: v, label: t(`maintenance.categories.${v}`) })),
            },
            {
              name: "type_ot", label: t("m8e.hab.type"), type: "select",
              options: ["correctif", "preventif", "urgence", "inspection"].map((v) => ({ value: v, label: t(`maintenance.ot_types.${v}`) })),
            },
            { name: "mot_cle", label: t("m8e.hab.motCle"), required: true },
          ]}
        />
        {error && <p className="action-error" role="alert">{error}</p>}
        {rows.length === 0 ? (
          <p className="muted">{t("m8e.hab.aucune")}</p>
        ) : (
          <table className="table">
            <caption className="sr-only">{t("m8e.hab.title")}</caption>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td>{r.categorie_label || t("m8e.hab.toutes")}</td>
                  <td>{r.type_label || t("m8e.hab.tous")}</td>
                  <td><strong>{r.mot_cle}</strong></td>
                  <td>
                    <button type="button" className="btn ghost" onClick={() => window.confirm(t("m8e.hab.confirmSupprimer")) && supprimer.mutate(r.id)}>
                      {t("m8e.hab.supprimer")}
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
