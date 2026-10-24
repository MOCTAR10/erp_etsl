import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate, formatMoney } from "../../lib/format";
import { describeError } from "../../lib/offlineQueue";
import { usePagedList } from "../../lib/usePagedList";
import type { AFacturer, FactureClient, ModeleFacture, Paginated } from "../../types";
import { Badge, FilterBar, Menu, Pagination, SearchField, SectionCard } from "../ui";
import { useFiltresListe } from "../../lib/useFiltresListe";

const CHAMPS: (keyof ModeleFacture)[] = ["entete", "mentions_legales", "conditions_paiement", "coordonnees_bancaires", "pied_page"];

/** Libellé de critère servi en minuscules par l'API (« nature ») → casse de phrase (« Nature »). */
const casseDePhrase = (s: string) => (s ? s.charAt(0).toLocaleUpperCase("fr") + s.slice(1) : s);

/**
 * Facturation client : jalons et situations « à facturer », factures et avoirs (émission = écriture 411/706/443,
 * puis scellé), modèle d'impression modifiable par ETSL (provisoire jusqu'à confirmation).
 */
export function FacturationSection() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [edition, setEdition] = useState<Partial<ModeleFacture> | null>(null);

  const filtresFc = useFiltresListe("/api/comptabilite/factures-clients/");
  const factures = usePagedList<FactureClient>(
    "factures-clients",
    (q) => api.get<Paginated<FactureClient>>(`/api/comptabilite/factures-clients/${q}`),
    { extra: filtresFc.extra },
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
        <div className="banner warn" role="note" data-testid="alerte-modele-provisoire">
          <AlertTriangle size={18} aria-hidden />
          <div className="banner-body">
            <span className="banner-text">{t("facturation.warnModele")}</span>
          </div>
        </div>
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
                  <td className="num">{j.montant === null ? "••••••" : formatMoney(j.montant)}</td>
                  <td className="num">
                    <button type="button" className="btn ghost sm" disabled={action.isPending} onClick={() => action.mutate({ path: "/api/comptabilite/factures-clients/depuis-jalon/", body: { jalon: j.id } })}>
                      {t("facturation.facturer")}
                    </button>
                  </td>
                </tr>
              ))}
              {situations.map((s) => (
                <tr key={s.id}>
                  <td>{s.code} — {s.affaire} {s.label}</td>
                  <td className="num">{s.montant === null ? "••••••" : formatMoney(s.montant)}</td>
                  <td className="num">
                    <button type="button" className="btn ghost sm" disabled={action.isPending} onClick={() => action.mutate({ path: "/api/comptabilite/factures-clients/depuis-situation/", body: { situation: s.id } })}>
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
      <FilterBar defs={filtresFc.defs.map((d) => ({ ...d, libelle: casseDePhrase(d.libelle) }))} value={filtresFc.criteres} onChange={filtresFc.setCriteres} idPrefix="fc-f" />
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
              <th className="num">
                <span className="sr-only">{t("ui.actions")}</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((f) => (
              <tr key={f.id}>
                <td>
                  <strong>{f.code}</strong>
                  {f.move_number && <span className="muted"> · {f.move_number}</span>}
                </td>
                <td>{f.client_name}</td>
                <td>{formatDate(f.date)}</td>
                <td className="num">{f.montant_ttc === null ? "••••••" : formatMoney(f.montant_ttc)}</td>
                <td>
                  <Badge tone={f.statut === "emise" ? "ok" : "warn"}>{t(`facturation.st.${f.statut}`)}</Badge>{" "}
                  {f.nature === "avoir" && <Badge tone="brand">{t("facturation.avoir")}</Badge>}
                </td>
                <td className="num">
                  <div className="card-actions card-actions--end">
                    {f.statut === "brouillon" ? (
                      <button
                        type="button"
                        className="btn ghost sm"
                        disabled={action.isPending}
                        onClick={() => window.confirm(t("facturation.confirmEmettre")) && action.mutate({ path: `/api/comptabilite/factures-clients/${f.id}/emettre/` })}
                      >
                        {t("facturation.emettre")}
                      </button>
                    ) : (
                      <button type="button" className="btn ghost sm" onClick={() => void api.download(`/api/comptabilite/factures-clients/${f.id}/pdf/`, `${f.code}.pdf`)}>
                        PDF
                      </button>
                    )}
                    {(f.statut === "brouillon" || f.nature === "facture") && (
                      <Menu
                        size="sm"
                        align="end"
                        label={t("ui.rowActions")}
                        items={[
                          f.statut === "brouillon" && {
                            id: "pdf",
                            label: "PDF",
                            onSelect: () => void api.download(`/api/comptabilite/factures-clients/${f.id}/pdf/`, `${f.code}.pdf`),
                          },
                          f.statut === "emise" &&
                            f.nature === "facture" && {
                              id: "avoir",
                              label: t("revueKit.fin.faireAvoir"),
                              disabled: action.isPending,
                              onSelect: () => {
                                const montant = window.prompt(t("facturation.avoirPrompt"));
                                if (montant !== null) action.mutate({ path: `/api/comptabilite/factures-clients/${f.id}/avoir/`, body: montant ? { montant_ht: montant } : {} });
                              },
                            },
                        ]}
                      />
                    )}
                  </div>
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
                <div className="field" key={c}>
                  <label htmlFor={`modele-facture-${c}`}>{t(`facturation.champ.${c}`)}</label>
                  <textarea
                    id={`modele-facture-${c}`}
                    rows={2}
                    value={String(edition[c] ?? "")}
                    onChange={(e) => setEdition({ ...edition, [c]: e.target.value })}
                  />
                </div>
              ))}
              <button type="button" className="btn primary" onClick={() => modifierModele.mutate({ id: m.id, body: edition })}>{t("facturation.valider")}</button>{" "}
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
