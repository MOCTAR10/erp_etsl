import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import "../i18n";
import type { NotificationItem } from "../types";
import { NotificationBell } from "./NotificationBell";

const notif = (id: string, subject: string, is_read: boolean): NotificationItem => ({
  id,
  subject,
  message: "",
  kind: "reminder",
  is_read,
  document_title: "Contrat AFF00001",
  step_name: null,
  created_at: "2026-10-24T09:00:00+01:00",
});

function monter(items: NotificationItem[]) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <NotificationBell items={items} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("NotificationBell", () => {
  it("affiche le nombre de non lues et les liste en premier dans l'aperçu", async () => {
    monter([notif("1", "Ancienne lue", true), notif("2", "Relance : visa du BC", false), notif("3", "Escalade PV", false)]);
    const cloche = screen.getByRole("button", { name: "Notifications : 2 non lues" });
    expect(cloche).toHaveTextContent("2");
    await userEvent.click(cloche);
    expect(await screen.findByText("Relance : visa du BC")).toBeInTheDocument();
    expect(screen.getByText("Escalade PV")).toBeInTheDocument();
    expect(screen.queryByText("Ancienne lue")).toBeNull();
    expect(screen.getByRole("button", { name: "Voir toutes les notifications" })).toBeInTheDocument();
  });

  it("sans notification : pas de compteur, message vide", async () => {
    monter([]);
    const cloche = screen.getByRole("button", { name: "Notifications" });
    expect(cloche).toHaveTextContent("");
    await userEvent.click(cloche);
    expect(await screen.findByText("Aucune notification")).toBeInTheDocument();
  });
});
