import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate, formatNumber } from "../../lib/format";
import { describeError } from "../../lib/offlineQueue";
import type { ClotureMensuelle, ControlesCloture, Paginated, PeriodeRef } from "../../types";
import { Badge, SectionCard } from "../ui";

const MONTANTS = ["produits", "charges", "resultat", "tresorerie", "creances_clients", "dettes_fournisseurs", "tva_nette"] as const;

/**
 * Clôture mensuelle : contrôles de pré-clôture, chrono (objectif < 2 h), synthèse figée et envoi à la Direction
 * à J+4. Objectif et jour d'envoi sont des paramètres ETSL (voir « Lettrage et paramètres »).
 */
export function ClotureSection() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [periode, setPeriode] = useState("");
  const [error, setError] = useState<string | null>(null);

  const periodes = useQuery({
    queryKey: ["cloture-periodes"],
    queryFn: () => api.get<Paginated<PeriodeRef>>("/api/accounting/periods/?page_size=60").then((p) => p.results),
    retry: 0,
  });
  const clotures = useQuery({
    queryKey: ["clotures-mensuelles"],
    queryFn: () => api.get<Paginated<ClotureMensuelle>>("/api/comptabilite/clotures-mensuelles/?page_size=24").then((p) => p.results),
    retry: 0,
  });
  const controles = useQuery({
    queryKey: ["cloture-controles", periode],
    queryFn: () => api.get<ControlesCloture>(`/api/comptabilite/clotures-mensuelles/controles/?period=${periode}`),
    enabled: !!periode,
    retry: 0,
  });

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["clotures-mensuelles"] });
    void qc.invalidateQueries({ queryKey: ["cloture-controles"] });
    void qc.invalidateQueries({ queryKey: ["cloture-periodes"] });
  };
  const action = useMutation({
    mutationFn: (v: { path: string; body?: unknown }) => api.post(v.path, v.body),
    onSuccess: () => {
      setError(null);
      refresh();
    },
    onError: (e) => setError(describeError(e)),
  });

  if (clotures.isError) return null;
  const rows = clotures.data ?? [];
  const courante = rows.find((c) => c.period === Number(periode) || String(c.period) === periode);
  const ouvertes = (periodes.data ?? []).filter((p) => p.status === "open");

  return (
    <SectionCard title={t("cloture.title")}>
      <p className="muted">{t("cloture.hint")}</p>
      {error && <p className="action-error" role="alert">{error}</p>}

      <div className="row-actions">
        <select aria-label={t("cloture.periode")} value={periode} onChange={(e) => setPeriode(e.target.value)}>
          <option value="">{t("cloture.choisir")}</option>
          {ouvertes.map((p) => (
            <option key={p.id} value={p.id}>{formatDate(p.start_date)} → {formatDate(p.end_date)}</option>
          ))}
        </select>
        <button
          type="button"
          className="btn"
          disabled={!periode || !!courante || action.isPending}
          onClick={() => action.mutate({ path: "/api/comptabilite/clotures-mensuelles/demarrer/", body: { period: periode } })}
        >
          {t("cloture.demarrer")}
        </button>
        {courante && courante.statut === "en_cours" && (
          <button type="button" className="btn" disabled={action.isPending} onClick={() => action.mutate({ path: `/api/comptabilite/clotures-mensuelles/${courante.id}/cloturer/` })}>
            {t("cloture.cloturer")}
          </button>
        )}
      </div>

      {controles.data && (
        <table className="table" data-testid="cloture-controles">
          <tbody>
            {controles.data.controles.map((c) => (
              <tr key={c.code}>
                <td>{c.label}</td>
                <td className="num">{c.nb}</td>
                <td>
                  <Badge tone={c.nb === 0 ? "ok" : c.bloquant ? "err" : "warn"}>
                    {c.nb === 0 ? t("cloture.ok") : c.bloquant ? t("cloture.bloquant") : t("cloture.avertissement")}
                  </Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {rows.length > 0 && <h4 className="section-heading">{t("cloture.suivi")}</h4>}
      {rows.map((c) => (
        <div key={c.id} className="card" style={{ marginBottom: "0.75rem" }}>
          <p>
            <strong>{c.periode}</strong>{" "}
            <Badge tone={c.statut === "cloturee" ? "ok" : "warn"}>{t(`cloture.st.${c.statut}`)}</Badge>{" "}
            {c.dans_objectif !== null && (
              <Badge tone={c.dans_objectif ? "ok" : "err"}>
                {t("cloture.duree", { min: c.duree_minutes, objectif: c.objectif_minutes })}
              </Badge>
            )}{" "}
            {c.retard && <Badge tone="err">{t(`cloture.retard.${c.retard}`)}</Badge>}
          </p>
          {c.statut === "cloturee" && c.has_amount_access && (
            <p className="muted">
              {MONTANTS.map((k) => `${t(`cloture.m.${k}`)} : ${formatNumber(Number(c.synthese[k]))} F`).join(" · ")}
            </p>
          )}
          {c.statut === "cloturee" && (
            <p className="muted">
              {c.envoyee_le
                ? t("cloture.envoyee", { date: formatDate(c.envoyee_le), n: c.destinataires.length })
                : t("cloture.echeance", { date: c.echeance_envoi ? formatDate(c.echeance_envoi) : "—" })}
            </p>
          )}
          {c.statut === "cloturee" && !c.envoyee_le && (
            <button type="button" className="btn ghost" onClick={() => action.mutate({ path: `/api/comptabilite/clotures-mensuelles/${c.id}/envoyer-direction/` })}>
              {t("cloture.envoyer")}
            </button>
          )}{" "}
          {c.statut === "cloturee" && (
            <button
              type="button"
              className="btn ghost"
              onClick={() => {
                const motif = window.prompt(t("cloture.motifPrompt"));
                if (motif) action.mutate({ path: `/api/comptabilite/clotures-mensuelles/${c.id}/rouvrir/`, body: { motif } });
              }}
            >
              {t("cloture.rouvrir")}
            </button>
          )}
        </div>
      ))}
    </SectionCard>
  );
}
