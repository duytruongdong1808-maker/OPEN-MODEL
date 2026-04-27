import { test } from "@playwright/test";

import { login, STORAGE_STATE_PATH } from "./helpers";

test.setTimeout(60_000);

test("authenticate", async ({ page }) => {
  await login(page);
  await page.context().storageState({ path: STORAGE_STATE_PATH });
});
