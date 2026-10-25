import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import "../../i18n";
import { SectionNav } from "./SectionNav";

type Callback = (entries: Array<{ target: Element; isIntersecting: boolean }>) => void;
let observers: Array<{ cb: Callback; targets: Element[] }> = [];

beforeEach(() => {
  observers = [];
  vi.stubGlobal(
    "IntersectionObserver",
    class {
      cb: Callback;
      targets: Element[] = [];
      constructor(cb: Callback) {
        this.cb = cb;
        observers.push(this);
      }
      observe(el: Element) {
        this.targets.push(el);
      }
      unobserve() {}
      disconnect() {}
      takeRecords() {
        return [];
      }
    },
  );
});
afterEach(() => vi.unstubAllGlobals());

const Page = ({ onNavigate }: { onNavigate?: (id: string) => void }) => (
  <div>
    <SectionNav
      onNavigate={onNavigate}
      items={[
        { id: "synthese", label: "Synthèse" },
        { id: "factures", label: "Factures", count: 4 },
        { id: "clotures", label: "Clôtures" },
      ]}
    />
    <section id="synthese">Synthèse</section>
    <section id="factures">Factures</section>
    <section id="clotures">Clôtures</section>
  </div>
);

describe("<SectionNav />", () => {
  it("nav nommée, une ancre par section, la première active (aria-current), compteur", () => {
    render(<Page />);
    const nav = screen.getByRole("navigation", { name: "Sections de la page" });
    const links = Array.from(nav.querySelectorAll("a"));
    expect(links.map((a) => a.getAttribute("href"))).toEqual(["#synthese", "#factures", "#clotures"]);
    expect(screen.getByRole("link", { name: "Synthèse" })).toHaveAttribute("aria-current", "location");
    expect(screen.getByRole("link", { name: /Factures/ })).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("link", { name: /Factures/ })).toHaveTextContent("4");
  });

  it("surligne la section qui entre dans la bande haute au défilement (IntersectionObserver)", () => {
    render(<Page />);
    const io = observers[0];
    expect(io.targets.map((t) => t.id)).toEqual(["synthese", "factures", "clotures"]);
    act(() =>
      io.cb([
        { target: io.targets[0], isIntersecting: false },
        { target: io.targets[1], isIntersecting: true },
      ]),
    );
    expect(screen.getByRole("link", { name: /Factures/ })).toHaveAttribute("aria-current", "location");
    expect(screen.getByRole("link", { name: "Synthèse" })).not.toHaveAttribute("aria-current");
  });

  it("clic : saut vers la section (focus déplacé), ancre active immédiatement, rappel onNavigate", async () => {
    const user = userEvent.setup();
    const onNavigate = vi.fn();
    render(<Page onNavigate={onNavigate} />);
    await user.click(screen.getByRole("link", { name: "Clôtures" }));
    expect(screen.getByRole("link", { name: "Clôtures" })).toHaveAttribute("aria-current", "location");
    const cible = document.getElementById("clotures")!;
    expect(cible).toHaveFocus();
    expect(cible).toHaveAttribute("tabindex", "-1");
    expect(onNavigate).toHaveBeenCalledWith("clotures");
  });

  it("aucune section : rien n'est rendu", () => {
    const { container } = render(<SectionNav items={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
