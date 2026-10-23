import type { GlobalProvider } from "@ladle/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useLayoutEffect, useState } from "react";
import { MemoryRouter } from "react-router-dom";

import "../src/i18n";
import "@fontsource-variable/inter";
import "@fontsource-variable/plus-jakarta-sans";
import "../src/styles/global.css";
import "../src/styles/primitives.css";
import "../src/styles/pages/shell.css";
import "../src/styles/pages/listes.css";
import "../src/styles/pages/formulaires.css";
import "../src/styles/pages/direction.css";
import { MotionProvider } from "../src/components/Pilot";

/**
 * Enveloppe de chaque histoire : mêmes styles, i18n, requêtes et routeur que l'application.
 * Thème = bouton de Ladle, ou `Histoire.meta = { theme: "dark" }` pour figer une variante sombre.
 * Aucune requête réseau : les requêtes ne sont jamais relancées et les mutations échouent hors ligne.
 */
export const Provider: GlobalProvider = ({ children, globalState, storyMeta }) => {
  const theme = (storyMeta?.theme as string | undefined) ?? globalState.theme;
  useLayoutEffect(() => {
    document.documentElement.setAttribute("data-theme", theme === "dark" ? "dark" : "light");
  }, [theme]);
  const [client] = useState(
    () => new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity }, mutations: { retry: false } } }),
  );
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <MotionProvider>
          <div className="ladle-cadre" style={{ padding: 24, minHeight: "100vh", background: "var(--bg)", color: "var(--text)" }}>
            {children}
          </div>
        </MotionProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
};
