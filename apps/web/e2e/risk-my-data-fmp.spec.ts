import { expect, test, type Page } from "@playwright/test";

// Risk & Performance on My data with FMP, and the provider choice when the user
// has both an FMP and a Tiingo key. FMP is the fake in e2e/fake-fmp.mjs and
// Tiingo the one in e2e/fake-tiingo.mjs (keys starting with "good" are valid;
// both serve AAPL, MSFT and SPY for 30 trading days from 2024-01-02, where AAPL's
// split-adjusted max drawdown is 10%).

function uniqueEmail(label: string) {
  return `${label}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.test`;
}

async function signInWithKeys(page: Page, keys: { tiingo?: string; fmp?: string }) {
  await page.goto("/settings");
  await page.getByRole("main").getByRole("link", { name: "Sign in with Google" }).click();
  await page.getByLabel("Email").fill(uniqueEmail("fmpdata"));
  await page.getByRole("button", { name: "Continue" }).click();
  for (const [provider, name] of [
    ["tiingo", "Tiingo"],
    ["fmp", "FMP"],
  ] as const) {
    const section = page.getByRole("main").getByRole("region", { name: `Your ${name} key` });
    await expect(section.getByLabel(`${name} API key`)).toBeVisible();
    const key = keys[provider];
    if (!key) continue;
    await section.getByLabel(`${name} API key`).fill(key);
    await section.getByRole("button", { name: "Save key" }).click();
    await expect(section.getByRole("status")).toHaveText("Key saved.");
  }
}

async function openRisk(page: Page) {
  await page.goto("/risk");
  const main = page.getByRole("main");
  // Wait for the first (demo) result so the page is hydrated and the key list has loaded.
  await expect(main.locator('[data-metric-value="annualized_return:DEMO-A"]')).toHaveAttribute("data-status", "ok");
  return main;
}

const metric = (page: Page, id: string) => page.getByRole("main").locator(`[data-metric-value="${id}"]`);

test("a user with only an FMP key gets My data on FMP", async ({ page }) => {
  await signInWithKeys(page, { fmp: "goodfmp000000000000000000000000fmp1" });
  const main = await openRisk(page);
  const toggle = main.getByTestId("data-mode");

  await toggle.getByText("My data").click();

  await expect(main.getByTestId("my-data-note")).toContainText("FMP");
  await expect(metric(page, "max_drawdown:AAPL")).toContainText("10.00%");
  await expect(main.getByText("Source: FMP")).toBeVisible();
  await expect(main.getByTestId("demo-badge")).toHaveCount(0);
});

test("a user with both keys picks the provider and the result names the one used", async ({ page }) => {
  await signInWithKeys(page, {
    tiingo: "good0000000000000000000000000000000abcd",
    fmp: "goodfmp000000000000000000000000fmp1",
  });
  const main = await openRisk(page);
  const toggle = main.getByTestId("data-mode");
  await expect(toggle.getByLabel("Demo data")).toBeChecked();

  await toggle.getByText("My data (FMP)").click();
  await expect(toggle.getByLabel("My data (FMP)")).toBeChecked();
  await expect(main.getByTestId("my-data-note")).toContainText("FMP");
  await expect(metric(page, "max_drawdown:AAPL")).toContainText("10.00%");
  await expect(main.getByText("Source: FMP")).toBeVisible();

  await toggle.getByText("My data (Tiingo)").click();
  await expect(toggle.getByLabel("My data (Tiingo)")).toBeChecked();
  await expect(main.getByText("Source: Tiingo")).toBeVisible();
  await expect(main.getByText("Source: FMP")).toHaveCount(0);
  await expect(metric(page, "max_drawdown:AAPL")).toContainText("10.00%");
});
