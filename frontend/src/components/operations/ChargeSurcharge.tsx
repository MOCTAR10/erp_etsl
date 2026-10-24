import { useState, type CSSProperties } from "react";
import { useTranslation } from "react-i18next";

import "../../styles/pages/sections.css";
import { formatDate, formatNumber, formatPercent } from "../../lib/format";
import type { ChargeAlerte, ChargeStats } from "../../types";
import { Badge, SectionCard } from "../ui";

/** Dépassement (en %) à partir duquel l'alerte passe au rouge : charge au moins triple de la capacité. */
const SURCHARGE_FORTE = 200;
const JOUR_MS = 86_400_000;

/** Niveau de la cellule de la carte de chaleur : 0 = pas de surcharge, 1 = < +50 %, 2 = jusqu'à +200 %, 3 = au-delà. */
const niveau = (pct: number | undefined) => (pct === undefined ? 0 : pct >= SURCHARGE_FORTE ? 3 : pct >= 50 ? 2 : 1);

/** Lundi ISO « AAAA-MM-JJ » → horodatage UTC (les semaines de l'API sont des lundis). */
const jourUtc = (iso: string) => Date.parse(`${iso.slice(0, 10)}T00:00:00Z`);

/**
 * Surcharge de capacité agrégée par ressource (atelier, chantier) : une ligne par ressource avec le nombre de
 * semaines en surcharge, le pic et la prochaine semaine concernée, et une carte de chaleur semaines × ressources.
 * Le détail semaine par semaine reste accessible (« Voir le détail »).
 */
