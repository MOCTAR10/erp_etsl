import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Sparkline } from "./Sparkline";

describe("<Sparkline />", () => {
  it("expose un résumé textuel accessible (valeurs, dernier, max)", () => {
    render(<Sparkline values={[1, 4, 2, 6]} label="Incidents" />);
    const svg = screen.getByRole("img");
    expect(svg).toHaveAttribute("aria-label", expect.stringContaining("1, 4, 2, 6"));
    expect(svg.getAttribute("aria-label")).toContain("dernier 6");
    expect(svg.getAttribute("aria-label")).toContain("max 6");
  });

  it("ne plante pas sur une série plate, un seul point ou vide", () => {
    const { container, rerender } = render(<Sparkline values={[0, 0, 0]} />);
    expect(container.querySelector("polyline")).not.toBeNull();
    expect(container.innerHTML).not.toContain("NaN");
    rerender(<Sparkline values={[5]} />);
    expect(container.innerHTML).not.toContain("NaN");
    rerender(<Sparkline values={[]} />);
    expect(container.querySelector("svg")).toBeNull();
  });
});
