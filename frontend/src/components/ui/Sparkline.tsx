import { useId } from "react";

type Props = {
  values: number[];
  /** Couleur CSS (variable de la charte par défaut). */
  color?: string;
  height?: number;
  label?: string;
};

/**
 * Mini-courbe de tendance (SVG pur, sans dépendance) : aire dégradée + point sur la dernière valeur.
 * Accessible : `role="img"` avec un résumé textuel (min / max / dernière valeur).
 */
export function Sparkline({ values, color = "var(--brand)", height = 44, label }: Props) {
  const gid = useId().replace(/:/g, "");
  const w = 160;
  const n = values.length;
  if (n === 0) return null;
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const span = max - min || 1;
  const pad = 4;
  const x = (i: number) => (n === 1 ? w / 2 : pad + (i * (w - pad * 2)) / (n - 1));
  const y = (v: number) => height - pad - ((v - min) / span) * (height - pad * 2);
  const pts = values.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`);
  const area = `M ${x(0).toFixed(1)},${height} L ${pts.join(" L ")} L ${x(n - 1).toFixed(1)},${height} Z`;
  const last = values[n - 1];
  const summary = `${label ?? "Tendance"} : ${values.join(", ")} (dernier ${last}, max ${Math.max(...values)})`;

  return (
    <svg
      className="sparkline"
      viewBox={`0 0 ${w} ${height}`}
      preserveAspectRatio="none"
      width="100%"
      height={height}
      role="img"
      aria-label={summary}
    >
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.28" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${gid})`} />
      <polyline points={pts.join(" ")} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
      <circle cx={x(n - 1)} cy={y(last)} r="3" fill={color} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}
