import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate, formatDateShort, formatMoney, formatNumber } from "../../lib/format";
import { describeError } from "../../lib/offlineQueue";
import { SectionActions } from "../sections/SectionActions";
import { ActionBar, Badge, DataTable, DatePicker, QuickForm, SectionCard } from "../ui";
import type { Column } from "../ui";
import { actionsColumn } from "../ui/DataTable";
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

const fcfa = (v: string | null | undefined) => formatMoney(v);
/** Cours de change lisible : « 655,957 » (décimales utiles seulement, pas de « 655.957000 »). */
const cours = (v: string | null | undefined) =>
  v === null || v === undefined || v === "" ? "—" : Number(v).toLocaleString("fr-FR", { maximumFractionDigits: 6 });

/** Écarts a2 : cours de change et opérations en devise, revenu à l'avancement, export des écritures vers SAGE. */
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

  const provisoire = (
    <Badge tone="warn" title={t("ecarts_a2.provisoire")}>
      {t("revueR3.provisoire")}
    </Badge>
  );
  const etrangeres = devises.filter((d) => d.code !== "XAF");
  const promptDate = { name: "date", label: t("ecarts_a2.promptDate") };
  const telecharger = (e: ExportSage) => {
    setDlError(null);
    api.download(`/api/integrations/exports-sage/${e.id}/telecharger/`, e.nom_fichier).catch((err) => setDlError(describeError(err)));
  };
  const actionsHeader = <span className="sr-only">{t("ui.actions")}</span>;

  const colsTaux: Column<Taux>[] = [
    { key: "devise", header: t("ecarts_a2.taux.devise"), render: (x) => x.devise_code, sortValue: (x) => x.devise_code },
    { key: "date", header: t("ecarts_a2.taux.date"), render: (x) => formatDate(x.date), sortValue: (x) => x.date },
    { key: "taux", header: t("ecarts_a2.taux.taux"), num: true, render: (x) => cours(x.taux) },
    { key: "source", header: t("ecarts_a2.taux.source"), render: (x) => x.source_label },
    {
      key: "statut",
      header: t("revueR3.statut"),
      render: (x) => (x.est_provisoire ? provisoire : <Badge tone="ok">{t("ecarts_a2.confirme")}</Badge>),
    },
    actionsColumn<Taux>(t("ui.actions"), (x) =>
      x.est_provisoire ? [{ label: t("ecarts_a2.confirmer"), path: `/api/comptabilite/taux-change/${x.id}/confirmer/`, tone: "ghost" }] : [],
    ),
  ];

  const colsOps: Column<Operation>[] = [
    {
      key: "code",
      header: t("ecarts_a2.ops.code"),
      render: (o) => (
        <>
          {o.code} <span className="muted">· {o.sens_label}</span>
        </>
      ),
      sortValue: (o) => o.code,
    },
    {
      key: "tiers",
      header: t("ecarts_a2.ops.tiers"),
      render: (o) => (
        <>
          {o.partner_name} <span className="muted">· {o.libelle}</span>
        </>
      ),
    },
    {
      key: "montant",
      header: t("ecarts_a2.ops.montant"),
      num: true,
      render: (o) => `${o.montant_devise === null ? "—" : formatNumber(o.montant_devise, { decimals: 2 })} ${o.devise_code}`,
    },
    {
      key: "cours",
      header: t("ecarts_a2.ops.cours"),
      num: true,
      render: (o) => (
        <>
          {cours(o.taux_origine)} {o.taux_provisoire && provisoire}
        </>
      ),
    },
    { key: "contreValeur", header: t("ecarts_a2.ops.contreValeur"), num: true, render: (o) => fcfa(o.contre_valeur), sortValue: (o) => Number(o.contre_valeur ?? 0) },
    {
      key: "ecarts",
      header: t("ecarts_a2.ops.ecarts"),
      render: (o) => (
        <>
          {o.ecart_change !== null && <span>{t("ecarts_a2.ops.realise")} {fcfa(o.ecart_change)} </span>}
          {o.ecart_latent !== null && o.statut !== "reglee" && (
            <span className="muted">
              {t("ecarts_a2.ops.latent")} {fcfa(o.ecart_latent)} ({formatDate(o.date_reevaluation)})
            </span>
          )}
        </>
      ),
    },
    {
      key: "statut",
      header: actionsHeader,
      render: (o) => (
        <>
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
        </>
      ),
    },
  ];

  type LigneRav = LigneAvancement & { id: string };
  const colsRav: Column<LigneRav>[] = [
    {
      key: "affaire",
      header: t("ecarts_a2.rav.affaire"),
      render: (r) => (
        <>
          {r.affaire_code}
          <span className="cell-sub">{r.affaire_label}</span>
        </>
      ),
      sortValue: (r) => r.affaire_code,
      width: 260,
    },
    {
      key: "pct",
      header: t("ecarts_a2.rav.pct"),
      num: true,
      render: (r) => (r.erreur ? <span className="muted">{r.erreur}</span> : <span title={r.detail}>{formatNumber(r.pct_avancement, { decimals: 2 })} %</span>),
    },
    { key: "contrat", header: t("ecarts_a2.rav.contrat"), num: true, render: (r) => (r.erreur ? "" : fcfa(r.ca_reference)) },
    { key: "revenu", header: t("ecarts_a2.rav.revenu"), num: true, render: (r) => (r.erreur ? "" : fcfa(r.revenu_cumule)) },
    { key: "facture", header: t("ecarts_a2.rav.facture"), num: true, render: (r) => (r.erreur ? "" : fcfa(r.facture_cumule)) },
    {
      key: "ecart",
      header: t("ecarts_a2.rav.ecart"),
      num: true,
      render: (r) =>
        r.erreur ? (
          ""
        ) : (
          <>
            <span className="r3-nowrap">{fcfa(r.ecart)}</span>
            {r.nature && r.nature !== "aucune" && <span className="cell-sub">{t(`ecarts_a2.rav.${r.nature}`)}</span>}
          </>
        ),
    },
    actionsColumn<LigneRav>(t("ui.actions"), (r) =>
      r.erreur || !Number(r.ecart)
        ? []
        : [
            {
              label: t("ecarts_a2.rav.comptabiliser"),
              path: "/api/comptabilite/reconnaissances-revenu/",
              body: { affaire: r.affaire, date_arrete: arrete },
              confirm: t("ecarts_a2.rav.confirm"),
              tone: "ghost",
            },
          ],
    ),
  ];

  const colsHisto: Column<Reconnaissance>[] = [
    { key: "code", header: t("ecarts_a2.rav.code"), render: (h) => h.code, sortValue: (h) => h.code },
    { key: "affaire", header: t("ecarts_a2.rav.affaire"), render: (h) => h.affaire_code },
    { key: "arrete", header: t("ecarts_a2.rav.arrete"), render: (h) => formatDate(h.date_arrete), sortValue: (h) => h.date_arrete },
    { key: "pct", header: t("ecarts_a2.rav.pct"), num: true, render: (h) => `${formatNumber(h.pct_avancement, { decimals: 2 })} %` },
    { key: "ecart", header: t("ecarts_a2.rav.ecart"), num: true, render: (h) => fcfa(h.ecart) },
    {
      key: "ecriture",
      header: t("ecarts_a2.rav.ecriture"),
      render: (h) => (
        <>
          {h.move_number ?? "—"} <Badge tone={h.statut === "en_vigueur" ? "ok" : "neutral"}>{h.statut_label}</Badge>
        </>
      ),
    },
  ];

  const colsSage: Column<ExportSage>[] = [
    {
      key: "periode",
      header: t("ecarts_a2.sage.periode"),
      render: (x) => (
        <>
          {formatDateShort(x.date_from)} → {formatDateShort(x.date_to)} {x.journal && <span className="muted">· {x.journal}</span>}
        </>
      ),
      sortValue: (x) => x.date_from,
    },
    { key: "ecritures", header: t("ecarts_a2.sage.ecritures"), num: true, render: (x) => `${formatNumber(x.nb_ecritures)} / ${formatNumber(x.nb_lignes)}` },
    { key: "total", header: t("ecarts_a2.sage.total"), num: true, render: (x) => fcfa(x.total_debit) },
    {
      key: "empreinte",
      header: t("ecarts_a2.sage.empreinte"),
      render: (x) => (
        <>
          <code>{x.sha256.slice(0, 12)}</code> {x.gabarit_provisoire && provisoire}
        </>
      ),
    },
    {
      key: "actions",
      header: actionsHeader,
      render: (x) => (
        <button type="button" className="btn ghost sm" onClick={() => telecharger(x)}>
          {t("ecarts_a2.sage.telecharger")}
        </button>
      ),
    },
  ];

  return (
    <>
      <SectionCard
        title={t("ecarts_a2.taux.title")}
        subtitle={t("ecarts_a2.taux.subtitle")}
        actions={
          <SectionActions>
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
          </SectionActions>
        }
      >
        {situation.isError && <p className="muted">{describeError(situation.error)}</p>}
        {situation.data && (
          <div className="r3-toolbar">
            {situation.data.devises.map((d) => (
              <span key={d.devise} className="r3-badges">
                <strong>{d.devise}</strong> {cours(d.taux)} <span className="muted">{d.date ? formatDate(d.date) : ""}</span>
                {d.a_jour ? <Badge tone="ok">{t("ecarts_a2.taux.aJour")}</Badge> : <Badge tone="err">{t("ecarts_a2.taux.manquant")}</Badge>}
              </span>
            ))}
            {situation.data.provisoire && provisoire}
          </div>
        )}
        <div data-testid="taux-change">
          <DataTable caption={t("ecarts_a2.taux.title")} columns={colsTaux} rows={taux.data?.results ?? []} />
        </div>
        <p className="muted">{t("ecarts_a2.taux.note")}</p>
      </SectionCard>

      <SectionCard
        title={t("ecarts_a2.ops.title")}
        subtitle={t("ecarts_a2.ops.subtitle")}
        actions={
          <SectionActions>
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
          </SectionActions>
        }
      >
        <div data-testid="operations-devise">
          <DataTable caption={t("ecarts_a2.ops.title")} columns={colsOps} rows={ops.data ?? []} />
        </div>
        <p className="muted">{t("ecarts_a2.ops.note")}</p>
        <ProvisionsChangeA7 />
      </SectionCard>

      <SectionCard title={t("ecarts_a2.rav.title")} subtitle={t("ecarts_a2.rav.subtitle")}>
        <div className="r3-toolbar">
          <div className="field">
            <label htmlFor="a2-arrete">{t("ecarts_a2.rav.arrete")}</label>
            <DatePicker id="a2-arrete" value={arrete} onChange={(v) => v && setArrete(v)} />
          </div>
          {apercu.data && (
            <p className="muted">
              {t("ecarts_a2.rav.methode")} : <strong>{t(`ecarts_a2.rav.methodes.${apercu.data.methode}`)}</strong> {apercu.data.provisoire && provisoire}
            </p>
          )}
        </div>
        {apercu.isError && <p className="muted">{describeError(apercu.error)}</p>}
        <div data-testid="revenu-avancement">
          <DataTable caption={t("ecarts_a2.rav.title")} columns={colsRav} rows={(apercu.data?.rows ?? []).map((r) => ({ ...r, id: r.affaire }))} />
        </div>
        {(historique.data?.results ?? []).length > 0 && (
          <div data-testid="revenu-historique">
            <DataTable caption={t("tableaux.comptabilite.historiqueRevenu")} columns={colsHisto} rows={historique.data?.results ?? []} />
          </div>
        )}
        <p className="muted">{t("ecarts_a2.rav.note")}</p>
      </SectionCard>

      <SectionCard
        title={t("ecarts_a2.sage.title")}
        subtitle={t("ecarts_a2.sage.subtitle")}
        actions={
          <SectionActions>
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
          </SectionActions>
        }
      >
        {gabarit.data && (
          <p className="muted">
            {gabarit.data.label} {gabarit.data.provisoire ? provisoire : <Badge tone="ok">{t("ecarts_a2.confirme")}</Badge>}
          </p>
        )}
        {dlError && <p className="error">{dlError}</p>}
        {exports.isError && <p className="muted">{describeError(exports.error)}</p>}
        <div data-testid="exports-sage">
          <DataTable caption={t("ecarts_a2.sage.title")} columns={colsSage} rows={exports.data?.results ?? []} />
        </div>
        <p className="muted">{t("ecarts_a2.sage.note")}</p>
      </SectionCard>
    </>
  );
}
