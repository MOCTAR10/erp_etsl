import { Info, Lock } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import "../../styles/pages/sections.css";
import { formatNumber } from "../../lib/format";
import { displayName } from "../../lib/people";
import { Badge, Popover } from "../ui";

/**
 * Aides d'affichage des modules métier (règle « zéro code technique ») :
 * empreintes scellées, libellés de référentiel traduits par code, titres sans préfixe de type,
 * nombres décimaux au format de la langue.
 */

/** Empreinte SHA-256 : badge « Scellé » (cadenas), l'empreinte complète en infobulle — jamais le hash en clair. */
export function ScelleBadge({ sha }: { sha: string | null | undefined }) {
  const { t } = useTranslation();
  if (!sha) return <span className="muted">—</span>;
  return (
    <Badge tone="ok" icon={Lock} title={t("premiumModules.scelle.title", { sha })}>
      {t("premiumModules.scelle.label")}
    </Badge>
  );
}

/** Fonction de traduction minimale (compatible avec les `t` locaux des pages). */
type Tr = (key: string, opts?: Record<string, unknown>) => string;

/**
 * Libellé d'une valeur de référentiel servie par l'API (choix Django) traduit côté client par son code :
 * `premiumModules.ref.<champ>.<code>`, avec le libellé serveur en repli (jamais de clé visible).
 */
export function refLabel(t: Tr, champ: string, code: string | null | undefined, libelleServeur?: string | null): string {
  if (!code) return libelleServeur || "—";
  return t(`premiumModules.ref.${champ}.${code}`, { defaultValue: libelleServeur || code });
}

/** Préfixes de type répétés dans les intitulés (« Offre - … », « Convention - … ») : le type est déjà affiché à côté. */
const PREFIXE_TYPE = /^(offre|convention|contrat|opportunit[ée]|march[ée])\s*[-–—:]\s+/i;

/** « Convention - Contrat cadre soudure » → « Contrat cadre soudure » (le titre complet reste en infobulle). */
export function sansPrefixeType(titre: string | null | undefined): string {
  if (!titre) return "—";
  const court = titre.replace(PREFIXE_TYPE, "");
  return court ? court.charAt(0).toLocaleUpperCase("fr") + court.slice(1) : titre;
}

/** Nombre décimal de l'API au format de la langue, décimales utiles seulement : « 2,5 », « 48,67 », « 12 » (jamais « 12.00 »). */
export function nombre(v: string | number | null | undefined, maxDecimales = 2): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = Number(v);
  if (!Number.isFinite(n)) return String(v);
  const arrondi = Number(n.toFixed(maxDecimales));
  const dec = (String(arrondi).split(".")[1] ?? "").length;
  return formatNumber(arrondi, { decimals: Math.min(dec, maxDecimales) });
}

/** Bouton (i) à côté d'un titre : méthode de calcul ou formule, au clic, au lieu d'un paragraphe en texte courant. */
export function InfoFormule({ children, label }: { children: ReactNode; label?: string }) {
  const { t } = useTranslation();
  const nom = label ?? t("premiumModules.methode");
  return (
    <Popover
      label={nom}
      trigger={
        <button type="button" className="icon-btn sm info-formule" aria-label={nom}>
          <Info size={15} aria-hidden />
        </button>
      }
    >
      <p className="info-formule-texte">{children}</p>
    </Popover>
  );
}

/**
 * Nom d'une personne servi par l'API sous forme de chaîne (`*_name`, `*_nom`) : `displayName` de `lib/people`
 * (jamais d'e-mail) ; « — » si absent.
 */
export function nomPersonne(t: Tr, nom: string | null | undefined): string {
  if (!nom || !nom.trim()) return "—";
  const tr: Tr = (key, opts) => t(key, key === "premiumPilotage.people.unknown" ? { defaultValue: "Utilisateur", ...opts } : opts);
  return displayName(tr, { name: nom });
}
