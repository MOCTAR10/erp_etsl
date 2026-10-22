import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { Badge, SectionCard } from "../ui";

interface FicheTerrain {
  id: string;
  code: string;
  titre: string;
  risques: string;
  consignes: string;
  epi: string;
  urgence: string;
  version: number;
  provisoire: boolean;
}

const CLE_LOCALE = "etls.fiches-securite";

function lireCopie(): FicheTerrain[] {
  try {
    return JSON.parse(localStorage.getItem(CLE_LOCALE) ?? "[]") as FicheTerrain[];
  } catch {
    return [];
  }
}

/**
 * Fiches sécurité sur smartphone (CDC M7-08) : le service worker garde une copie de la liste publiée et une copie
 * locale sert de secours hors ligne (lecture seule, aucune donnée sensible).
 */
export function FichesSecuriteTerrain() {
  const { t } = useTranslation();
  const q = useQuery({
    queryKey: ["terrain", "fiches-securite"],
    queryFn: async () => {
      const fiches = await api.listAll<FicheTerrain>("/api/hse/fiches-securite/?publiees=1");
      try {
        localStorage.setItem(CLE_LOCALE, JSON.stringify(fiches));
      } catch {
        /* stockage indisponible : la copie du service worker suffit */
      }
      return fiches;
    },
    retry: 0,
  });
  const fiches = q.data ?? (q.isError ? lireCopie() : []);
  if (fiches.length === 0) return null;
  const m = "ecarts_m6m7.fiches";
  return (
    <SectionCard title={t(`${m}.terrain`)}>
      <div data-testid="fiches-terrain">
        {q.isError && <p className="muted">{t(`${m}.copieLocale`)}</p>}
        {fiches.map((f) => (
          <details key={f.id}>
            <summary>
              <strong>{f.titre}</strong> <span className="muted">v{f.version}</span>{" "}
              {f.provisoire && <Badge tone="warn">{t("ecarts_m6m7.provisoire")}</Badge>}
            </summary>
            {f.risques && <p><strong>{t(`${m}.risques`)}</strong> : {f.risques}</p>}
            <p style={{ whiteSpace: "pre-line" }}><strong>{t(`${m}.consignes`)}</strong> : {f.consignes}</p>
            {f.epi && <p><strong>{t(`${m}.epi`)}</strong> : {f.epi}</p>}
            {f.urgence && <p><strong>{t(`${m}.urgence`)}</strong> : {f.urgence}</p>}
          </details>
        ))}
      </div>
    </SectionCard>
  );
}
