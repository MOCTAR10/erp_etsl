import { render } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { Kpi } from "./Kpi";

// jsdom n'a pas d'IntersectionObserver (compteur animé : useInView de motion).
beforeAll(() => {
  vi.stubGlobal(
    "IntersectionObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
      takeRecords() {
        return [];
      }
    },
  );
});

describe("<Kpi />", () => {
  it("montant : nombre et unité insécables, coupure permise seulement entre les deux", () => {
    const { container } = render(<Kpi label="Engagé" value="25000000" kind="money" />);
    const value = container.querySelector(".kpi-value")!;
    expect(value.textContent).toBe("25 000 000 FCFA");
    expect(value.querySelector(".ui-kpi-num")?.textContent).toBe("25 000 000");
    expect(value.querySelector(".ui-kpi-unit")?.textContent).toBe("FCFA");
    expect(value.querySelector("wbr")).not.toBeNull();
  });

  it("montant numérique (compteur animé) et montant masqué « — »", () => {
    const { container, rerender } = render(<Kpi label="Engagé" value={1500000} kind="money" />);
    expect(container.querySelector(".kpi-value")?.textContent).toBe("1 500 000 FCFA");
    rerender(<Kpi label="Engagé" value="—" kind="money" />);
    expect(container.querySelector(".kpi-value")?.textContent).toBe("—");
    expect(container.querySelector(".ui-kpi-unit")).toBeNull();
  });

  it("nombre simple : pas d'unité", () => {
    const { container } = render(<Kpi label="Bons" value={4} />);
    expect(container.querySelector(".kpi-value")?.textContent).toBe("4");
  });
});
