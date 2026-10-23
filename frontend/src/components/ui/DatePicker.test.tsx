import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import i18n from "../../i18n";
import { DatePicker, DateRangePicker, dateToIso, formatIsoDate, isoToDate, parseDateInput } from "./DatePicker";
import type { DateRangeValue } from "./DatePicker";

describe("conversions de dates", () => {
  it("ISO ↔ jj/mm/aaaa sans décalage de fuseau", () => {
    expect(formatIsoDate("2026-10-22")).toBe("22/10/2026");
    expect(formatIsoDate("")).toBe("");
    expect(dateToIso(new Date(2026, 0, 5))).toBe("2026-01-05");
    expect(isoToDate("2026-02-30")).toBeUndefined();
  });
  it("saisie tolérante", () => {
    expect(parseDateInput("22/10/2026")).toBe("2026-10-22");
    expect(parseDateInput("2.1.26")).toBe("2026-01-02");
    expect(parseDateInput("22102026")).toBe("2026-10-22");
    expect(parseDateInput("2026-10-22")).toBe("2026-10-22");
    expect(parseDateInput("  ")).toBe("");
    expect(parseDateInput("31/02/2026")).toBeNull();
    expect(parseDateInput("demain")).toBeNull();
  });
});

describe("<DatePicker />", () => {
  it("compatible .field : libellé associé, saisie clavier → ISO + champ caché pour FormData", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <form aria-label="ged">
        <div className="field">
          <label htmlFor="ged-date">Date du document</label>
          <DatePicker id="ged-date" name="document_date" onChange={onChange} />
        </div>
      </form>,
    );
    const input = screen.getByLabelText("Date du document");
    expect(input).toHaveAttribute("placeholder", "jj/mm/aaaa");
    await user.type(input, "05/03/2026");
    await user.tab();
    expect(onChange).toHaveBeenCalledWith("2026-03-05");
    expect(input).toHaveValue("05/03/2026");
    const data = new FormData(screen.getByRole("form", { name: "ged" }) as HTMLFormElement);
    expect(data.get("document_date")).toBe("2026-03-05");
  });

  it("saisie invalide signalée (aria-invalid + message), valeur inchangée", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<DatePicker aria-label="Échéance" onChange={onChange} />);
    const input = screen.getByRole("textbox", { name: "Échéance" });
    await user.type(input, "45/13/2026");
    await user.tab();
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("alert")).toHaveTextContent("Date invalide");
    expect(onChange).not.toHaveBeenCalled();
  });

  it("calendrier : Alt+↓ ouvre, jour ciblé au clavier, Entrée choisit et ferme", async () => {
    function Ctl() {
      const [v, setV] = useState("2026-10-22");
      return (
        <>
          <DatePicker aria-label="Date" value={v} onChange={setV} />
          <output>{v}</output>
        </>
      );
    }
    const user = userEvent.setup();
    render(<Ctl />);
    screen.getByRole("textbox", { name: "Date" }).focus();
    await user.keyboard("{Alt>}{ArrowDown}{/Alt}");
    const grid = await screen.findByRole("grid");
    expect(grid).toBeInTheDocument();
    expect(screen.getByText(/octobre 2026/i)).toBeInTheDocument();
    await waitFor(() => expect(document.activeElement?.textContent).toBe("22"));
    await user.keyboard("{ArrowRight}{Enter}");
    await waitFor(() => expect(screen.queryByRole("grid")).toBeNull());
    expect(screen.getByText("2026-10-23")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Date" })).toHaveValue("23/10/2026");
  });

  it("anglais : bouton et mois traduits, format jj/mm/aaaa conservé", async () => {
    await i18n.changeLanguage("en");
    const user = userEvent.setup();
    render(<DatePicker aria-label="Due" defaultValue="2026-10-22" />);
    expect(screen.getByRole("textbox", { name: "Due" })).toHaveValue("22/10/2026");
    await user.click(screen.getByRole("button", { name: "Open calendar" }));
    expect(await screen.findByText(/October 2026/)).toBeInTheDocument();
    await i18n.changeLanguage("fr");
  });
});

describe("<DateRangePicker />", () => {
  it("deux clics = une période, panneau fermé, libellé « du – au »", async () => {
    const onChange = vi.fn();
    function Ctl() {
      const [r, setR] = useState<DateRangeValue>({ from: "", to: "" });
      return (
        <DateRangePicker
          aria-label="Période"
          value={r}
          months={1}
          onChange={(v) => {
            setR(v);
            onChange(v);
          }}
        />
      );
    }
    const user = userEvent.setup();
    render(<Ctl />);
    const trigger = screen.getByRole("button", { name: "Période" });
    expect(trigger).toHaveAccessibleDescription("Choisir une période");
    await user.click(trigger);
    await screen.findByRole("grid");
    const days = screen.getAllByRole("gridcell").filter((c) => !c.hasAttribute("data-outside"));
    await user.click(days[4].querySelector("button")!);
    await user.click(days[9].querySelector("button")!);
    await waitFor(() => expect(screen.queryByRole("grid")).toBeNull());
    const last = onChange.mock.calls.at(-1)![0] as DateRangeValue;
    expect(last.from < last.to).toBe(true);
    expect(trigger).toHaveAccessibleDescription(`${formatIsoDate(last.from)} – ${formatIsoDate(last.to)}`);
  });
});
