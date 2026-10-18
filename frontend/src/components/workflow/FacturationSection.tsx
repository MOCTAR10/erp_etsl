import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate, formatNumber } from "../../lib/format";
import { describeError } from "../../lib/offlineQueue";
import { usePagedList } from "../../lib/usePagedList";
import type { AFacturer, FactureClient, ModeleFacture, Paginated } from "../../types";
import { Badge, Pagination, SearchField, SectionCard } from "../ui";

const CHAMPS: (keyof ModeleFacture)[] = ["entete", "mentions_legales", "conditions_paiement", "coordonnees_bancaires", "pied_page"];

/**
 * Facturation client : jalons et situations « à facturer », factures et avoirs (émission = écriture 411/706/443,
 * puis scellé), modèle d'impression modifiable par ETSL (provisoire jusqu'à confirmation).
 */
export function FacturationSection() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [edition, setEdition] = useState<Partial<ModeleFacture> | null>(null);

  const factures = usePagedList<FactureClient>("factures-clients", (q) =>
    api.get<Paginated<FactureClient>>(`/api/comptabilite/factures-clients/${q}`),
  );
  const aFacturer = useQuery({
    queryKey: ["factures-a-facturer"],
    queryFn: () => api.get<AFacturer>("/api/comptabilite/factures-clients/a-facturer/"),
    retry: 0,
  });
  const modele = useQuery({
    queryKey: ["modele-facture"],
    queryFn: () => api.get<Paginated<ModeleFacture>>("/api/comptabilite/modele-facture/").then((p) => p.results[0]),
    retry: 0,
  });

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["factures-clients"] });
    void qc.invalidateQueries({ queryKey: ["factures-a-facturer"] });
    void qc.invalidateQueries({ queryKey: ["modele-facture"] });
  };
  const action = useMutation({
    mutationFn: (v: { path: string; body?: unknown }) => api.post(v.path, v.body),
    onSuccess: () => {
      setError(null);
      refresh();
    },
    onError: (e) => setError(describeError(e)),
  });
  const modifierModele = useMutation({
    mutationFn: (v: { id: string; body: Partial<ModeleFacture> }) => api.patch(`/api/comptabilite/modele-facture/${v.id}/`, v.body),
    onSuccess: () => {
      setEdition(null);
      setError(null);
      refresh();
    },
    onError: (e) => setError(describeError(e)),
  });

  if (factures.query.isError) return null; // pas de droit de lecture : la section n'apparaît pas
  const rows = factures.rows;
  const m = modele.data;
  const jalons = aFacturer.data?.jalons ?? [];
  const situations = aFacturer.data?.situations ?? [];

  return (
    <SectionCard title={t("facturation.title")}>
      <p className="muted">{t("facturation.hint")}</p>
      {m?.est_provisoire && (
        <p className="action-error" role="note" data-testid="alerte-modele-provisoire">
          {t("facturation.warnModele")}
        </p>
      )}
      {error && <p className="action-error" role="alert">{error}</p>}

      {(jalons.length > 0 || situations.length > 0) && (
        <>
          <h4 className="section-heading">{t("facturation.aFacturer", { count: jalons.length + situations.length })}</h4>
          <table className="table">
            <tbody>
              {jalons.map((j) => (
                <tr key={j.id}>
                  <td>{j.affaire} — {j.label}</td>
                  <td className="num">{j.montant === null ? "••••••" : `${formatNumber(Number(j.montant))} F`}</td>
                  <td>
                    <button type="button" className="btn ghost" onClick={() => action.mutate({ path: "/api/comptabilite/factures-clients/depuis-jalon/", body: { jalon: j.id } })}>
                      {t("facturation.facturer")}
                    </button>
                  </td>
                </tr>
              ))}
              {situations.map((s) => (
                <tr key={s.id}>
                  <td>{s.code} — {s.affaire} {s.label}</td>
                  <td className="num">{s.montant === null ? "••••••" : `${formatNumber(Number(s.montant))} F`}</td>
                  <td>
                    <button type="button" className="btn ghost" onClick={() => action.mutate({ path: "/api/comptabilite/factures-clients/depuis-situation/", body: { situation: s.id } })}>
                      {t("facturation.facturer")}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      <h4 className="section-heading">{t("facturation.factures", { count: factures.count })}</h4>
      <SearchField value={factures.search} onChange={factures.setSearch} placeholder={t("facturation.search")} />
      {rows.length === 0 ? (
        <p className="muted">{t("facturation.aucune")}</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>{t("facturation.numero")}</th>
              <th>{t("facturation.client")}</th>
              <th>{t("facturation.date")}</th>
              <th className="num">{t("facturation.ttc")}</th>
              <th>{t("facturation.statut")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((f) => (
              <tr key={f.id}>
                <td><strong>{f.code}</strong></td>
                <td>{f.client_name}</td>
                <td>{formatDate(f.date)}</td>
                <td className="num">{f.montant_ttc === null ? "••••••" : `${formatNumber(Number(f.montant_ttc))} F`}</td>
                <td>
                  <Badge tone={f.statut === "emise" ? "ok" : "warn"}>{t(`facturation.st.${f.statut}`)}</Badge>{" "}
                  {f.nature === "avoir" && <Badge tone="brand">{t("facturation.avoir")}</Badge>}
                </td>
                <td>
                  {f.statut === "brouillon" && (
                    <button type="button" className="btn" onClick={() => window.confirm(t("facturation.confirmEmettre")) && action.mutate({ path: `/api/comptabilite/factures-clients/${f.id}/emettre/` })}>
                      {t("facturation.emettre")}
                    </button>
                  )}
                  {f.statut === "emise" && f.nature === "facture" && (
                    <button
                      type="button"
                      className="btn ghost"
                      onClick={() => {
                        const montant = window.prompt(t("facturation.avoirPrompt"));
                        if (montant !== null) action.mutate({ path: `/api/comptabilite/factures-clients/${f.id}/avoir/`, body: montant ? { montant_ht: montant } : {} });
                      }}
                    >
                      {t("facturation.faireAvoir")}
                    </button>
                  )}{" "}
                  <button type="button" className="btn ghost" onClick={() => void api.download(`/api/comptabilite/factures-clients/${f.id}/pdf/`, `${f.code}.pdf`)}>
                    PDF
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <Pagination page={factures.page} pageSize={factures.pageSize} count={factures.count} onPageChange={factures.setPage} onPageSizeChange={factures.setPageSize} />

      {m && (
        <>
          <h4 className="section-heading">
            {t("facturation.modele")} <Badge tone={m.est_provisoire ? "warn" : "ok"}>{t(`facturation.${m.statut_valeur}`)}</Badge>
          </h4>
          {edition ? (
            <div>
              {CHAMPS.map((c) => (
                <label key={c} style={{ display: "block", marginBottom: "0.5rem" }}>
                  {t(`facturation.champ.${c}`)}
                  <textarea
                    rows={2}
                    style={{ width: "100%" }}
                    value={String(edition[c] ?? "")}
                    onChange={(e) => setEdition({ ...edition, [c]: e.target.value })}
                  />
                </label>
              ))}
              <button type="button" className="btn" onClick={() => modifierModele.mutate({ id: m.id, body: edition })}>{t("facturation.valider")}</button>{" "}
              <button type="button" className="btn ghost" onClick={() => setEdition(null)}>{t("facturation.annuler")}</button>
            </div>
          ) : (
            <>
              <pre className="muted" style={{ whiteSpace: "pre-wrap" }}>{m.entete}</pre>
              <button type="button" className="btn ghost" onClick={() => setEdition({ entete: m.entete, mentions_legales: m.mentions_legales, conditions_paiement: m.conditions_paiement, coordonnees_bancaires: m.coordonnees_bancaires, pied_page: m.pied_page })}>
                {t("facturation.modifier")}
              </button>{" "}
              {m.est_provisoire && (
                <button type="button" className="btn ghost" onClick={() => window.confirm(t("facturation.confirmModele")) && action.mutate({ path: `/api/comptabilite/modele-facture/${m.id}/confirmer/` })}>
                  {t("facturation.confirmer")}
                </button>
              )}
            </>
          )}
        </>
      )}
    </SectionCard>
  );
}
