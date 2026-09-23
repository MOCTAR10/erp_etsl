import { describe, expect, it } from "vitest";

import { formatBytes, formatDate, formatNumber } from "./format";

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