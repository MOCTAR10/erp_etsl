import path from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "@playwright/test";

import { DEMO_PASSWORD, DEMO_USERS, loginAs } from "../helpers";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** Une seule connexion (admin, données de démo) ; la session (localStorage `etls.auth`) est rejouée par les écrans. */
test("connexion admin", async ({ page }) => {
  await loginAs(page, DEMO_USERS.admin, DEMO_PASSWORD);
  await page.context().storageState({ path: path.join(__dirname, ".auth/admin.json") });
});
