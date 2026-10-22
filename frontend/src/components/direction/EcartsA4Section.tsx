import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate } from "../../lib/format";
import { Badge, SectionCard } from "../ui";

interface CapaLigne {
  origine: "qualite" | "hse";
  total: number;
  ouvertes: number;
  echues: number;
  cloturees: number;
  delai_moyen_cloture_jours: string | null;
  efficacite_verifiee: number;
  efficaces: number;
  taux_efficacite_pct: string | null;
}
interface EtatBi {
  fraicheur: { statut: "a_jour" | "en_retard" | "jamais"; rafraichi_le: string | null; age_minutes: number | null; seuil_minutes: number };
  fraicheur_provisoire: boolean;
  capa: CapaLigne[];
  marts: string[];
  staging: string[];
}

const TONE = { a_jour: "ok", en_retard: "err", jamais: "warn" } as const;

/** Écarts a4 — Couche D : fraîcheur de l'ETL horaire, CAPA qualité / HSE, modèles dbt alimentant Superset. */
export function EcartsA4Section() {
  const { t } = useTranslation();
  const etat = useQuery({ queryKey: ["a4", "etat-bi"], queryFn: () => api.get<EtatBi>("/api/analytics/etat-bi/"), retry: 0 });
  const e = etat.data;
  if (!e) return null;
  const f = e.fraicheur;
  return (
    <>
      <SectionCard title={t("ecarts_a4.fraicheur.title")}>
        <p data-testid="fraicheur-bi">
          <Badge tone={TONE[f.statut]}>{t(`ecarts_a4.fraicheur.${f.statut}`)}</Badge>{" "}
          {f.rafraichi_le
            ? t("ecarts_a4.fraicheur.derniere", { date: formatDate(f.rafraichi_le), age: f.age_minutes })
            : t("ecarts_a4.fraicheur.aucune")}{" "}
          · {t("ecarts_a4.fraicheur.seuil", { n: f.seuil_minutes })}{" "}
          {e.fraicheur_provisoire && <Badge tone="warn">{t("ecarts_a4.provisoire")}</Badge>}
        </p>
        <p className="muted">{t("ecarts_a4.fraicheur.hint", { marts: e.marts.length, staging: e.staging.length })}</p>
      </SectionCard>

      {e.capa.length > 0 && (
        <SectionCard title={t("ecarts_a4.capa.title")}>
          <table className="table" data-testid="capa-couche-d">
            <thead>
              <tr>
                <th>{t("ecarts_a4.capa.origine")}</th>
                <th>{t("ecarts_a4.capa.ouvertes")}</th>
                <th>{t("ecarts_a4.capa.echues")}</th>
                <th>{t("ecarts_a4.capa.cloturees")}</th>
                <th>{t("ecarts_a4.capa.delai")}</th>
                <th>{t("ecarts_a4.capa.efficacite")}</th>
              </tr>
            </thead>
            <tbody>
              {e.capa.map((c) => (
                <tr key={c.origine}>
                  <td>{t(`ecarts_a4.capa.${c.origine}`)}</td>
                  <td>{c.ouvertes} / {c.total}</td>
                  <td>{c.echues > 0 ? <Badge tone="err">{c.echues}</Badge> : 0}</td>
                  <td>{c.cloturees}</td>
                  <td>{c.delai_moyen_cloture_jours === null ? "—" : t("ecarts_a4.capa.jours", { n: c.delai_moyen_cloture_jours })}</td>
                  <td>{c.taux_efficacite_pct === null ? "—" : `${c.taux_efficacite_pct} % (${c.efficaces} / ${c.efficacite_verifiee})`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </SectionCard>
      )}
    </>
  );
}
