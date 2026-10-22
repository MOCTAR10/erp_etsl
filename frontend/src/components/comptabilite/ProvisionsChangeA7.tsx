import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatNumber } from "../../lib/format";
import { Badge } from "../ui";

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

const fcfa = (v: string | null) => (v === null || v === "" ? "—" : `${formatNumber(Number(v))} F`);

/** Lot a7 : provisions pour perte de change latente (Dr 697 / Cr 499), dotées par « Réévaluer tout » et
 * contre-passées au calcul suivant. Paramètre provisoire DEVISE_PROVISION_PERTE (Comptabilité → Paramètres). */
export function ProvisionsChangeA7() {
  const { t } = useTranslation();
  const q = useQuery({
    queryKey: ["a7", "provisions-change"],
    queryFn: () => api.get<{ results: Provision[]; provisoire?: boolean }>("/api/comptabilite/provisions-change/"),
    retry: 0,
  });
  const rows = q.data?.results ?? [];
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
        <div className="table-wrap" tabIndex={0} role="region" aria-label={t("ecarts_a7.provision.title")}>
          <table className="table">
            <thead>
              <tr>
                <th>{t("ecarts_a7.provision.date")}</th>
                <th>{t("ecarts_a7.provision.pertes")}</th>
                <th>{t("ecarts_a7.provision.gains")}</th>
                <th>{t("ecarts_a7.provision.montant")}</th>
                <th>{t("ecarts_a7.provision.statut")}</th>
                <th>{t("ecarts_a7.provision.ecritures")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((p) => (
                <tr key={p.id}>
                  <td>{p.date_cloture}</td>
                  <td>{fcfa(p.perte_latente)}</td>
                  <td>{fcfa(p.gain_latent)}</td>
                  <td>{fcfa(p.montant)}</td>
                  <td>
                    <Badge tone={p.statut === "active" ? "warn" : "neutral"}>{p.statut_label}</Badge>
                    {p.date_contre_passation && <span className="muted"> {p.date_contre_passation}</span>}
                  </td>
                  <td>
                    {p.move_number ?? "—"}
                    {p.move_contre_passation_number && ` / ${p.move_contre_passation_number}`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
