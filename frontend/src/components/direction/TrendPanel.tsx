import { useId } from "react";
import { useTranslation } from "react-i18next";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis } from "recharts";

import { formatNumber } from "../../lib/format";
import { useThemeMode } from "../../lib/useThemeMode";
import { paletteFor } from "../../theme/tokens";
import type { Tendances } from "../../types";
import { Skeleton } from "../ui";

type SerieKey = keyof Tendances["series"];

/** « 2026-05 » → « mai » (mois court dans la langue de l'interface). */
function moisCourt(m: string, locale: string, withYear = false): string {
  const [y, mo] = m.split("-").map(Number);
  if (!y || !mo) return m;
  return new Date(y, mo - 1, 1).toLocaleDateString(locale, withYear ? { month: "long", year: "numeric" } : { month: "short" });
}

function Serie({ label, values, mois, color, gid }: { label: string; values: number[]; mois: string[]; color: string; gid: string }) {
  const { t, i18n } = useTranslation();
  const mode = useThemeMode();
  const c = paletteFor(mode);
  const last = values[values.length - 1] ?? 0;
  const prev = values[values.length - 2] ?? 0;
  const diff = last - prev;
  const data = values.map((v, i) => ({ m: mois[i] ?? String(i), v }));
  const evolution =
    diff === 0
      ? t("direction2.tendances.stable")
      : t("direction2.tendances.evolution", { signe: diff > 0 ? "+" : "−", n: formatNumber(Math.abs(diff)) });
  return (
    <figure className="dir-trend">
      <figcaption className="dir-trend-head">
        <span className="dir-trend-label">{label}</span>
        <span className="dir-trend-value">{formatNumber(last)}</span>
        <span className="dir-trend-delta">{evolution}</span>
      </figcaption>
      <div className="dir-trend-chart" role="img" aria-label={`${label} : ${values.map((v, i) => `${moisCourt(mois[i] ?? "", i18n.language)} ${v}`).join(", ")}`}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 6, right: 6, left: 6, bottom: 0 }}>
            <defs>
              <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={color} stopOpacity={0.18} />
                <stop offset="100%" stopColor={color} stopOpacity={0} />
              </linearGradient>
            </defs>
            <XAxis
              dataKey="m"
              tickFormatter={(m: string) => moisCourt(m, i18n.language)}
              stroke={c.textMuted}
              fontSize={11}
              tickLine={false}
              axisLine={false}
              interval={0}
              tickMargin={6}
              padding={{ left: 12, right: 12 }}
              height={22}
            />
            <Tooltip
              cursor={{ stroke: c.borderStrong, strokeWidth: 1 }}
              contentStyle={{ background: c.surface, border: `1px solid ${c.border}`, borderRadius: 8, color: c.text, fontSize: 12, padding: "6px 10px" }}
              labelFormatter={(m) => moisCourt(String(m), i18n.language, true)}
              formatter={(v) => [formatNumber(Number(v)), label]}
            />
            <Area type="monotone" dataKey="v" stroke={color} strokeWidth={2} fill={`url(#${gid})`} isAnimationActive={false} dot={false} activeDot={{ r: 3.5, strokeWidth: 0 }} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </figure>
  );
}

/** Tendances sur 6 mois : trois petites courbes sobres (une seule teinte), valeur du mois et évolution sur un mois. */
export function TrendPanel({ data, loading }: { data: Tendances | undefined; loading: boolean }) {
  const { t } = useTranslation();
  const mode = useThemeMode();
  const c = paletteFor(mode);
  const uid = useId().replace(/:/g, "");
  const series: { key: SerieKey; label: string }[] = [
    { key: "documents", label: t("direction.trend.documents") },
    { key: "incidents", label: t("direction.trend.incidents") },
    { key: "ordres_travail", label: t("direction.trend.ordres") },
  ];
  return (
    <section className="card dir-trends" aria-labelledby={`${uid}-title`}>
      <header className="card-header">
        <div>
          <h3 id={`${uid}-title`} className="card-title">
            {t("direction.tendances")}
          </h3>
          <p className="card-sub">{t("direction2.tendances.sub")}</p>
        </div>
      </header>
      <div className="dir-trend-grid">
        {series.map(({ key, label }) => {
          const values = data?.series[key];
          if (loading) return <Skeleton key={key} style={{ height: 120 }} />;
          if (!values || !data) {
            return (
              <div className="dir-trend" key={key}>
                <span className="dir-trend-label">{label}</span>
                <span className="muted">{t("direction.noData")}</span>
              </div>
            );
          }
          return <Serie key={key} label={label} values={values} mois={data.mois} color={c.brand} gid={`${uid}-${key}`} />;
        })}
      </div>
    </section>
  );
}
