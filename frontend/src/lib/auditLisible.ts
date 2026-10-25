import { formatDate, formatDateTime } from "./format";

/**
 * Piste d'audit lisible (vague 3, A03) : valeurs brutes du journal (null, horodatage ISO, UUID) rendues pour un
 * lecteur métier, champs techniques écartés, lignes répétées regroupées.
 */

const ISO_DATETIME = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const TECHNIQUES = new Set(["id", "pk", "created_at", "updated_at", "modified_at", "search_vector", "extracted_text"]);
const MAX = 60;

/** Champ sans intérêt pour un lecteur : clé étrangère brute (`*_id`), horodatage technique, index de recherche. */
export const champTechnique = (champ: string) => TECHNIQUES.has(champ) || champ.endsWith("_id");

/** Champs modifiés à afficher (techniques retirés). */
export const champsVisibles = (champs: string[] | undefined) => (champs ?? []).filter((c) => !champTechnique(c));

/** Valeur lisible : vide → « — », ISO → date française, booléen → Oui / Non, UUID → référence courte. */
export function valeurLisible(v: unknown, oui = "Oui", non = "Non"): string {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "boolean") return v ? oui : non;
  if (typeof v === "string") {
    if (ISO_DATETIME.test(v)) return formatDateTime(v);
    if (ISO_DATE.test(v)) return formatDate(v);
    if (UUID.test(v)) return `#${v.slice(0, 8)}`;
    return v.length > MAX ? `${v.slice(0, MAX)}…` : v;
  }
  if (typeof v === "number") return String(v);
  const s = JSON.stringify(v);
  return s.length > MAX ? `${s.slice(0, MAX)}…` : s;
}

interface LigneAudit {
  id: string;
  user_email: string | null;
  action: string;
  object_type: string;
  created_at: string;
  detail: { champs?: string[] };
}

/** Clé de regroupement : même auteur, même action, même type d'objet, mêmes champs, même minute. */
const cle = (a: LigneAudit) =>
  [a.user_email ?? "", a.action, a.object_type, a.created_at.slice(0, 16), champsVisibles(a.detail.champs).join(",")].join("|");

/** Regroupe les lignes CONSÉCUTIVES identiques ; `repetitions` = nombre de lignes fusionnées (1 si seule). */
export function regrouperAudit<T extends LigneAudit>(rows: T[]): (T & { repetitions: number })[] {
  const out: (T & { repetitions: number })[] = [];
  for (const r of rows) {
    const prev = out[out.length - 1];
    if (prev && cle(prev) === cle(r)) prev.repetitions += 1;
    else out.push({ ...r, repetitions: 1 });
  }
  return out;
}
