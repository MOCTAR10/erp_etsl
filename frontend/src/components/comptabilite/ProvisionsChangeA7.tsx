import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate, formatMoney } from "../../lib/format";
import { Badge, DataTable } from "../ui";
import type { Column } from "../ui";

interface Provision {
  id: string;
  date_cloture: string;
  perte_latente: string | null;
  gain_latent: string | null;
  montant: string | null;
  operations: number;
  statut: "active" | "contre_passee";
  statut_label: string;
  move_number: string | null;
  move_contre_passation_number: string | null;
  date_contre_passation: string | null;
}

const fcfa = (v: string | null) => formatMoney(v);

/** Lot a7 : provisions pour perte de change latente (Dr 697 / Cr 499), dotées par « Réévaluer tout » et
 * contre-passées au calcul suivant (activation paramétrable dans Comptabilité → Paramètres). */
export function ProvisionsChangeA7() {
  const { t } = useTranslation();
  const q = useQuery({
    queryKey: ["a7", "provisions-change"],
    queryFn: () => api.get<{ results: Provision[]; provisoire?: boolean }>("/api/comptabilite/provisions-change/"),
    retry: 0,
  });
  const rows = q.data?.results ?? [];
  const columns: Column<Provision>[] = [
    { key: "date", header: t("ecarts_a7.provision.date"), render: (p) => formatDate(p.date_cloture), sortValue: (p) => p.date_cloture },
    { key: "pertes", header: t("ecarts_a7.provision.pertes"), num: true, render: (p) => fcfa(p.perte_latente) },
    { key: "gains", header: t("ecarts_a7.provision.gains"), num: true, render: (p) => fcfa(p.gain_latent) },
    { key: "montant", header: t("ecarts_a7.provision.montant"), num: true, render: (p) => fcfa(p.montant) },
    {
      key: "statut",
      header: t("ecarts_a7.provision.statut"),
      render: (p) => (
        <>
          <Badge tone={p.statut === "active" ? "warn" : "neutral"}>{p.statut_label}</Badge>
          {p.date_contre_passation && <span className="muted"> {formatDate(p.date_contre_passation)}</span>}
        </>
      ),
    },
    {
      key: "ecritures",
      header: t("ecarts_a7.provision.ecritures"),
      render: (p) => `${p.move_number ?? "—"}${p.move_contre_passation_number ? ` / ${p.move_contre_passation_number}` : ""}`,
    },
  ];
  return (
    <div className="a7-provisions">
      <h4>
        {t("ecarts_a7.provision.title")}{" "}
        {q.data?.provisoire && <Badge tone="warn">{t("ecarts_a7.provisoire")}</Badge>}
      </h4>
      <p className="muted">{t("ecarts_a7.provision.subtitle")}</p>
      {rows.length === 0 ? (
        <p className="muted">{t("ecarts_a7.provision.vide")}</p>
      ) : (
        <DataTable caption={t("ecarts_a7.provision.title")} columns={columns} rows={rows} />
      )}
    </div>
  );
}
