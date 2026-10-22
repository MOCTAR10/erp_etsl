import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatNumber } from "../../lib/format";
import { describeError } from "../../lib/offlineQueue";
import { ActionBar, Badge, QuickForm, SectionCard } from "../ui";
import { ProvisionsChangeA7 } from "./ProvisionsChangeA7";

interface SituationDevise {
  devise: string;
  date: string | null;
  taux: string | null;
  provisoire: boolean;
  age_jours: number | null;
  a_jour: boolean;
}
interface Taux {
  id: number;
  devise_code: string;
  date: string;
  taux: string;
  source_label: string;
  est_provisoire: boolean;
}
interface Operation {
  id: string;
  code: string;
  sens: "creance" | "dette";
  sens_label: string;
  partner_name: string;
  devise_code: string;
  date: string;
  libelle: string;
  montant_devise: string | null;
  taux_origine: string | null;
  taux_provisoire: boolean;
  contre_valeur: string | null;
  statut: "brouillon" | "comptabilisee" | "reglee";
  statut_label: string;
  move_number: string | null;
  ecart_change: string | null;
  ecart_latent: string | null;
  date_reevaluation: string | null;
}
interface LigneAvancement {
  affaire: string;
  affaire_code: string;
  affaire_label: string;
  erreur?: string;
  methode_label?: string;
  pct_avancement?: string;
  ca_reference?: string | null;
  revenu_cumule?: string | null;
  facture_cumule?: string | null;
  ecart?: string | null;
  nature?: "produits_a_recevoir" | "produits_constates_avance" | "aucune";
  detail?: string;
}
interface Apercu {
  date: string;
  methode: string;
  provisoire: boolean;
  rows: LigneAvancement[];
}
interface Reconnaissance {
  id: string;
  code: string;
  affaire_code: string;
  date_arrete: string;
  pct_avancement: string;
  ecart: string | null;
  statut: string;
  statut_label: string;
  move_number: string | null;
  methode_provisoire: boolean;
}
interface ExportSage {
  id: string;
  date_from: string;
  date_to: string;
  journal: string;
  nb_ecritures: number;
  nb_lignes: number;
  total_debit: string;
  nom_fichier: string;
  sha256: string;
  gabarit_provisoire: boolean;
  created_at: string;
}
interface Ref {
  id: string | number;
  code: string;
  name?: string;
  label?: string;
  account_class?: number;
}

const fcfa = (v: string | null | undefined) => (v === null || v === undefined || v === "" ? "—" : `${formatNumber(Number(v))} F`);

