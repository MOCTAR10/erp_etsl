import { describe, expect, it } from "vitest";

import * as ui from "./index";

describe("barrel components/ui", () => {
  it("exporte les aides d'actions partagées (cartes et tableaux)", () => {
    expect(typeof ui.CardActions).toBe("function");
    expect(typeof ui.actionsColumn).toBe("function");
    const col = ui.actionsColumn<{ id: number }>("Actions", () => []);
    expect(col.key).toBe("__actions");
  });

  it("exporte le kit complet utilisé par les écrans", () => {
    for (const name of ["DataGrid", "DataTable", "PagedDataGrid", "Kpi", "Menu", "CommandPalette", "DatePicker", "MonthPicker", "FilterBar", "EmptyState"] as const) {
      expect(ui[name], name).toBeDefined();
    }
  });
});
