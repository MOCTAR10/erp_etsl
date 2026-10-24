import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { EMPTY, formatDate, formatMoney, formatPercent } from "../../lib/format";
import { describeError } from "../../lib/offlineQueue";
import { Badge, DatePicker, SectionCard } from "../ui";

interface Declaration {
  id: string;
  code: string;
  type: string;
  type_label: string;
  periode_debut: string;
  periode_fin: string;
  nb_salaries: number;
  total_brut: string;
  total_salarial: string;
  total_patronal: string;
  provisoire: boolean;
  avertissement: string;
}
type Declarations = { type: string; periode_debut: string; periode_fin: string };

/** Taux en points (« 8.57 ») → « 8,57 % » ; « — » si absent. */
const pourcent = (v: string | null) => (v === null ? EMPTY : formatPercent(v, { decimals: Number.isInteger(Number(v)) ? 0 : 2 }));

interface Reporting {
  annee: number;
  effectif_fin: number;
  entrees: number;
  sorties: number;
  turnover_pct: string | null;
  jours_absence: number;
  absenteisme_pct: string | null;
}

/** Déclarations CNSS / CNAMGS / IRPP (2460) / DADS générées depuis les bulletins + indicateurs RH. */
export function DeclarationsSection() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const decls = useQuery({
    queryKey: ["declarations"],
    queryFn: () => api.listAll<Declaration>("/api/rh-paie/declarations/"),
    retry: 0,
  });
  const annee = new Date().getFullYear();
  const reporting = useQuery({
    queryKey: ["reporting-rh", annee],
    queryFn: () => api.get<Reporting>(`/api/rh-paie/reporting/?annee=${annee}`),
    retry: 0,
  });
  const [form, setForm] = useState<Declarations>({ type: "cnss", periode_debut: "", periode_fin: "" });
  const [error, setError] = useState<string | null>(null);
  const generer = useMutation({
    mutationFn: (body: Declarations) => api.post("/api/rh-paie/declarations/generer/", body),
    onSuccess: () => {
      setError(null);
      void qc.invalidateQueries({ queryKey: ["declarations"] });
    },
    onError: (e) => setError(describeError(e)),
  });

  if (decls.isError) return null; // hors cercle paie : la section n'apparaît pas
  const r = reporting.data;
  const lignes = decls.data ?? [];
  // Un seul bandeau pour les avertissements « provisoire » (souvent identiques d'une déclaration à l'autre).
  const avertissements = [...new Set(lignes.filter((d) => d.provisoire && d.avertissement).map((d) => d.avertissement))];

  return (
    <SectionCard title={t("declarations.title")}>
      <p className="muted">{t("declarations.hint")}</p>
      {r && (
        <p className="muted" data-testid="reporting-rh">
          {t("revueKit.fin.reportingRh", {
            annee: r.annee,
            effectif: r.effectif_fin,
            entrees: r.entrees,
            sorties: r.sorties,
            turnover: pourcent(r.turnover_pct),
            absence: r.jours_absence,
            absenteisme: pourcent(r.absenteisme_pct),
          })}
        </p>
      )}
      <form
        className="r3-toolbar"
        onSubmit={(e) => {
          e.preventDefault();
          generer.mutate(form);
        }}
      >
        <div className="field">
          <label htmlFor="decl-type">{t("declarations.type")}</label>
          <select id="decl-type" className="control" value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}>
            <option value="cnss">CNSS</option>
            <option value="cnamgs">CNAMGS</option>
            <option value="irpp">IRPP (2460)</option>
            <option value="dads">DADS</option>
            <option value="fnh">FNH</option>
            <option value="cfp">CFP</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="decl-du">{t("declarations.du")}</label>
          <DatePicker id="decl-du" required value={form.periode_debut} onChange={(v) => setForm((f) => ({ ...f, periode_debut: v }))} />
        </div>
        <div className="field">
          <label htmlFor="decl-au">{t("declarations.au")}</label>
          <DatePicker id="decl-au" required value={form.periode_fin} onChange={(v) => setForm((f) => ({ ...f, periode_fin: v }))} />
        </div>
        <button className="btn primary" type="submit" disabled={generer.isPending}>
          {t("declarations.generer")}
        </button>
      </form>
      {error && (
        <p className="action-error" role="alert">
          {error}
        </p>
      )}
      {avertissements.length > 0 && (
        <div className="banner warn" role="note">
          <AlertTriangle size={18} aria-hidden />
          <div className="banner-body">
            {avertissements.map((a) => (
              <span key={a} className="banner-text">
                {a}
              </span>
            ))}
          </div>
        </div>
      )}
      {lignes.length > 0 && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>{t("revueKit.fin.declaration")}</th>
                <th className="num">{t("revueKit.fin.brut")}</th>
                <th className="num">{t("revueKit.fin.salarial")}</th>
                <th className="num">{t("revueKit.fin.patronal")}</th>
                <th className="num">
                  <span className="sr-only">{t("ui.actions")}</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {lignes.map((d) => (
                <tr key={d.id}>
                  <td>
                    <strong>{d.code}</strong> · {d.type_label}{" "}
                    {d.provisoire && (
                      <Badge tone="warn" title={d.avertissement || undefined}>
                        {t("revueKit.fin.provisoire")}
                      </Badge>
                    )}
                    <div className="cell-sub">
                      {formatDate(d.periode_debut)} → {formatDate(d.periode_fin)} · {t("revueKit.fin.salaries", { count: d.nb_salaries })}
                    </div>
                  </td>
                  <td className="num cell-nowrap">{formatMoney(d.total_brut)}</td>
                  <td className="num cell-nowrap">{formatMoney(d.total_salarial)}</td>
                  <td className="num cell-nowrap">{formatMoney(d.total_patronal)}</td>
                  <td className="num">
                    <button type="button" className="btn ghost sm" onClick={() => void api.download(`/api/rh-paie/declarations/${d.id}/fichier/`, `${d.code}_${d.type}.csv`)}>
                      {t("virements.telecharger")}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </SectionCard>
  );
}
