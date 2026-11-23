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
  await expect(main.getByRole("heading", { level: 1, name: "Operator" })).toBeVisible();
  await expect(main.getByRole("heading", { level: 2, name: "AI usage" })).toBeVisible();

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

test("the operator sees registered users, today's sign-ups and recent sign-ins", async ({ browser, page }) => {
  const context = await browser.newContext();
  await signIn(await context.newPage(), uniqueEmail("new-user"));
  await context.close();
  await signIn(page, OPERATOR_EMAIL);

  await page.goto("/operator");

  const users = page.getByRole("main").getByRole("region", { name: "Users" });
  await expect(users.getByTestId("users-total")).toHaveText(/^[1-9][\d,]*$/);
  await expect(users.getByText("Signed in within 7 days")).toBeVisible();
  await expect(users.getByTestId("users-signed-in-7")).toHaveText(/^[1-9][\d,]*$/);
  await expect(users.getByText("Signed in within 30 days")).toBeVisible();

  const signUps = users.getByRole("table", { name: "Sign-ups per day" });
  const today = signUps.getByRole("row").filter({ hasText: todayUtc() });
  await expect(today.getByRole("cell").nth(1)).toHaveText(/^[1-9][\d,]*$/);
});

test("the operator picks the window the sign-ups and AI usage cover", async ({ page }) => {
  await signIn(page, OPERATOR_EMAIL);
  await page.goto("/operator");
  const main = page.getByRole("main");
  const window = main.getByRole("navigation", { name: "Window" });
  await expect(window.getByRole("link", { name: "Last 30 days" })).toHaveAttribute("aria-current", "page");
  const signUps = main.getByRole("table", { name: "Sign-ups per day" });
  await expect(signUps.locator("tbody tr")).toHaveCount(30);

  await window.getByRole("link", { name: "Last 7 days" }).click();

  await expect(page).toHaveURL(/\/operator\?days=7$/);
  await expect(window.getByRole("link", { name: "Last 7 days" })).toHaveAttribute("aria-current", "page");
  await expect(signUps.locator("tbody tr")).toHaveCount(7);
  const weekAgo = new Date(Date.now() - 6 * 86_400_000).toISOString().slice(0, 10);
  await expect(main.getByRole("region", { name: "Users" })).toContainText(`${weekAgo} to ${todayUtc()}`);
  await expect(main.getByRole("region", { name: "AI usage" })).toContainText(`${weekAgo} to ${todayUtc()}`);
});
