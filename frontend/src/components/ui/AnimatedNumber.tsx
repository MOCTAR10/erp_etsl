import { animate, useInView, useReducedMotion } from "motion/react";
import { useEffect, useRef } from "react";

import { formatNumber } from "../../lib/format";
import { motionTokens } from "../../theme/tokens";

type Props = {
  value: number;
  /** Format de l'affichage (doit rester stable pour éviter un re-render en boucle). */
  format?: (n: number) => string;
  duration?: number;
};

/** Compteur animé (count-up) — démarre à l'entrée dans le viewport, une seule fois. */
export function AnimatedNumber({ value, format = formatNumber, duration = 0.9 }: Props) {
  const ref = useRef<HTMLSpanElement>(null);
  const prev = useRef(value);
  const formatRef = useRef(format);
  formatRef.current = format;
  const reduce = useReducedMotion();
  const inView = useInView(ref, { once: true });

  useEffect(() => {
    if (reduce) {
      prev.current = value;
      if (ref.current) ref.current.textContent = formatRef.current(value);
      return;
    }
    if (!inView) return;

    const controls = animate(prev.current, value, {
      duration,
      ease: motionTokens.ease.out,
      onUpdate: (v) => {
        if (ref.current) ref.current.textContent = formatRef.current(v);
      },
    });
    return () => {
      prev.current = value;
      controls.stop();
    };
  }, [value, inView, reduce, duration]);

  return (
    <span ref={ref} className="tabular-nums">
      {format(value)}
    </span>
  );
}