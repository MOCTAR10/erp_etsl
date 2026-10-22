/// <reference types="node" />
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { palette } from "./tokens";

// `css: false` dans vitest.config.ts : un import `?raw` renverrait une chaine vide.
const css = readFileSync(join(process.cwd(), "src/styles/global.css"), "utf-8");

/** Extrait les custom properties du premier bloc dont le sélecteur est `selector`. */
function vars(selector: string): Record<string, string> {
  const start = css.indexOf(`${selector} {`);
  expect(start, `bloc ${selector} introuvable`).toBeGreaterThanOrEqual(0);
  const body = css.slice(start, css.indexOf("}", start));
  const out: Record<string, string> = {};
  for (const m of body.matchAll(/--([\w-]+):\s*([^;]+);/g)) out[m[1]] = m[2].trim();
  return out;
}

const kebab = (k: string) => k.replace(/[A-Z0-9]/g, (c) => `-${c.toLowerCase()}`);

describe("charte ETSL : tokens.ts <-> global.css", () => {
  for (const [mode, selector] of [
    ["light", ":root"],
    ["dark", ':root[data-theme="dark"]'],
  ] as const) {
    it(`palette ${mode} synchronisée avec le CSS`, () => {
      const cssVars = vars(selector);
      const diffs: string[] = [];
      for (const [key, value] of Object.entries(palette[mode])) {
        const name = kebab(key);
        // `ring` : en CSS c'est un box-shadow complet, pas une couleur — non comparable.
        if (key === "ring") continue;
        if (!(name in cssVars)) {
          diffs.push(`${name}: absent du CSS`);
          continue;
        }
        if (cssVars[name].toLowerCase() !== value.toLowerCase()) {
          diffs.push(`${name}: css=${cssVars[name]} ts=${value}`);
        }
      }
      expect(diffs).toEqual([]);
    });
  }

  it("échelles d'espacement, de rayons et d'ombres présentes en CSS", () => {
    const root = vars(":root");
    for (const name of ["space-1", "space-2", "space-4", "space-6", "space-8", "radius-xs", "radius-lg", "radius-full", "shadow-xs", "shadow-md", "shadow-pop", "fs-h1", "fs-kpi", "fs-body", "control-h"]) {
      expect(root, name).toHaveProperty(name);
    }
    expect(root["radius-lg"]).toBe("12px");
  });

  it("la couleur d'accent est le rouge du logo (pas l'ancien orange)", () => {
    expect(palette.light.accent).toBe("#d4142a");
    expect(palette.light.brand).toBe("#12308f");
  });
});
