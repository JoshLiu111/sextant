import { expect, test, type Page } from "@playwright/test";

// Sign-in runs against the fake OIDC provider in e2e/fake-oidc.mjs, never Google.
// Each test signs in with its own email, so tests stay independent.

function uniqueEmail(label: string) {
  return `${label}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.test`;
}

async function signIn(page: Page, email: string, name = "Test User") {
  await page.goto("/");
  await page.getByRole("banner").getByRole("link", { name: "Sign in with Google" }).click();
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Name").fill(name);
  await page.getByRole("button", { name: "Continue" }).click();
}

test("anonymous visitors see a sign-in link and can still open every tool", async ({ page }) => {
  await page.goto("/");

  await expect(
    page.getByRole("banner").getByRole("link", { name: "Sign in with Google" }),
  ).toBeVisible();
  const nav = page.getByRole("navigation", { name: "Tools" });
  await nav.getByRole("button", { name: "Portfolio & Risk" }).click();
  await nav.getByRole("link", { name: "My Portfolio" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "My Portfolio" })).toBeVisible();
});

test("signing in shows the user in the nav, and signing out ends the session", async ({ page }) => {
  const email = uniqueEmail("signout");
  await signIn(page, email, "Ada Lovelace");

  const banner = page.getByRole("banner");
  await expect(banner.getByTestId("signed-in-user")).toHaveText("Ada Lovelace");
  await expect(banner.getByRole("link", { name: "Sign in with Google" })).toHaveCount(0);

  await banner.getByRole("button", { name: "Sign out" }).click();

  await expect(banner.getByRole("link", { name: "Sign in with Google" })).toBeVisible();
  await page.reload();
  await expect(banner.getByRole("link", { name: "Sign in with Google" })).toBeVisible();
  await expect(banner.getByTestId("signed-in-user")).toHaveCount(0);
});

test("sign-in returns the user to the page they started from", async ({ page }) => {
  await page.goto("/risk");
  await page.getByRole("banner").getByRole("link", { name: "Sign in with Google" }).click();
  await page.getByLabel("Email").fill(uniqueEmail("return"));
  await page.getByRole("button", { name: "Continue" }).click();

  await expect(page).toHaveURL(/\/risk$/);
  await expect(page.getByRole("banner").getByTestId("signed-in-user")).toBeVisible();
});

test("deleting the account asks for confirmation, then removes it and signs out", async ({ page }) => {
  const email = uniqueEmail("delete");
  await signIn(page, email, "Grace Hopper");
  await page.getByRole("banner").getByRole("link", { name: "Account" }).click();

  const main = page.getByRole("main");
  await expect(main.getByText(email)).toBeVisible();
  await main.getByRole("button", { name: "Delete account" }).click();

  // Nothing is deleted until the user confirms; cancelling keeps the account.
  await main.getByRole("button", { name: "Cancel" }).click();
  await page.reload();
  await expect(main.getByText(email)).toBeVisible();

  await main.getByRole("button", { name: "Delete account" }).click();
  await main.getByRole("button", { name: "Yes, permanently delete my account" }).click();

  await expect(page).toHaveURL(/\/account\?deleted=1$/);
  await expect(main.getByText("Your account and all of its data were deleted.")).toBeVisible();
  await expect(page.getByRole("banner").getByRole("link", { name: "Sign in with Google" })).toBeVisible();

  await page.goto("/account");
  await expect(page.getByRole("main").getByText(email)).toHaveCount(0);
});
