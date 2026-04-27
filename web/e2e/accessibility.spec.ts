import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { login, openExistingConversation, SIGN_IN_PATH } from "./helpers";

async function expectNoBlockingA11yViolations(page: Page) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  const blocking = results.violations.filter(
    (violation) => violation.impact && ["serious", "critical"].includes(violation.impact),
  );
  expect(blocking, JSON.stringify(blocking, null, 2)).toEqual([]);
}

test("home page has no serious or critical axe violations", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/chat\/[^/?#]+/);
  await expectNoBlockingA11yViolations(page);
});

test("sign-in page has no serious or critical axe violations", async ({ browser }) => {
  const context = await browser.newContext({ storageState: { cookies: [], origins: [] } });
  const page = await context.newPage();
  await page.goto(SIGN_IN_PATH);
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await expectNoBlockingA11yViolations(page);
  await context.close();
});

test("chat page has no serious or critical axe violations", async ({ page }) => {
  await openExistingConversation(page);
  await expectNoBlockingA11yViolations(page);
});

test("newly created chat route has no serious or critical axe violations", async ({ browser }) => {
  const context = await browser.newContext();
  const page = await context.newPage();
  await login(page);
  await expectNoBlockingA11yViolations(page);
  await context.close();
});
