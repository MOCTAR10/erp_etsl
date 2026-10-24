import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import i18n from "../../i18n";

import { formatMonth, monthRange, MonthPicker, normalizeMonth, shiftMonth } from "./MonthPicker";

describe("MonthPicker", () => {
  it("normalise, décale et libelle les mois dans la langue de l'interface", () => {
    expect(normalizeMonth("2026-9")).toBe("2026-09");
    expect(normalizeMonth("2026-10-01")).toBe("2026-10");
    expect(normalizeMonth("2026-13")).toBe("");
    expect(shiftMonth("2026-01", -1)).toBe("2025-12");
    expect(formatMonth("2026-10", "fr")).toBe("Octobre 2026");
    expect(formatMonth("2026-10", "en")).toBe("October 2026");
    expect(monthRange("2026-08", "2026-10")).toEqual(["2026-10", "2026-09", "2026-08"]);
  });

  it("liste déroulante du kit, libellée en français, valeur AAAA-MM", async () => {
    await i18n.changeLanguage("fr");
    const onChange = vi.fn();
    render(
      <>
        <label htmlFor="mois">Mois</label>
        <MonthPicker id="mois" value="2026-10" onChange={onChange} min="2026-01" max="2026-12" />
      </>,
    );
    const select = screen.getByLabelText("Mois");
    expect(select).toHaveClass("control");
    expect(screen.getByRole("option", { name: "Octobre 2026" })).toBeInTheDocument();
    await userEvent.selectOptions(select, "2026-09");
    expect(onChange).toHaveBeenCalledWith("2026-09");
  });

  it("garde une valeur hors plage sélectionnable", () => {
    render(<MonthPicker aria-label="Mois" value="2020-03" onChange={() => {}} min="2026-01" max="2026-02" />);
    expect(screen.getByRole("option", { name: "Mars 2020" })).toBeInTheDocument();
  });
});