/** Écarts a2 : cours de change et opérations en devise (EX-G-04), revenu à l'avancement, export des écritures vers SAGE. */
export function EcartsA2Section() {
  const { t } = useTranslation();
  const [arrete, setArrete] = useState(new Date().toISOString().slice(0, 10));
  const [dlError, setDlError] = useState<string | null>(null);
  const situation = useQuery({
    queryKey: ["a2", "taux-situation"],
    queryFn: () => api.get<{ devises: SituationDevise[]; provisoire: boolean }>("/api/comptabilite/taux-change/situation/"),
    retry: 0,
  });
  const taux = useQuery({ queryKey: ["a2", "taux"], queryFn: () => api.get<{ results: Taux[] }>("/api/comptabilite/taux-change/"), retry: 0 });
  const ops = useQuery({ queryKey: ["a2", "operations"], queryFn: () => api.listAll<Operation>("/api/comptabilite/operations-devise/"), retry: 0 });
  const apercu = useQuery({
    queryKey: ["a2", "apercu", arrete],
    queryFn: () => api.get<Apercu>(`/api/comptabilite/reconnaissances-revenu/apercu/?date=${arrete}`),
    retry: 0,
  });
  const historique = useQuery({
    queryKey: ["a2", "reconnaissances"],
    queryFn: () => api.get<{ results: Reconnaissance[] }>("/api/comptabilite/reconnaissances-revenu/"),
    retry: 0,
  });
  const exports = useQuery({ queryKey: ["a2", "exports"], queryFn: () => api.get<{ results: ExportSage[] }>("/api/integrations/exports-sage/"), retry: 0 });
  const gabarit = useQuery({ queryKey: ["a2", "gabarit"], queryFn: () => api.get<{ label: string; provisoire: boolean }>("/api/integrations/exports-sage/gabarit/"), retry: 0 });
  const devises = useQuery({ queryKey: ["a2", "devises"], queryFn: () => api.listAll<Ref>("/api/referentiels/currencies/"), retry: 0 }).data ?? [];
  const partners = useQuery({ queryKey: ["m10", "partners"], queryFn: () => api.listAll<Ref>("/api/referentiels/partners/"), retry: 0 }).data ?? [];
  const comptes = useQuery({ queryKey: ["m10", "accounts"], queryFn: () => api.listAll<Ref>("/api/referentiels/accounts/"), retry: 0 }).data ?? [];

  const provisoire = <Badge tone="warn">{t("ecarts_a2.provisoire")}</Badge>;
  const etrangeres = devises.filter((d) => d.code !== "XAF");
  const promptDate = { name: "date", label: t("ecarts_a2.promptDate") };
  const telecharger = (e: ExportSage) => {
    setDlError(null);
    api.download(`/api/integrations/exports-sage/${e.id}/telecharger/`, e.nom_fichier).catch((err) => setDlError(describeError(err)));
  };

  return (
    <>
      <SectionCard title={t("ecarts_a2.taux.title")} subtitle={t("ecarts_a2.taux.subtitle")}>
        <div className="action-bar-buttons">
          <QuickForm
            title={t("ecarts_a2.taux.ajouter")}
            endpoint="/api/comptabilite/taux-change/"
            fields={[
              { name: "devise", label: t("ecarts_a2.taux.devise"), type: "select", required: true, options: etrangeres.map((d) => ({ value: d.code, label: `${d.code} · ${d.label ?? ""}` })) },
              { name: "date", label: t("ecarts_a2.taux.date"), type: "date", required: true },
              { name: "taux", label: t("ecarts_a2.taux.taux"), type: "number", min: 0, step: "0.000001", required: true },
            ]}
          />
          <QuickForm
            title={t("ecarts_a2.taux.importer")}
            endpoint="/api/comptabilite/taux-change/importer/"
            submitLabel={t("ecarts_a2.taux.importerBtn")}
            fields={[{ name: "contenu", label: t("ecarts_a2.taux.contenu"), type: "textarea", required: true }]}
          />
        </div>
        {situation.isError && <p className="muted">{describeError(situation.error)}</p>}
        {situation.data && (
          <p className="muted">
            {situation.data.devises.map((d) => (
              <span key={d.devise} style={{ marginRight: 12 }}>
                <strong>{d.devise}</strong> {d.taux ?? "—"} {d.date ? `(${d.date})` : ""}{" "}
                {d.a_jour ? <Badge tone="ok">{t("ecarts_a2.taux.aJour")}</Badge> : <Badge tone="err">{t("ecarts_a2.taux.manquant")}</Badge>}
              </span>
            ))}
            {situation.data.provisoire && provisoire}
          </p>
        )}
        <table className="table" data-testid="taux-change">
          <thead>
            <tr>
              <th>{t("ecarts_a2.taux.devise")}</th>
              <th>{t("ecarts_a2.taux.date")}</th>
              <th>{t("ecarts_a2.taux.taux")}</th>
              <th>{t("ecarts_a2.taux.source")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {(taux.data?.results ?? []).map((x) => (
              <tr key={x.id}>
                <td>{x.devise_code}</td>
                <td>{x.date}</td>
                <td className="num">{x.taux}</td>
                <td>{x.source_label}</td>
                <td>
                  {x.est_provisoire ? (
                    <>
                      {provisoire} <ActionBar actions={[{ label: t("ecarts_a2.confirmer"), path: `/api/comptabilite/taux-change/${x.id}/confirmer/`, tone: "ghost" }]} />
                    </>
                  ) : (
                    <Badge tone="ok">{t("ecarts_a2.confirme")}</Badge>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted">{t("ecarts_a2.taux.note")}</p>
      </SectionCard>

      <SectionCard title={t("ecarts_a2.ops.title")} subtitle={t("ecarts_a2.ops.subtitle")}>
        <div className="action-bar-buttons">
          <QuickForm
            title={t("ecarts_a2.ops.ajouter")}
            endpoint="/api/comptabilite/operations-devise/"
            fields={[
              { name: "sens", label: t("ecarts_a2.ops.sens"), type: "select", required: true, options: ["creance", "dette"].map((v) => ({ value: v, label: t(`ecarts_a2.ops.sens_${v}`) })) },
              { name: "partner", label: t("ecarts_a2.ops.tiers"), type: "select", required: true, options: partners.map((p) => ({ value: String(p.id), label: `${p.code} · ${p.name ?? ""}` })) },
              { name: "devise", label: t("ecarts_a2.taux.devise"), type: "select", required: true, options: etrangeres.map((d) => ({ value: String(d.id), label: d.code })) },
              { name: "date", label: t("ecarts_a2.ops.date"), type: "date", required: true },
              { name: "libelle", label: t("ecarts_a2.ops.libelle"), required: true },
              { name: "reference", label: t("ecarts_a2.ops.reference") },
              { name: "montant_devise", label: t("ecarts_a2.ops.montant"), type: "number", min: 0, step: "0.01", required: true },
              {
                name: "compte_contrepartie",
                label: t("ecarts_a2.ops.compte"),
                type: "select",
                required: true,
                options: comptes.filter((c) => [2, 6, 7].includes(c.account_class ?? 0)).map((c) => ({ value: String(c.id), label: `${c.code} · ${c.label ?? ""}` })),
              },
            ]}
          />
          <ActionBar actions={[{ label: t("ecarts_a2.ops.reevaluerTout"), path: "/api/comptabilite/operations-devise/reevaluer-tout/", tone: "ghost", prompt: promptDate }]} />
        </div>
        <div className="table-wrap" tabIndex={0} role="region" aria-label={t("ecarts_a2.ops.title")}>
          <table className="table" data-testid="operations-devise">
            <thead>
              <tr>
                <th>{t("ecarts_a2.ops.code")}</th>
                <th>{t("ecarts_a2.ops.tiers")}</th>
                <th>{t("ecarts_a2.ops.montant")}</th>
                <th>{t("ecarts_a2.ops.cours")}</th>
                <th>{t("ecarts_a2.ops.contreValeur")}</th>
                <th>{t("ecarts_a2.ops.ecarts")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {(ops.data ?? []).map((o) => (
                <tr key={o.id}>
                  <td>
                    {o.code} <span className="muted">· {o.sens_label}</span>
                  </td>
                  <td>
                    {o.partner_name} <span className="muted">· {o.libelle}</span>
                  </td>
                  <td className="num">
                    {o.montant_devise === null ? "—" : formatNumber(Number(o.montant_devise))} {o.devise_code}
                  </td>
                  <td className="num">
                    {o.taux_origine ?? "—"} {o.taux_provisoire && provisoire}
                  </td>
                  <td className="num">{fcfa(o.contre_valeur)}</td>
                  <td>
                    {o.ecart_change !== null && <span>{t("ecarts_a2.ops.realise")} {fcfa(o.ecart_change)} </span>}
                    {o.ecart_latent !== null && o.statut !== "reglee" && (
                      <span className="muted">
                        {t("ecarts_a2.ops.latent")} {fcfa(o.ecart_latent)} ({o.date_reevaluation})
                      </span>
                    )}
                  </td>
                  <td>
                    <Badge tone={o.statut === "reglee" ? "ok" : o.statut === "comptabilisee" ? "brand" : "neutral"}>{o.statut_label}</Badge> {o.move_number ?? ""}
                    {o.statut === "brouillon" && (
                      <ActionBar actions={[{ label: t("ecarts_a2.ops.comptabiliser"), path: `/api/comptabilite/operations-devise/${o.id}/comptabiliser/`, confirm: t("ecarts_a2.ops.confirm") }]} />
                    )}
                    {o.statut === "comptabilisee" && (
                      <ActionBar
                        actions={[
                          { label: t("ecarts_a2.ops.regler"), path: `/api/comptabilite/operations-devise/${o.id}/regler/`, prompt: promptDate },
                          { label: t("ecarts_a2.ops.reevaluer"), path: `/api/comptabilite/operations-devise/${o.id}/reevaluer/`, tone: "ghost", prompt: promptDate },
                        ]}
                      />
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="muted">{t("ecarts_a2.ops.note")}</p>
        <ProvisionsChangeA7 />
      </SectionCard>

      <SectionCard title={t("ecarts_a2.rav.title")} subtitle={t("ecarts_a2.rav.subtitle")}>
        <div className="action-bar-buttons">
          <label className="field">
            <span>{t("ecarts_a2.rav.arrete")}</span>
            <input type="date" value={arrete} onChange={(e) => setArrete(e.target.value)} />
          </label>
          {apercu.data && (
            <p className="muted">
              {t("ecarts_a2.rav.methode")} : <strong>{t(`ecarts_a2.rav.methodes.${apercu.data.methode}`)}</strong> {apercu.data.provisoire && provisoire}
            </p>
          )}
        </div>
        {apercu.isError && <p className="muted">{describeError(apercu.error)}</p>}
        <div className="table-wrap" tabIndex={0} role="region" aria-label={t("ecarts_a2.rav.title")}>
          <table className="table" data-testid="revenu-avancement">
            <thead>
              <tr>
                <th>{t("ecarts_a2.rav.affaire")}</th>
                <th>{t("ecarts_a2.rav.pct")}</th>
                <th>{t("ecarts_a2.rav.contrat")}</th>
                <th>{t("ecarts_a2.rav.revenu")}</th>
                <th>{t("ecarts_a2.rav.facture")}</th>
                <th>{t("ecarts_a2.rav.ecart")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {(apercu.data?.rows ?? []).map((r) => (
                <tr key={r.affaire}>
                  <td>
                    {r.affaire_code} <span className="muted">· {r.affaire_label}</span>
                  </td>
                  {r.erreur ? (
                    <td colSpan={6} className="muted">
                      {r.erreur}
                    </td>
                  ) : (
                    <>
                      <td className="num" title={r.detail}>
                        {r.pct_avancement} %
                      </td>
                      <td className="num">{fcfa(r.ca_reference)}</td>
                      <td className="num">{fcfa(r.revenu_cumule)}</td>
                      <td className="num">{fcfa(r.facture_cumule)}</td>
                      <td className="num">
                        {fcfa(r.ecart)} {r.nature && r.nature !== "aucune" && <Badge tone={r.nature === "produits_a_recevoir" ? "brand" : "warn"}>{t(`ecarts_a2.rav.${r.nature}`)}</Badge>}
                      </td>
                      <td>
                        <ActionBar
                          actions={[
                            {
                              label: t("ecarts_a2.rav.comptabiliser"),
                              path: "/api/comptabilite/reconnaissances-revenu/",
                              body: { affaire: r.affaire, date_arrete: arrete },
                              confirm: t("ecarts_a2.rav.confirm"),
                            },
                          ]}
                        />
                      </td>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {(historique.data?.results ?? []).length > 0 && (
          <table className="table" data-testid="revenu-historique">
            <thead>
              <tr>
                <th>{t("ecarts_a2.rav.code")}</th>
                <th>{t("ecarts_a2.rav.affaire")}</th>
                <th>{t("ecarts_a2.rav.arrete")}</th>
                <th>{t("ecarts_a2.rav.pct")}</th>
                <th>{t("ecarts_a2.rav.ecart")}</th>
                <th>{t("ecarts_a2.rav.ecriture")}</th>
              </tr>
            </thead>
            <tbody>
              {(historique.data?.results ?? []).map((h) => (
                <tr key={h.id}>
                  <td>{h.code}</td>
                  <td>{h.affaire_code}</td>
                  <td>{h.date_arrete}</td>
                  <td className="num">{h.pct_avancement} %</td>
                  <td className="num">{fcfa(h.ecart)}</td>
                  <td>
                    {h.move_number ?? "—"} <Badge tone={h.statut === "en_vigueur" ? "ok" : "neutral"}>{h.statut_label}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="muted">{t("ecarts_a2.rav.note")}</p>
      </SectionCard>

      <SectionCard title={t("ecarts_a2.sage.title")} subtitle={t("ecarts_a2.sage.subtitle")}>
        <div className="action-bar-buttons">
          <QuickForm
            title={t("ecarts_a2.sage.exporter")}
            endpoint="/api/integrations/exports-sage/"
            fields={[
              { name: "date_from", label: t("ecarts_a2.sage.du"), type: "date", required: true },
              { name: "date_to", label: t("ecarts_a2.sage.au"), type: "date", required: true },
              { name: "journal", label: t("ecarts_a2.sage.journal") },
              {
                name: "seulement_nouvelles",
                label: t("ecarts_a2.sage.nouvelles"),
                type: "select",
                defaultValue: "true",
                options: [
                  { value: "true", label: t("ecarts_a2.oui") },
                  { value: "false", label: t("ecarts_a2.non") },
                ],
              },
            ]}
          />
          {gabarit.data && (
            <p className="muted">
              {gabarit.data.label} {gabarit.data.provisoire ? provisoire : <Badge tone="ok">{t("ecarts_a2.confirme")}</Badge>}
            </p>
          )}
        </div>
        {dlError && <p className="error">{dlError}</p>}
        {exports.isError && <p className="muted">{describeError(exports.error)}</p>}
        <table className="table" data-testid="exports-sage">
          <thead>
            <tr>
              <th>{t("ecarts_a2.sage.periode")}</th>
              <th>{t("ecarts_a2.sage.ecritures")}</th>
              <th>{t("ecarts_a2.sage.total")}</th>
              <th>{t("ecarts_a2.sage.empreinte")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {(exports.data?.results ?? []).map((e) => (
              <tr key={e.id}>
                <td>
                  {e.date_from} → {e.date_to} {e.journal && <span className="muted">· {e.journal}</span>}
                </td>
                <td className="num">
                  {e.nb_ecritures} / {e.nb_lignes}
                </td>
                <td className="num">{fcfa(e.total_debit)}</td>
                <td>
                  <code>{e.sha256.slice(0, 12)}</code> {e.gabarit_provisoire && provisoire}
                </td>
                <td>
                  <button type="button" className="btn" onClick={() => telecharger(e)}>
                    {t("ecarts_a2.sage.telecharger")}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted">{t("ecarts_a2.sage.note")}</p>
      </SectionCard>
    </>
  );
}
