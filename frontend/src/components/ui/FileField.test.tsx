import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import "../../i18n";
import { FileField } from "./FileField";

describe("<FileField />", () => {
  it("bouton et mention en français, nom du fichier choisi, « Retirer »", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<FileField aria-label="Relevé bancaire" accept=".sta" name="releve" onChange={onChange} />);
    expect(screen.getByText("Choisir un fichier")).toBeInTheDocument();
    expect(screen.getByText("Aucun fichier choisi")).toBeInTheDocument();

    const input = screen.getByLabelText("Relevé bancaire") as HTMLInputElement;
    expect(input).toHaveAttribute("type", "file");
    expect(input).toHaveAttribute("name", "releve");
    const fichier = new File(["x"], "releve-octobre.sta", { type: "text/plain" });
    await user.upload(input, fichier);
    expect(onChange).toHaveBeenCalledWith(fichier);
    expect(screen.getByText("releve-octobre.sta")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Retirer le fichier" }));
    expect(onChange).toHaveBeenLastCalledWith(null);
    expect(screen.getByText("Aucun fichier choisi")).toBeInTheDocument();
    expect(input).toHaveFocus();
  });
});
