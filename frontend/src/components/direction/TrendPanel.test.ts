import { describe, expect, it } from "vitest";

import { trendDomainMax } from "./TrendPanel";

describe("trendDomainMax", () => {
  it("série nulle : ligne de base plate (domaine [0, 1]), jamais de pic artificiel", () => {
    expect(trendDomainMax([0, 0, 0])).toBe(1);
    expect(trendDomainMax([])).toBe(1);
  });

  it("garde de l'air au-dessus du maximum", () => {
    expect(trendDomainMax([2, 5, 4])).toBeCloseTo(5.75);
  });
});
