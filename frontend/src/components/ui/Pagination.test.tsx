import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import "../../i18n";
import { pagedQuery } from "../../lib/usePagedList";
import { Board, BoardColumn } from "./Board";
import { Pagination } from "./Pagination";
import { SearchField } from "./SearchField";

describe("<Pagination />", () => {
  it("n'affiche rien quand tout tient sur une page", () => {
    const { container } = render(<Pagination page={1} pageSize={20} count={12} onPageChange={() => {}} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("pagine : suivant / précédent, bornes désactivées, total annoncé", async () => {
    const onPage = vi.fn();
    const user = userEvent.setup();
    const { rerender } = render(<Pagination page={1} pageSize={20} count={45} onPageChange={onPage} />);
    expect(screen.getByText("45 résultats")).toBeInTheDocument();
    expect(screen.getByText("Page 1 / 3")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Page précédente" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Page suivante" }));
    expect(onPage).toHaveBeenCalledWith(2);
    rerender(<Pagination page={3} pageSize={20} count={45} onPageChange={onPage} />);
    expect(screen.getByRole("button", { name: "Page suivante" })).toBeDisabled();
  });

  it("change la taille de page", async () => {
    const onSize = vi.fn();
    const user = userEvent.setup();
    render(<Pagination page={1} pageSize={20} count={200} onPageChange={() => {}} onPageSizeChange={onSize} />);
    await user.selectOptions(screen.getByRole("combobox", { name: "Lignes par page" }), "50");
    expect(onSize).toHaveBeenCalledWith(50);
  });
});

describe("<SearchField />", () => {
  it("transmet la saisie après le délai, pas à chaque touche", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const onChange = vi.fn();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<SearchField value="" onChange={onChange} delay={300} />);
    await user.type(screen.getByRole("searchbox"), "zan");
    expect(onChange).not.toHaveBeenCalled();
    vi.advanceTimersByTime(350);
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith("zan");
    vi.useRealTimers();
  });
});

describe("pagedQuery", () => {
  it("compose page, taille, recherche et filtres fixes", () => {
    expect(pagedQuery(2, 50, " abc ", "statut=ouvert")).toBe("?statut=ouvert&page=2&page_size=50&search=abc");
  });
  it("omet search quand vide", () => {
    expect(pagedQuery(1, 20, "  ")).toBe("?page=1&page_size=20");
  });
});

describe("<BoardColumn limit />", () => {
  it("affiche `limit` cartes puis « Voir plus » révèle la suite", async () => {
    const user = userEvent.setup();
    render(
      <Board>
        <BoardColumn title="Col" limit={2}>
          {[1, 2, 3, 4, 5].map((n) => (
            <div key={n} className="task-card">
              {`carte ${n}`}
            </div>
          ))}
        </BoardColumn>
      </Board>,
    );
    expect(screen.getAllByText(/^carte /)).toHaveLength(2);
    await user.click(screen.getByRole("button", { name: "Voir plus (3)" }));
    expect(screen.getAllByText(/^carte /)).toHaveLength(4);
    await user.click(screen.getByRole("button", { name: "Voir plus (1)" }));
    expect(screen.getAllByText(/^carte /)).toHaveLength(5);
    expect(screen.queryByRole("button", { name: /Voir plus/ })).toBeNull();
  });

  it("sans limit : toutes les cartes, pas de bouton", () => {
    render(
      <Board>
        <BoardColumn title="Col">
          <div className="task-card">a</div>
          <div className="task-card">b</div>
        </BoardColumn>
      </Board>,
    );
    expect(screen.queryByRole("button")).toBeNull();
  });
});
