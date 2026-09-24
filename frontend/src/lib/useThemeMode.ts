import { useEffect, useState } from "react";

import { readThemeMode } from "../theme/tokens";
import type { ThemeMode } from "../theme/tokens";

/** Suit le mode sombre/clair courant (attribut data-theme) — pour les charts. */
export function useThemeMode(): ThemeMode {
  const [mode, setMode] = useState<ThemeMode>(readThemeMode);
  useEffect(() => {
    const el = document.documentElement;
    const observer = new MutationObserver(() => setMode(readThemeMode()));
    observer.observe(el, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  }, []);
  return mode;
}