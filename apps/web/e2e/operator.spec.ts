import { expect, test, type Browser, type Page } from "@playwright/test";

// Operator view of AI usage (/operator). Only OPERATOR_EMAILS (playwright.config.ts:
// operator@example.test) get in; everyone else gets a real 404. AI calls go to
// e2e/fake-anthropic.mjs. Users sign in with unique emails, so tests stay independent.

const OPERATOR_EMAIL = "operator@example.test";

function uniqueEmail(label: string) {
  return `${label}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.test`;
}

async function signIn(page: Page, email: string, returnTo = "/") {
  await page.goto(returnTo);
  await page.getByRole("banner").getByRole("link", { name: "Sign in with Google" }).click();
  await page.getByLabel("Email").fill(email);
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByRole("banner").getByRole("button", { name: "Sign out" })).toBeVisible();
}

/** A fresh user, in their own browser context, who makes one AI Explain call. */
async function userWithOneAiCall(browser: Browser): Promise<string> {
  const email = uniqueEmail("ai-user");
  const context = await browser.newContext();
  const page = await context.newPage();
  await signIn(page, email, "/options");
  const ai = page.getByRole("main").getByRole("region", { name: "AI Explain" });
  await ai.getByRole("button", { name: "AI Explain" }).click();
  await expect(ai.getByTestId("ai-explanation")).toBeVisible();
  await context.close();
  return email;
}

function todayUtc() {
  return new Date().toISOString().slice(0, 10);
}

test("visitors get a 404", async ({ page }) => {
  const response = await page.goto("/operator");

  expect(response?.status()).toBe(404);
  await expect(page.getByRole("heading", { level: 1, name: "Page not found" })).toBeVisible();
});

test("signed-in users who are not operators get a 404 that shows no one's email", async ({ browser, page }) => {
  const other = await userWithOneAiCall(browser);
  await signIn(page, uniqueEmail("not-operator"));

  const response = await page.goto("/operator");

  expect(response?.status()).toBe(404);
  await expect(page.getByRole("heading", { level: 1, name: "Page not found" })).toBeVisible();
  await expect(page.locator("body")).not.toContainText(other);
});

test("the operator sees each user's AI calls, tokens and estimated cost by day", async ({ browser, page }) => {
  const user = await userWithOneAiCall(browser);
  await signIn(page, OPERATOR_EMAIL);

  const response = await page.goto("/operator");

  expect(response?.status()).toBe(200);
  const main = page.getByRole("main");
  await expect(main.getByRole("heading", { level: 1, name: "AI usage" })).toBeVisible();

  const perUser = main.getByRole("table", { name: "AI usage per user" });
  const userRow = perUser.getByRole("row").filter({ hasText: user });
  await expect(userRow.getByRole("cell").nth(1)).toHaveText("1"); // calls
  await expect(userRow.getByRole("cell").nth(2)).not.toHaveText("0"); // input tokens
  await expect(userRow.getByRole("cell").nth(4)).toHaveText(/^\$\d+\.\d{4}$/); // estimated cost

  const perDay = main.getByRole("table", { name: "AI usage per user per day" });
  const dayRow = perDay.getByRole("row").filter({ hasText: user });
  await expect(dayRow.getByRole("cell").nth(0)).toHaveText(todayUtc());
  await expect(dayRow.getByRole("cell").nth(2)).toHaveText("1");

  await expect(main.getByTestId("ai-usage-pricing")).toContainText("per million input tokens");
});
