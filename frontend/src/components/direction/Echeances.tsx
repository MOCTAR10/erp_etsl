import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../../api/client";
import { formatDate, formatNumber } from "../../lib/format";
import type { AlerteEcheanceItem, AlertesAgregees } from "../../types";
import { Badge } from "../ui";
import type { AlerteCal } from "./types";

/** Paliers d'échéance, du plus urgent au plus lointain. */
const BANDES = ["expiree", "j0", "j15", "j30", "j60", "j90"] as const;
const BANDE_TONE: Record<string, "ok" | "warn" | "err" | "neutral"> = {
  expiree: "err",
  j0: "err",
  j15: "err",
  j30: "warn",
  j60: "warn",
  j90: "neutral",
};

interface Ligne {
  id: string;
  type: string;
  libelle: string;
  date: string | null;
  jours: number;
  bande: string;
}

const VISIBLES = 8;

/** Libellé lisible d'un type d'échéance (jamais l'identifiant technique). */
function useTypeLabel() {
  const { t, i18n } = useTranslation();
  return (type: string) => {
    const key = `direction2.echeances.types.${type}`;
    if (i18n.exists(key)) return t(key);
    const cal = `ecarts_cd.calendrier.types.${type}`;
    if (i18n.exists(cal)) return t(cal);
    const txt = type.replace(/_/g, " ");
    return txt.charAt(0).toUpperCase() + txt.slice(1);
  };
}

/** Alertes d'échéance transverses : répartition par palier et prochaines échéances (contrats, RH, juridique, calendrier). */
export function EcheancesSection({ a }: { a: AlertesAgregees }) {
  const { t } = useTranslation();
  const typeLabel = useTypeLabel();
  const [tout, setTout] = useState(false);
  const calendrier = useQuery({
    queryKey: ["cd", "calendrier"],
    queryFn: () => api.get<{ items: AlerteCal[]; paliers: number[] }>("/api/analytics/alertes-calendaires/"),
    retry: 0,
  });

  const items: AlerteEcheanceItem[] = [
    ...a.documents,
    ...(a.juridique.conventions ?? []),
    ...(a.juridique.cautions ?? []),
    ...(a.juridique.assurances ?? []),
    ...((a.juridique as unknown as { jalons?: AlerteEcheanceItem[] }).jalons ?? []),
    ...a.rh,
    ...(a.qualite ?? []),
    ...(a.maintenance ?? []),
  ];
  const lignes: Ligne[] = [
    ...items
      .filter((e) => e.jours !== null)
      .map((e, i) => ({ id: `a-${e.type}-${e.code ?? i}-${i}`, type: e.type, libelle: e.libelle, date: e.date_echeance, jours: e.jours ?? 0, bande: e.bande })),
    ...(calendrier.data?.items ?? []).map((e, i) => ({ id: `c-${e.type}-${e.code}-${i}`, type: e.type, libelle: e.libelle, date: e.date_echeance, jours: e.jours, bande: e.bande })),
  ].sort((x, y) => x.jours - y.jours);

  const total = BANDES.reduce((s, b) => s + (a.compteurs[b] ?? 0), 0);
  const affichees = tout ? lignes : lignes.slice(0, VISIBLES);

  return (
    <section id="echeances" className="dir-section" aria-labelledby="dir-echeances-title">
      <h3 id="dir-echeances-title" className="section-title">
        {t("direction2.echeances.titre")}
        <span className="dir-count">{formatNumber(total)}</span>
      </h3>
      <div className="card dir-echeances">
        <div className="dir-bands" data-testid="alertes-calendaires">
          <div className="dir-bands-bar" role="img" aria-label={BANDES.map((b) => `${t(`juridique.bande.${b}`)} ${a.compteurs[b] ?? 0}`).join(", ")}>
            {total > 0
              ? BANDES.map((b) =>
                  a.compteurs[b] ? <span key={b} className={`dir-band tone-${BANDE_TONE[b]}`} style={{ flexGrow: a.compteurs[b] }} /> : null,
                )
              : null}
          </div>
          <ul className="dir-bands-legend">
            {BANDES.map((b) => (
              <li key={b}>
                <span className={`dir-band-dot tone-${BANDE_TONE[b]}`} aria-hidden />
                <span>{t(`juridique.bande.${b}`)}</span>
                <strong className="num">{formatNumber(a.compteurs[b] ?? 0)}</strong>
              </li>
            ))}
          </ul>
        </div>

        {lignes.length === 0 ? (
          <p className="muted">{t("direction.aucuneEcheance")}</p>
        ) : (
          <ol className="dir-due-list">
            {affichees.map((l) => {
              const tone = l.jours < 0 ? "err" : l.jours <= 15 ? "err" : l.jours <= 60 ? "warn" : "neutral";
              return (
                <li key={l.id} className="dir-due">
                  <span className={`dir-due-days tone-${tone}`}>
                    {l.jours < 0 ? t("direction2.echeances.retard", { n: formatNumber(-l.jours) }) : l.jours === 0 ? t("direction2.echeances.aujourdhui") : t("direction2.echeances.dans", { n: formatNumber(l.jours) })}
                  </span>
                  <span className="dir-due-body">
                    <span className="dir-due-title">{l.libelle}</span>
                    <span className="dir-due-meta">
                      {typeLabel(l.type)} · {formatDate(l.date)}
                    </span>
                  </span>
                  <Badge tone={BANDE_TONE[l.bande] ?? "neutral"}>{t(`juridique.bande.${l.bande}`)}</Badge>
                </li>
              );
            })}
          </ol>
        )}
        {lignes.length > VISIBLES ? (
          <button type="button" className="btn ghost sm dir-more" aria-expanded={tout} onClick={() => setTout((v) => !v)}>
            {tout ? t("direction2.attention.moins") : t("direction2.echeances.toutes", { count: lignes.length })}
          </button>
        ) : null}
      </div>
    </section>
  );
}
