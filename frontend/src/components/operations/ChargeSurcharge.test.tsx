import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it } from "vitest";

import i18n from "../../i18n";
import type { ChargeStats } from "../../types";
import { ChargeSurcharge } from "./ChargeSurcharge";

/** Lundi ISO à `n` semaines de la semaine courante. */
function lundi(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7) + n * 7);
  return d.toISOString().slice(0, 10);
}

const stats: ChargeStats = {
  ordres: [],
  totals: { atelier: { calculated: 0, pointed: 0, count: 0 }, chantier: { calculated: 0, pointed: 0, count: 0 } },
  alertes: [
    { scope: "atelier", week: lundi(0), planned_hours: 594, capacity: 120, overload_pct: 395 },
    { scope: "atelier", week: lundi(1), planned_hours: 150, capacity: 120, overload_pct: 25 },
    { scope: "atelier", week: lundi(2), planned_hours: 594, capacity: 120, overload_pct: 395 },
    { scope: "chantier", week: lundi(1), planned_hours: 435, capacity: 200, overload_pct: 117 },
  ],
};

beforeAll(async () => {
  await i18n.changeLanguage("fr");
});

describe("<ChargeSurcharge />", () => {
  it("agrège la surcharge par ressource (une ligne chacune, pic unique) avec une carte de chaleur", () => {
    const { container } = render(<ChargeSurcharge stats={stats} />);
    const lignes = container.querySelectorAll(".charge-ligne");
    expect(lignes).toHaveLength(2);
    expect(lignes[0].textContent).toContain("3 semaines en surcharge");
    expect(lignes[0].textContent).toMatch(/Pic \+395\s%/);
    expect(lignes[1].textContent).toContain("1 semaine en surcharge");
    // Axe commun de 3 semaines : 3 cellules par ressource, niveaux selon le dépassement.
    const cellules = lignes[0].querySelectorAll(".charge-heatmap .charge-cell");
    expect(cellules).toHaveLength(3);
    expect(cellules[0]).toHaveClass("n3");
    expect(cellules[1]).toHaveClass("n1");
    expect(lignes[1].querySelectorAll(".charge-cell.n2")).toHaveLength(1);
    expect(screen.getByTestId("alertes-surcharge")).toBeInTheDocument();
    // Détail semaine par semaine replié par défaut.
    expect(container.querySelector(".overload-list")).toBeNull();
  });

  it("déplie le détail semaine par semaine à la demande", async () => {
    const { container } = render(<ChargeSurcharge stats={stats} />);
    await userEvent.click(screen.getByRole("button", { name: /Voir le détail \(4\)/ }));
    expect(container.querySelectorAll(".overload-list li")).toHaveLength(4);
  });

  it("ne rend rien sans alerte", () => {
    const { container } = render(<ChargeSurcharge stats={{ ...stats, alertes: [] }} />);
    expect(container).toBeEmptyDOMElement();
  });
});
