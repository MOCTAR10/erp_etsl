import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate, formatMoney, formatNumber } from "../../lib/format";
import { EmptyState, QuickForm, SectionCard } from "../ui";

interface Ordre {
  id: string;
  code: string;
  label: string;
  status: string;
}
interface Quant {
  id: string;
  depot: string;
  depot_code: string;
  article: string;
  article_code: string;
  article_label: string;
  lot: string | null;
  lot_code: string | null;
  quantity: string;
}
interface Lot {
  id: string;
  numero_coulee: string;
}
interface Ligne {
  id: string;
  code: string;
  date: string;
  article_code: string;
  article_label: string;
  lot_code: string | null;
  numero_coulee: string;
  depot_code: string | null;
  quantite: string;
  valeur: string | null;
}

/** M3 → M5 : consommation de matière sur l'OF (sortie de stock liée à l'OF, lot / coulée / coût repris). */
export function ConsommationOfSection() {
  const { t } = useTranslation();
  const [ordre, setOrdre] = useState("");
  const ordres = useQuery({
    queryKey: ["a3", "ordres-consommables"],
    queryFn: () => api.listAll<Ordre>("/api/operations/ordres/"),
    retry: 0,
  }).data ?? [];
  const actifs = ordres.filter((o) => o.status === "lance" || o.status === "en_cours");
  const quants = useQuery({
    queryKey: ["a3", "quants"],
    queryFn: () => api.listAll<Quant>("/api/stocks/quants/"),
    retry: 0,
  }).data ?? [];
  const lots = useQuery({ queryKey: ["a3", "lots"], queryFn: () => api.listAll<Lot>("/api/stocks/lots/"), retry: 0 }).data ?? [];
  const coulee = new Map(lots.map((l) => [l.id, l.numero_coulee]));
  const lignes = useQuery({
    queryKey: ["a3", "consommations", ordre],
    queryFn: () => api.get<{ lignes: Ligne[] }>(`/api/operations/ordres/${ordre}/consommations/`),
    enabled: Boolean(ordre),
    retry: 0,
  }).data?.lignes ?? [];
  const dispo = quants.filter((q) => Number(q.quantity) > 0);

  return (
    <SectionCard title={t("ecarts_a3.conso.title")} subtitle={t("ecarts_a3.conso.hint")}>
      <div className="action-bar-buttons">
        <label className="field">
          <span>{t("ecarts_a3.conso.ordre")}</span>
          <select value={ordre} onChange={(e) => setOrdre(e.target.value)} aria-label={t("ecarts_a3.conso.ordre")}>
            <option value="">{t("ecarts_a3.conso.choisir")}</option>
            {actifs.map((o) => (
              <option key={o.id} value={o.id}>
                {o.code} · {o.label}
              </option>
            ))}
          </select>
        </label>
        {ordre && (
          <QuickForm
            title={t("ecarts_a3.conso.consommer")}
            endpoint={`/api/operations/ordres/${ordre}/consommations/`}
            submitLabel={t("ecarts_a3.conso.consommer")}
            fields={[
              {
                name: "quant", label: t("ecarts_a3.conso.stock"), type: "select", required: true,
                options: dispo.map((q) => ({
                  value: q.id,
                  label: `${q.article_code} · ${q.lot_code ?? "—"}${q.lot && coulee.get(q.lot) ? ` (${coulee.get(q.lot)})` : ""} · ${q.depot_code} · ${formatNumber(Number(q.quantity))}`,
                })),
              },
              { name: "quantite", label: t("ecarts_a3.conso.quantite"), type: "number", required: true, min: 0, step: "0.01" },
              { name: "date", label: t("ecarts_a3.conso.date"), type: "date" },
            ]}
            transform={(v) => {
              const q = quants.find((x) => x.id === v.quant);
              return { article: q?.article, depot: q?.depot, lot: q?.lot ?? undefined, quantite: v.quantite, date: v.date };
            }}
          />
        )}
      </div>
      {ordre &&
        (lignes.length === 0 ? (
          <EmptyState label={t("ecarts_a3.conso.vide")} />
        ) : (
          <table className="table" data-testid="consommations-of">
            <thead>
              <tr>
                <th>{t("ecarts_a3.conso.cols.code")}</th>
                <th>{t("ecarts_a3.conso.cols.date")}</th>
                <th>{t("ecarts_a3.conso.cols.article")}</th>
                <th>{t("ecarts_a3.conso.cols.lot")}</th>
                <th>{t("ecarts_a3.conso.cols.coulee")}</th>
                <th>{t("ecarts_a3.conso.cols.depot")}</th>
                <th className="num">{t("ecarts_a3.conso.cols.quantite")}</th>
                <th className="num">{t("ecarts_a3.conso.cols.valeur")}</th>
              </tr>
            </thead>
            <tbody>
              {lignes.map((l) => (
                <tr key={l.id}>
                  <td>{l.code}</td>
                  <td>{formatDate(l.date)}</td>
                  <td>
                    {l.article_code} · {l.article_label}
                  </td>
                  <td>{l.lot_code ?? "—"}</td>
                  <td>{l.numero_coulee || "—"}</td>
                  <td>{l.depot_code ?? "—"}</td>
                  <td className="num">{formatNumber(Number(l.quantite))}</td>
                  <td className="num">{formatMoney(l.valeur)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ))}
    </SectionCard>
  );
}
