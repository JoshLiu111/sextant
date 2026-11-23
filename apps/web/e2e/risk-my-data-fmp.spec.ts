import { expect, test, type Page } from "@playwright/test";

// Risk & Performance on My data with FMP, and the provider choice when the user
// has both an FMP and a Tiingo key. FMP is the fake in e2e/fake-fmp.mjs and
// Tiingo the one in e2e/fake-tiingo.mjs (keys starting with "good" are valid;
// both serve AAPL, MSFT and SPY for 30 trading days from 2024-01-02, where AAPL's
// split-adjusted max drawdown is 10%, and MSFT last closes at $402.00 on 2024-02-12).

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

test("the Valuation Calculator takes its My data price from FMP's latest close", async ({ page }) => {
  await signInWithKeys(page, { fmp: "goodfmp000000000000000000000000fmp1" });
  await page.goto("/valuation");
  const main = page.getByRole("main");
  const value = (id: string) => main.locator(`[data-metric-value="${id}"]`);
  // EDGAR's MSFT FY2026 at the defaults (e2e/fake-edgar.mjs).
  await expect(value("intrinsic_value_per_share")).toContainText("$163.73");

  await main.getByTestId("data-mode").getByText("My data").click();

  const market = main.getByTestId("market-comparison");
  await expect(market.locator('[data-metric-value="share_price"]')).toContainText("$402.00");
  await expect(market.locator('[data-metric-value="share_price"]')).toContainText("Latest close from FMP, 2024-02-12");
  await expect(main.getByText("Optional. Leave blank to use the latest close from FMP.")).toBeVisible();

  // The footer credits both sources the result used: EDGAR statements and the FMP price.
  const footer = page.getByRole("contentinfo");
  await expect(footer.locator('[data-attribution="fmp"]')).toContainText("Data provided by Financial Modeling Prep");
  await expect(footer.locator('[data-attribution="sec"]')).toBeVisible();
});

test("on Risk & Performance with FMP the footer credits FMP instead of demo data", async ({ page }) => {
  await signInWithKeys(page, { fmp: "goodfmp000000000000000000000000fmp1" });
  const main = await openRisk(page);
  const footer = page.getByRole("contentinfo");

  await main.getByTestId("data-mode").getByText("My data").click();
  await expect(metric(page, "max_drawdown:AAPL")).toContainText("10.00%");
  await expect(footer.locator('[data-attribution="fmp"]')).toBeVisible();
  await expect(footer.locator('[data-attribution="demo"]')).toHaveCount(0);
  await expect(footer.locator('[data-attribution="tiingo"]')).toHaveCount(0);
});

test("with both keys the screener's price criteria run on the provider the user picks", async ({ page }) => {
  await signInWithKeys(page, {
    tiingo: "good0000000000000000000000000000000abcd",
    fmp: "goodfmp000000000000000000000000fmp1",
  });
  await page.goto("/screener");
  const main = page.getByRole("main");
  // A cold screen fetches ~20 frames through the EDGAR limiter; by then the key list has loaded too.
  await expect(main.getByTestId("screen-summary")).toBeVisible({ timeout: 30_000 });
  const provider = main.getByLabel("Price provider");
  await expect(provider).toHaveValue("tiingo");

  await provider.selectOption({ label: "FMP" });
  await expect(main.getByTestId("price-criteria-note")).toContainText("FMP");
  await main.getByRole("button", { name: "Add criterion" }).click();
  await main.getByLabel("Metric for criterion 4").selectOption({ label: "52-week change" });
  await main.getByLabel("Value for criterion 4").fill("18");
  await main.getByRole("button", { name: "Run screen" }).click();
  // The FMP fake only knows AAPL, MSFT and SPY, so the screen asked FMP and got no prices for its matches.
  await expect(main.getByTestId("prices-info")).toContainText("Prices: FMP", { timeout: 30_000 });

  await provider.selectOption({ label: "Tiingo" });
  await expect(main.getByTestId("prices-info")).toContainText("Prices: Tiingo, as of 2026-11-20", { timeout: 30_000 });
});

test("with both keys My Portfolio runs the demo and saved portfolios on the provider the user picks", async ({
  page,
}) => {
  await signInWithKeys(page, {
    tiingo: "good0000000000000000000000000000000abcd",
    fmp: "goodfmp000000000000000000000000fmp1",
  });
  await page.goto("/portfolio");
  const main = page.getByRole("main");
  const demo = main.getByRole("region", { name: "Demo portfolio" });
  await expect(demo.locator('[data-metric-value="annualized_return:portfolio"]')).toHaveAttribute("data-status", "ok");
  await demo.getByTestId("data-mode").getByText("My data (FMP)").click();
  await expect(demo.getByTestId("results").getByText("Source: FMP")).toBeVisible();
  await expect(demo.locator('[data-metric-value="annualized_volatility:portfolio"]')).toHaveAttribute(
    "data-status",
    "ok",
  );

  const saved = main.getByRole("region", { name: "Your portfolios" });
  await saved.getByLabel("Portfolio name").fill("Brokerage");
  await saved.getByLabel("Ticker 1").fill("AAPL");
  await saved.getByLabel("Quantity 1").fill("10");
  await saved.getByLabel("Cost price 1").fill("90");
  await saved.getByRole("button", { name: "Save portfolio" }).click();
  await expect(saved.getByRole("status").first()).toContainText("Saved");
  const results = saved.getByTestId("saved-results");
  const toggle = results.getByTestId("data-mode");
  // Real tickers open on the first My data provider; the user can pick the other.
  await expect(toggle.getByLabel("My data (Tiingo)")).toBeChecked({ timeout: 20_000 });
  await toggle.getByText("My data (FMP)").click();
  await expect(toggle.getByLabel("My data (FMP)")).toBeChecked();
  await expect(results.getByText("Source: FMP").first()).toBeVisible();
  await expect(results.locator('[data-position-value="market_value:AAPL"]')).toHaveText("1,300.00");
});