export function ChargeSurcharge({ stats }: { stats: ChargeStats }) {
  const { t } = useTranslation();
  const [detail, setDetail] = useState(false);
  const alertes = stats.alertes ?? [];
  if (alertes.length === 0) return null;
  // Semaine en cours comprise : seuil = lundi de la semaine dernière (comme la liste détaillée).
  const lundi = new Date();
  lundi.setDate(lundi.getDate() - 7);
  const seuil = lundi.toISOString().slice(0, 10);

  // Axe commun des semaines (de la première à la dernière alerte, pas de 7 jours).
  const debut = Math.min(...alertes.map((a) => jourUtc(a.week)));
  const fin = Math.max(...alertes.map((a) => jourUtc(a.week)));
  const semaines: string[] = [];
  for (let d = debut; d <= fin; d += 7 * JOUR_MS) semaines.push(new Date(d).toISOString().slice(0, 10));
  const courante = semaines.find((w) => w >= seuil);

  const ressources = (["atelier", "chantier"] as const)
    .map((scope) => {
      const liste = alertes.filter((a) => a.scope === scope);
      const parSemaine = new Map(liste.map((a) => [a.week.slice(0, 10), a]));
      const pic = liste.reduce<ChargeAlerte | null>((m, a) => (!m || a.overload_pct > m.overload_pct ? a : m), null);
      const prochaine = liste.filter((a) => a.week >= seuil).sort((x, y) => x.week.localeCompare(y.week))[0] ?? null;
      return { scope, liste, parSemaine, pic, prochaine };
    })
    .filter((r) => r.liste.length > 0);

  // Détail : semaines à venir d'abord, puis les semaines passées ; chronologique dans chaque groupe.
  const triees = [...alertes].sort((a, b) => {
    const pa = a.week >= seuil ? 0 : 1;
    const pb = b.week >= seuil ? 0 : 1;
    return pa - pb || a.week.localeCompare(b.week) || a.scope.localeCompare(b.scope);
  });
  const charge = (a: ChargeAlerte) => (a.capacity > 0 ? a.planned_hours / a.capacity : 1);
  const maxCharge = Math.max(1, ...alertes.map(charge));
  const repere = Math.round((1 / maxCharge) * 100);

  return (
    <SectionCard
      title={`${t("operations.surcharge")} · ${alertes.length}`}
      subtitle={t("premiumModules.charge.sousTitre", { debut: formatDate(semaines[0]), fin: formatDate(semaines[semaines.length - 1]) })}
      actions={
        <button type="button" className="btn ghost sm" aria-expanded={detail} onClick={() => setDetail((v) => !v)}>
          {detail ? t("revueR2.operations.alertesReduire") : t("premiumModules.charge.voirDetail", { count: alertes.length })}
        </button>
      }
    >
      <div className="charge-resume" data-testid="alertes-surcharge" style={{ "--semaines": semaines.length } as CSSProperties}>
        {ressources.map((r) => {
          const fort = (r.pic?.overload_pct ?? 0) >= SURCHARGE_FORTE;
          return (
            <div className="charge-ligne" key={r.scope}>
              <div className="charge-ressource">
                <strong>{t(`operations.${r.scope}`)}</strong>
                <span className="cell-sub">
                  {t("premiumModules.charge.semaines", { count: r.liste.length })}
                  {r.prochaine ? ` · ${t("premiumModules.charge.prochaine", { date: formatDate(r.prochaine.week) })}` : ""}
                </span>
              </div>
              <div
                className="charge-heatmap"
                role="img"
                aria-label={t("premiumModules.charge.carteAria", {
                  ressource: t(`operations.${r.scope}`),
                  count: r.liste.length,
                  pic: r.pic ? formatPercent(r.pic.overload_pct) : "—",
                })}
              >
                {semaines.map((w) => {
                  const a = r.parSemaine.get(w);
                  return (
                    <span
                      key={w}
                      className={`charge-cell n${niveau(a?.overload_pct)}${w === courante ? " is-now" : ""}`}
                      title={
                        a
                          ? `${t("listes.operations.surchargeHint", { date: formatDate(w) })} · ${formatNumber(a.planned_hours)} h / ${formatNumber(a.capacity)} h · +${formatPercent(a.overload_pct)}`
                          : t("premiumModules.charge.sansSurcharge", { date: formatDate(w) })
                      }
                    />
                  );
                })}
              </div>
              {r.pic ? (
                <Badge tone={fort ? "err" : "warn"} title={t("listes.operations.surchargeHint", { date: formatDate(r.pic.week) })}>
                  {t("premiumModules.charge.pic", { pct: formatPercent(r.pic.overload_pct) })}
                </Badge>
              ) : null}
            </div>
          );
        })}
        <div className="charge-legende" aria-hidden>
          <span>
            <i className="charge-cell n0" /> {t("premiumModules.charge.legende0")}
          </span>
          <span>
            <i className="charge-cell n1" /> {t("premiumModules.charge.legende1")}
          </span>
          <span>
            <i className="charge-cell n2" /> {t("premiumModules.charge.legende2")}
          </span>
          <span>
            <i className="charge-cell n3" /> {t("premiumModules.charge.legende3")}
          </span>
          <span>
            <i className="charge-cell n0 is-now" /> {t("premiumModules.charge.legendeNow")}
          </span>
        </div>
      </div>
      {detail ? (
        <ul className="overload-list">
          {triees.map((a) => {
            const largeur = Math.max(4, Math.round((charge(a) / maxCharge) * 100));
            const fort = a.overload_pct >= SURCHARGE_FORTE;
            return (
              <li key={`${a.scope}-${a.week}`}>
                <span>
                  <strong>{t(`operations.${a.scope}`)}</strong>
                  <span className="cell-sub">{t("listes.operations.surchargeHint", { date: formatDate(a.week) })}</span>
                </span>
                <span className={`overload-bar${fort ? " err" : ""}`} aria-hidden>
                  <span style={{ width: `${largeur}%` }} />
                  <span className="overload-cap" style={{ left: `${repere}%` }} />
                </span>
                <span className="overload-hours">
                  {formatNumber(a.planned_hours)} h / {formatNumber(a.capacity)} h
                </span>
                <Badge tone={fort ? "err" : "warn"}>+{formatPercent(a.overload_pct)}</Badge>
              </li>
            );
          })}
        </ul>
      ) : null}
    </SectionCard>
  );
}
