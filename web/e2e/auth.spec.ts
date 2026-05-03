import { expect, test } from "@playwright/test";

import { e2eCredentials, login, SIGN_IN_PATH } from "./helpers";

test.use({ storageState: { cookies: [], origins: [] } });

test("unauthenticated user is redirected to sign-in when visiting home", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/login\?callbackUrl=(%2F|\/)/);
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
});

test("correct credentials log in and reach mail", async ({ page }) => {
  await login(page);
  await expect(page.getByRole("heading", { name: "Mail Chat", exact: true })).toBeVisible();
});

test("wrong credentials show an error and stay on sign-in page", async ({ page }) => {
  const { username } = e2eCredentials();
  await page.goto(`${SIGN_IN_PATH}?callbackUrl=/`);
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password").fill("not-the-password");
  await page.getByRole("button", { name: /^sign in$/i }).click();

  await expect(page.locator('[role="alert"]').filter({ hasText: "Invalid username or password" })).toBeVisible();
  await expect(page).toHaveURL(/\/login/);
});

test("logout clears the session", async ({ page }) => {
  await login(page);
  await page.getByRole("button", { name: /sign out|logout/i }).click();

  await expect(page).toHaveURL(/\/login/);
  await page.goto("/");
  await expect(page).toHaveURL(/\/login\?callbackUrl=(%2F|\/)/);
});
