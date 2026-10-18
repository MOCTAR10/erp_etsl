import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatNumber } from "../../lib/format";
import { describeError } from "../../lib/offlineQueue";
import type { Budget, ConsommationsStock, PeriodeRef } from "../../types";
import { DataTable, QuickForm, SectionCard } from "../ui";
import type { Column } from "../ui";

interface AxisRef {
  id: string;
  code: string;
  label: string;
}
interface AnalyticRef {
  id: string;
  axis_code: string;
  code: string;
  label: string;
}

const money = (v: string | null) => (v === null ? "••••••" : `${formatNumber(v)} F`);

/**
 * Saisie budgétaire M11 : création des budgets (V0), lignes mensuelles, révisions R1-R4 et clôtures de gestion,
 * détection des écarts > 10 % et consommations de stock publiées par M5. Les droits et les règles
 * (budget scellé, 4 révisions maximum, double visa) restent contrôlés par l'API.
 */
export function SaisieBudgetaireSection({ fiscalYear, budgets }: { fiscalYear: string; budgets: Budget[] }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [periodeStock, setPeriodeStock] = useState("");
  const [detection, setDetection] = useState<{ ok: boolean; text: string } | null>(null);

  const axes = useQuery({
    queryKey: ["cg-axes"],
    queryFn: () => api.listAll<AxisRef>("/api/referentiels/analytic-axes/"),
    retry: 0,
  });
  const analytiques = useQuery({
    queryKey: ["cg-analytiques"],
    queryFn: () => api.listAll<AnalyticRef>("/api/referentiels/analytic-accounts/"),
    retry: 0,
  });
  const periodes = useQuery({
    queryKey: ["cg-periodes", fiscalYear],
    queryFn: () => api.listAll<PeriodeRef>(`/api/accounting/periods/?fiscal_year=${fiscalYear}`),
    retry: 0,
  });
  const stock = useQuery({
    queryKey: ["cg-consommations-stock", periodeStock],
    queryFn: () => api.get<ConsommationsStock>(`/api/controle-gestion/consommations-stock/${periodeStock ? `?periode=${periodeStock}` : ""}`),
    retry: 0,
  });

  const detecter = useMutation({
    mutationFn: () => api.post<{ analyses: string[] }>("/api/controle-gestion/analyses-ecart/detecter/"),
    onSuccess: (r) => {
      setDetection({ ok: true, text: r.analyses.length ? t("controleGestion.saisie.detectes", { n: r.analyses.length, codes: r.analyses.join(", ") }) : t("controleGestion.saisie.aucunEcart") });
      void qc.invalidateQueries();
    },
    onError: (e) => setDetection({ ok: false, text: describeError(e) }),
  });

  const brouillons = budgets.filter((b) => b.statut === "brouillon");
  const approuves = budgets.filter((b) => b.statut === "approuve");
  const optBudget = (list: Budget[]) => list.map((b) => ({ value: b.id, label: `${b.code} — ${b.label}` }));
  const optPeriode = (periodes.data ?? []).map((p) => ({ value: String(p.id), label: p.start_date.slice(0, 7) }));
  const aujourdhui = new Date().toISOString().slice(0, 10);

  const depotCols: Column<ConsommationsStock["depots"][number] & { id: string }>[] = [
    { key: "periode", header: t("controleGestion.col.periode"), render: (r) => r.periode },
    { key: "depot", header: t("controleGestion.saisie.depot"), render: (r) => r.depot },
    { key: "valeur", header: t("controleGestion.saisie.valeurStock"), num: true, render: (r) => money(r.valeur_stock) },
    { key: "conso", header: t("controleGestion.saisie.consommation"), num: true, render: (r) => money(r.consommation) },
  ];

  return (
    <SectionCard title={t("controleGestion.saisie.title")}>
      <div data-testid="saisie-budgetaire" style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", marginBottom: "0.75rem" }}>
        <QuickForm
          title={t("controleGestion.saisie.nouveauBudget")}
          endpoint="/api/controle-gestion/budgets/"
          transform={(v) => ({ ...v, fiscal_year: fiscalYear })}
          fields={[
            { name: "label", label: t("controleGestion.saisie.libelle"), required: true },
            {
              name: "type_budget",
              label: t("controleGestion.saisie.type"),
              type: "select",
              required: true,
              defaultValue: "charge",
              options: [
                { value: "charge", label: t("controleGestion.budgetTypeCharge") },
                { value: "produit", label: t("controleGestion.budgetTypeProduit") },
              ],
            },
            { name: "axis", label: t("controleGestion.col.axe"), type: "select", options: (axes.data ?? []).map((a) => ({ value: a.id, label: `${a.code} — ${a.label}` })) },
            {
              name: "analytic",
              label: t("controleGestion.saisie.compteAnalytique"),
              type: "select",
              options: (analytiques.data ?? []).map((a) => ({ value: a.id, label: `${a.axis_code} : ${a.code} — ${a.label}` })),
            },
            { name: "montant", label: t("controleGestion.saisie.montantAnnuel"), type: "number", min: 0, step: "0.01", required: true },
            {
              name: "classe_mix",
              label: t("controleGestion.saisie.classeMix"),
              type: "select",
              options: ["A", "B", "C"].map((c) => ({ value: c, label: `Mix ${c}` })),
            },
          ]}
        />
        {brouillons.length > 0 && (
          <QuickForm
            title={t("controleGestion.saisie.nouvelleLigne")}
            endpoint="/api/controle-gestion/budget-lignes/"
            fields={[
              { name: "budget", label: t("controleGestion.col.budget"), type: "select", required: true, options: optBudget(brouillons) },
              { name: "period", label: t("controleGestion.col.periode"), type: "select", required: true, options: optPeriode },
              { name: "montant", label: t("controleGestion.saisie.montantLigne"), type: "number", min: 0, step: "0.01", required: true },
            ]}
          />
        )}
        {approuves.length > 0 && (
          <QuickForm
            title={t("controleGestion.saisie.nouvelleRevision")}
            endpoint="/api/controle-gestion/revisions/"
            fields={[
              { name: "budget", label: t("controleGestion.col.budget"), type: "select", required: true, options: optBudget(approuves) },
              { name: "nouveau_montant", label: t("controleGestion.col.nouveauMontant"), type: "number", min: 0, step: "0.01", required: true },
              { name: "date_revision", label: t("controleGestion.saisie.dateRevision"), type: "date", required: true, defaultValue: aujourdhui },
              { name: "commentaire", label: t("controleGestion.col.commentaire") },
            ]}
          />
        )}
        <QuickForm
          title={t("controleGestion.saisie.nouvelleCloture")}
          endpoint="/api/controle-gestion/clotures/"
          fields={[{ name: "period", label: t("controleGestion.col.periode"), type: "select", required: true, options: optPeriode }]}
        />
        <button type="button" className="btn ghost" disabled={detecter.isPending} onClick={() => detecter.mutate()}>
          {t("controleGestion.saisie.detecter")}
        </button>
      </div>
      {detection && (
        <p className={detection.ok ? "quick-form-ok" : "action-error"} role={detection.ok ? "status" : "alert"}>
          {detection.text}
        </p>
      )}

      <h3 style={{ marginTop: "1rem" }}>{t("controleGestion.saisie.stockTitle")}</h3>
      <div className="field" style={{ maxWidth: "14rem" }}>
        <label htmlFor="cg-periode-stock">{t("controleGestion.saisie.periodeStock")}</label>
        <input id="cg-periode-stock" type="month" value={periodeStock} onChange={(e) => setPeriodeStock(e.target.value)} />
      </div>
      {stock.isError ? null : (stock.data?.depots.length ?? 0) === 0 ? (
        <p className="muted">{t("controleGestion.saisie.stockVide")}</p>
      ) : (
        <>
          <DataTable
            rows={(stock.data?.depots ?? []).map((d) => ({ ...d, id: `${d.periode}-${d.depot}` }))}
            columns={depotCols}
            caption={t("controleGestion.saisie.stockTitle")}
          />
          {(stock.data?.consommations_par_axe.length ?? 0) > 0 && (
            <ul className="muted">
              {stock.data?.consommations_par_axe.map((a) => (
                <li key={a.axe}>
                  {a.axe} : {money(a.valeur)}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </SectionCard>
  );
}
