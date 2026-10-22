/// <reference types="node" />
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

// Garde-fou accessibilité : les couples texte/fond de la charte tiennent WCAG AA (4.5:1, texte courant et badges 12px).
const css = readFileSync(join(process.cwd(), "src/styles/global.css"), "utf-8");

function vars(selector: string): Record<string, string> {
  const start = css.indexOf(`${selector} {`);
  const body = css.slice(start, css.indexOf("}", start));
  const out: Record<string, string> = {};
  for (const m of body.matchAll(/--([\w-]+):\s*([^;]+);/g)) out[m[1]] = m[2].trim();
  return out;
}

type Rgb = [number, number, number];

function parse(color: string, under?: Rgb): Rgb {
  const hex = color.match(/^#([0-9a-f]{6})$/i);
  if (hex) return [0, 2, 4].map((i) => parseInt(hex[1].slice(i, i + 2), 16)) as Rgb;
  const rgba = color.match(/^rgba\((\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\)$/);
  if (rgba && under) {
    const a = Number(rgba[4]);
    return [1, 2, 3].map((i, k) => Math.round(Number(rgba[i]) * a + under[k] * (1 - a))) as Rgb;
  }
  throw new Error(`couleur non gérée : ${color}`);
}

function luminance([r, g, b]: Rgb): number {
  const f = (v: number) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
}

function ratio(a: Rgb, b: Rgb): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

describe("contraste WCAG AA de la charte", () => {
  for (const [mode, selector] of [
    ["light", ":root"],
    ["dark", ':root[data-theme="dark"]'],
  ] as const) {
    it(`${mode} : textes et badges >= 4.5:1`, () => {
      const v = { ...vars(":root"), ...vars(selector) };
      const surface = parse(v.surface);
      const pairs: Array<[string, string]> = [
        ["text", "surface"],
        ["text-muted", "surface"],
        ["text-muted", "surface-2"],
        ["text-muted", "bg"],
        ["brand", "surface"],
        ["accent", "surface"],
        ["ok-text", "ok-soft"],
        ["warn-text", "warn-soft"],
        ["err-text", "err-soft"],
        ["brand", "brand-soft"],
        ["steel", "steel-soft"],
        ["on-brand", "brand"],
        ["info-text", "info-soft"],
        ["text", "surface-2"],
      ];
      const failures = pairs
        .map(([fg, bg]) => [fg, bg, ratio(parse(v[fg], surface), parse(v[bg], surface))] as const)
        .filter(([, , r]) => r < 4.5)
        .map(([fg, bg, r]) => `${fg} sur ${bg} : ${r.toFixed(2)}`);
      expect(failures).toEqual([]);
    });

    it(`${mode} : texte discret et bordure de champ (non-texte) >= 3:1 / visibles`, () => {
      const v = { ...vars(":root"), ...vars(selector) };
      const surface = parse(v.surface);
      expect(ratio(parse(v["text-subtle"], surface), surface)).toBeGreaterThanOrEqual(3);
      expect(ratio(parse(v["border-strong"], surface), surface)).toBeGreaterThan(1.3);
    });
  }
});
