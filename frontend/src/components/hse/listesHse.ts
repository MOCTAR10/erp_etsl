import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";

export interface ValeurListeHse {
  id: string;
  categorie: string;
  code: string;
  libelle: string;
  actif: boolean;
  gaz_obligatoire: boolean;
  dangereux: boolean;
  est_provisoire: boolean;
}

/** Valeurs par défaut (avant chargement, ou si la liste paramétrée est illisible) : libellés i18n existants. */
const DEFAUTS: Record<string, { codes: string[]; prefix: string }> = {
  type_permis: { codes: ["chaud", "hauteur", "levage", "confine", "atex", "froid", "electrique", "fouille", "chimique"], prefix: "hse.permis_types" },
  type_incident: {
    codes: ["quasi_accident", "incident", "accident", "blessure", "depart_feu", "pollution", "deversement", "dommage_materiel", "situation_dangereuse"],
    prefix: "hse.incident_types",
  },
  type_dechet: { codes: ["huiles", "solvants", "batteries", "peintures", "dib", "deee", "metaux", "papier_carton"], prefix: "hse.dechet_types" },
};

/** Listes HSE paramétrables (écarts M7 §9.2) : types de permis, d'incidents, de déchets — options de formulaire. */
export function useListeHse(categorie: "type_permis" | "type_incident" | "type_dechet") {
  const { t, i18n } = useTranslation();
  const q = useQuery({
    queryKey: ["hse-listes", categorie],
    queryFn: () => api.listAll<ValeurListeHse>(`/api/hse/listes/?categorie=${categorie}&actifs=1`),
    retry: 0,
    staleTime: 60_000,
  });
  const d = DEFAUTS[categorie];
  if (!q.data || q.data.length === 0) return d.codes.map((v) => ({ value: v, label: t(`${d.prefix}.${v}`) }));
  // Libellé paramétré par ETSL (français) ; traduction i18n en anglais quand elle existe.
  const fr = (i18n.language ?? "fr").startsWith("fr");
  return q.data.map((v) => ({ value: v.code, label: fr ? v.libelle : t(`${d.prefix}.${v.code}`, { defaultValue: v.libelle }) }));
}
