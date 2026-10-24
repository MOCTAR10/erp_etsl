import { afterEach, describe, expect, it } from "vitest";

import i18n from "../i18n";

import { formatBytes, formatDate, formatDateShort, formatMoney, formatNumber, formatParametre, formatPercent } from "./format";

/** Normalise les espaces insécables pour comparer. */
const sp = (v: string) => v.replace(/\u202f|\u00a0/g, " ");

describe("formatBytes", () => {
  it("renvoie 0 B pour zéro/falsy", () => {
    expect(formatBytes(0)).toBe("0 B");
    expect(formatBytes(undefined as unknown as number)).toBe("0 B");
  });

  it("formate les ordres de grandeur", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(1536)).toBe("1.5 KB");
    expect(formatBytes(35 * 1024 * 1024)).toBe("35.0 MB");
    expect(formatBytes(2 * 1024 ** 3)).toBe("2.0 GB");
  });
});

describe("formatNumber", () => {
  it("masque les valeurs manquantes avec —", () => {
    expect(formatNumber(null)).toBe("—");
    expect(formatNumber(undefined)).toBe("—");
    expect(formatNumber("")).toBe("—");
    expect(formatNumber("abc")).toBe("—");
  });

  it("formate en fr-FR sans décimales", () => {
    expect(formatNumber(1234567).replace(/\u202f|\u00a0/g, " ")).toBe("1 234 567");
    expect(formatNumber("2500").replace(/\u202f|\u00a0/g, " ")).toBe("2 500");
  });
});

describe("formatDate", () => {
  it("formate une date ISO selon la locale", () => {
    const d = formatDate("2026-09-23T10:00:00Z", "fr-FR");
    expect(d).toContain("2026");
    expect(d.toLowerCase()).toContain("sept");
  });
});

describe("formatNumber (décimales)", () => {
  it("applique des décimales fixes à la française", () => {
    expect(formatNumber(0, { decimals: 2 })).toBe("0,00");
    expect(sp(formatNumber(1234.5, { decimals: 1 }))).toBe("1 234,5");
  });
});

describe("formatMoney", () => {
  it("formate en FCFA, espaces insécables", () => {
    expect(sp(formatMoney(25000000))).toBe("25 000 000 FCFA");
    expect(sp(formatMoney("4500000.00"))).toBe("4 500 000 FCFA");
    expect(formatMoney(25000000)).not.toContain(" ");
  });

  it("un seul séparateur de milliers pour les nombres et les montants (A-14)", () => {
    const nombre = formatNumber(323721750);
    const montant = formatMoney(323721750);
    expect(montant.startsWith(nombre)).toBe(true);
    expect(nombre).not.toMatch(/ /);
  });

  it("reste exact, jamais abrégé (y compris les grands montants)", () => {
    expect(sp(formatMoney(1250000000))).toBe("1 250 000 000 FCFA");
    expect(sp(formatMoney(-4500))).toBe("-4 500 FCFA");
  });

  it("laisse passer les montants masqués et absents", () => {
    expect(formatMoney("—")).toBe("—");
    expect(formatMoney("••••••")).toBe("••••••");
    expect(formatMoney(null)).toBe("—");
    expect(formatMoney(undefined)).toBe("—");
    expect(formatMoney("")).toBe("—");
  });
});

describe("formatPercent", () => {
  it("points ou ratio", () => {
    expect(sp(formatPercent(75))).toBe("75 %");
    expect(sp(formatPercent(0.075, { ratio: true, decimals: 1 }))).toBe("7,5 %");
    expect(formatPercent(null)).toBe("—");
  });
});

describe("formatDate (valeurs absentes)", () => {
  it("renvoie — si absente ou invalide", () => {
    expect(formatDate(null)).toBe("—");
    expect(formatDate("pas une date")).toBe("—");
    expect(formatDateShort("2026-09-23T10:00:00Z")).toBe("23/09/2026");
  });
});

describe("formats numériques en anglais", () => {
  afterEach(async () => {
    await i18n.changeLanguage("fr");
  });

  it("suivent la langue de l'interface (montant toujours exact, en FCFA)", async () => {
    await i18n.changeLanguage("en");
    expect(sp(formatMoney(3337000000))).toBe("3,337,000,000 FCFA");
    expect(formatPercent(81.3, { decimals: 1 })).toBe("81.3%");
    expect(formatNumber(1234.5, { decimals: 1 })).toBe("1,234.5");
  });

  it("restent à la française en français", async () => {
    await i18n.changeLanguage("fr");
    expect(sp(formatMoney(3337000000))).toBe("3 337 000 000 FCFA");
    expect(sp(formatPercent(81.3, { decimals: 1 }))).toBe("81,3 %");
  });
});

describe("formatParametre", () => {
  it("rend lisibles les valeurs brutes de l'API", async () => {
    await i18n.changeLanguage("fr");
    expect(sp(formatParametre("30.00", "jours"))).toBe("30 jours");
    expect(sp(formatParametre("1.00", "jours"))).toBe("1 jour");
    expect(sp(formatParametre("50000000.00", "FCFA"))).toBe("50 000 000 FCFA");
    expect(sp(formatParametre("15000.00", "FCFA/h"))).toBe("15 000 FCFA/h");
    expect(sp(formatParametre("90.00", "%"))).toBe("90 %");
    expect(formatParametre("411700.00", "compte")).toBe("411700");
    expect(formatParametre("1.00", "0/1")).toBe("Oui");
    expect(formatParametre("0.00", "0 / 1")).toBe("Non");
    expect(sp(formatParametre("2.50", "heures"))).toBe("2,5 heures");
    expect(sp(formatParametre("1.00", "cycles/an"))).toBe("1 cycle/an");
    expect(sp(formatParametre("12.00", "unités"))).toBe("12 unités");
    expect(formatParametre(null, "jours")).toBe("—");
  });
});
