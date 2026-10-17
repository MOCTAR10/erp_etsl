type Tone = "brand" | "ok" | "warn" | "err" | "accent";

export function ProgressBar({
  value,
  label,
  max = 100,
  tone = "brand",
  className = "",
}: {
  value: number;
  /** Nom accessible (obligatoire : axe aria-progressbar-name). */
  label: string;
  max?: number;
  tone?: Tone;
  className?: string;
}) {
  const pct = max > 0 ? Math.min(100, Math.max(0, (value / max) * 100)) : 0;
  return (
    <div
      className={`progress ${className}`.trim()}
      role="progressbar"
      aria-label={label}
      aria-valuenow={Math.round(pct)}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div className={`progress-fill ${tone}`} style={{ width: `${pct}%` }} />
    </div>
  );
}