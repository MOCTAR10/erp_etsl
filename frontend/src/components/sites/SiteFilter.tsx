import { useQuery } from "@tanstack/react-query";
import { useId } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";

/** Site ETSL (EX-G-03, `referentiels.Site`) : liste provisoire paramétrable dans Administration. */
export interface SiteEtsl {
  id: number;
  code: string;
  libelle: string;
  type_site: string;
  type_site_label: string;
  ville: string;
  alias: string;
  actif: boolean;
  statut_valeur: string;
  est_provisoire: boolean;
  confirme_par_email: string | null;
  confirme_le: string | null;
}

export function useSites() {
  return useQuery({
    queryKey: ["sites-etsl"],
    queryFn: () => api.listAll<SiteEtsl>("/api/referentiels/sites/"),
    retry: 0,
    staleTime: 60_000,
  });
}

/** Critère d'URL du filtre par site (`site_etsl=<id>`, filtre multicritère du serveur), vide = tous les sites. */
export function siteQuery(site: string): string {
  return site ? `site_etsl=${encodeURIComponent(site)}` : "";
}

/** Options de sélection d'un site (formulaires de création) : sites actifs. */
export function useSiteOptions() {
  return (useSites().data ?? []).filter((s) => s.actif).map((s) => ({ value: String(s.id), label: `${s.code} — ${s.libelle}` }));
}

/** Filtre « Site » d'une liste métier (EX-G-03) ; masqué tant qu'aucun site n'est défini. */
export function SiteFilter({ value, onChange }: { value: string; onChange: (next: string) => void }) {
  const { t } = useTranslation();
  const id = useId();
  const sites = useSites().data ?? [];
  if (sites.length === 0) return null;
  return (
    <div className="field site-filter" style={{ maxWidth: 320 }}>
      <label htmlFor={id}>{t("ecarts_a5.site")}</label>
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">{t("ecarts_a5.tousSites")}</option>
        {sites
          .filter((s) => s.actif || String(s.id) === value)
          .map((s) => (
            <option key={s.id} value={String(s.id)}>
              {s.code} — {s.libelle}
            </option>
          ))}
      </select>
    </div>
  );
}
