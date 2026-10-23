import { defineConfig } from "vite";

// Vite de Ladle : il ajoute lui-même le plugin React ; aucune dépendance au backend (pas de proxy /api).
export default defineConfig({
  base: process.env.LADLE_BASE || "/",
  // Pas de dossier public : ni service worker ni manifeste de la PWA dans le catalogue.
  publicDir: false,
});
