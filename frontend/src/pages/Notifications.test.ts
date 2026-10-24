import { describe, expect, it } from "vitest";

import { groupeDe, joursRetard } from "./Notifications";

describe("notifications : regroupement et retard", () => {
  const now = new Date("2026-10-24T12:00:00");

  it("classe par jour de réception", () => {
    expect(groupeDe("2026-10-24T06:03:00", now)).toBe("aujourdhui");
    expect(groupeDe("2026-10-21T06:03:00", now)).toBe("semaine");
    expect(groupeDe("2026-10-01T06:03:00", now)).toBe("ancien");
  });

  it("compte les jours de retard de la tâche", () => {
    expect(joursRetard("2026-10-19T12:00:00", now)).toBe(5);
    expect(joursRetard("2026-10-30T12:00:00", now)).toBe(0);
    expect(joursRetard(null, now)).toBe(0);
  });
});
