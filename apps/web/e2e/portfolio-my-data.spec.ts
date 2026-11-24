import { expect, test, type Page } from "@playwright/test";

// My Portfolio on My data: a signed-in user with a saved Tiingo key computes the
// demo portfolio and a saved portfolio on their own Tiingo prices. Tiingo is the
// fake in e2e/fake-tiingo.mjs (keys starting with "good" are valid; it knows
// AAPL, MSFT and SPY, 30 trading days from 2024-01-02). Split-adjusted, AAPL goes
// 100 -> 120 -> 108 -> 130 (max drawdown 10%, +30% overall) and ends at 130.

const COLD = { timeout: 20_000 };

function uniqueEmail(label: string) {
  return `${label}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.test`;
}

async function signIn(page: Page, email: string, { withKey }: { withKey: boolean }) {
  await page.goto("/settings");
  await page.getByRole("main").getByRole("link", { name: "Sign in with Google" }).click();
  await page.getByLabel("Email").fill(email);
  await page.getByRole("button", { name: "Continue" }).click();
  const section = page.getByRole("main").getByRole("region", { name: "Your Tiingo key" });
  await expect(section.getByLabel("Tiingo API key")).toBeVisible();
  if (withKey) {
    await section.getByLabel("Tiingo API key").fill("good0000000000000000000000000000000abcd");
    await section.getByRole("button", { name: "Save key" }).click();
    await expect(section.getByRole("status")).toHaveText("Key saved.");
  }
}

/** The demo portfolio's region, once its first (demo) result is in: hydrated, key list loaded. */
async function openDemoPortfolio(page: Page) {
  await page.goto("/portfolio");
  const demo = page.getByRole("main").getByRole("region", { name: "Demo portfolio" });
  const first = demo.getByTestId("results").locator('[data-metric-value="annualized_return:portfolio"]');
  await expect(first).toHaveAttribute("data-status", "ok", COLD);
  return demo;
}

test("visitors and users without a key get no toggle on My Portfolio", async ({ page }) => {
  let demo = await openDemoPortfolio(page);
  await expect(demo.getByTestId("data-mode")).toHaveCount(0);

  await signIn(page, uniqueEmail("pf-nokey"), { withKey: false });
  demo = await openDemoPortfolio(page);
  await expect(demo.getByTestId("data-mode")).toHaveCount(0);
  await expect(page.getByRole("main").getByTestId("data-mode")).toHaveCount(0);
});

test("the demo portfolio computes on the user's Tiingo prices and refuses demo tickers there", async ({ page }) => {
  await signIn(page, uniqueEmail("pf-mydata"), { withKey: true });
  const demo = await openDemoPortfolio(page);
  const toggle = demo.getByTestId("data-mode");
  await expect(toggle.getByLabel("Demo data")).toBeChecked();

  await toggle.getByText("My data").click();

  await expect(demo.getByLabel("Ticker 1")).toHaveValue("AAPL");
  await expect(demo.getByLabel("Ticker 2")).toHaveValue("MSFT");
  await expect(demo.getByRole("textbox", { name: "Benchmark" })).toHaveValue("SPY");
  await expect(demo.getByTestId("my-data-note")).toContainText("Tiingo");
  const results = demo.getByTestId("results");
  const volatility = results.locator('[data-metric-value="annualized_volatility:portfolio"]');
  await expect(volatility).toHaveAttribute("data-status", "ok");
  await expect(results.getByTestId("demo-badge")).toHaveCount(0);
  await expect(results.getByText("Source: Tiingo")).toBeVisible();
  // The footer follows the data: Tiingo, no demo-data notice, and no exchange rates (nothing was converted).
  const footer = page.getByRole("contentinfo");
  await expect(footer.locator('[data-attribution="tiingo"]')).toBeVisible();
  await expect(footer.locator('[data-attribution="demo"]')).toHaveCount(0);
  await expect(footer.locator('[data-attribution="frankfurter"]')).toHaveCount(0);
  // The rebalancing backtest and efficient frontier (their own tabs) run on the same My data holdings.
  const main = page.getByRole("main");
  const backtest = main.getByRole("region", { name: "Rebalancing backtest" });
  const frontier = main.getByRole("region", { name: "Efficient frontier" });
  const openTab = (name: string) => demo.getByRole("tab", { name }).click();
  await openTab("Rebalancing");
  await expect(backtest.locator('[data-metric-value="turnover:rebalanced"]')).toHaveAttribute("data-status", "ok");
  await expect(backtest.getByTestId("demo-badge")).toHaveCount(0);
  await openTab("Efficient frontier");
  await expect(frontier.getByRole("cell", { name: "AAPL" })).toBeVisible();
  await expect(frontier.getByTestId("demo-badge")).toHaveCount(0);

  await demo.getByLabel("Ticker 2").fill("DEMO-A");
  await demo.getByRole("button", { name: "Calculate" }).click();
  await expect(frontier.getByText(/DEMO-A is a demo ticker/).first()).toBeVisible();
  await openTab("Rebalancing");
  await expect(backtest.getByText(/DEMO-A is a demo ticker/).first()).toBeVisible();
  await openTab("Overview");
  await expect(demo.getByText(/DEMO-A is a demo ticker/).first()).toBeVisible();

  await toggle.getByText("Demo data").click();
  await expect(demo.getByRole("textbox", { name: "Benchmark" })).toHaveValue("DEMO-MKT");
  await expect(results.getByTestId("demo-badge")).toBeVisible();
});

test("a saved portfolio with real tickers is valued at the user's Tiingo closes", async ({ page }) => {
  await signIn(page, uniqueEmail("pf-saved"), { withKey: true });
  await page.goto("/portfolio");
  const saved = page.getByRole("main").getByRole("region", { name: "Your portfolios" });
  await saved.getByLabel("Portfolio name").fill("Brokerage");
  await saved.getByLabel("Ticker 1").fill("AAPL");
  await saved.getByLabel("Quantity 1").fill("10");
  await saved.getByLabel("Cost price 1").fill("90");
  await saved.getByRole("button", { name: "Save portfolio" }).click();
  await expect(saved.getByRole("status").first()).toContainText("Saved");

  const results = saved.getByTestId("saved-results");
  // Real tickers and a saved key: it opens on My data, with no failed Demo run first.
  await expect(results.getByTestId("data-mode").getByLabel("My data")).toBeChecked(COLD);
  await expect(results.getByRole("textbox", { name: "Benchmark" })).toHaveValue("SPY");
  await expect(results.locator('[data-position-value="market_value:AAPL"]')).toHaveText("1,300.00", COLD);
  await expect(results.locator('[data-metric-value="max_drawdown:portfolio"]')).toContainText("10.00%");
  await expect(results.locator('[data-metric-value="twr:portfolio"]')).toContainText("30.00%");
  // The same headline figures as the demo portfolio, from the same result.
  const strip = results.getByTestId("key-figures");
  await expect(strip.locator("[data-key-figure]")).toHaveCount(4);
  await expect(strip.locator('[data-key-figure="max_drawdown:portfolio"]')).toContainText("10.00%");
  await expect(results.getByTestId("demo-badge")).toHaveCount(0);
  await expect(results.getByText(/Unknown ticker/)).toHaveCount(0);
});

test("an unknown ticker in a saved portfolio marks only its own position missing", async ({ page }) => {
  await signIn(page, uniqueEmail("pf-unknown"), { withKey: true });
  await page.goto("/portfolio");
  const saved = page.getByRole("main").getByRole("region", { name: "Your portfolios" });
  await saved.getByLabel("Portfolio name").fill("Mixed");
  await saved.getByLabel("Ticker 1").fill("AAPL");
  await saved.getByLabel("Quantity 1").fill("10");
  await saved.getByLabel("Cost price 1").fill("90");
  await saved.getByRole("button", { name: "Add holding" }).click();
  await saved.getByLabel("Ticker 2").fill("ZZZZ");
  await saved.getByLabel("Quantity 2").fill("3");
  await saved.getByLabel("Cost price 2").fill("20");
  await saved.getByRole("button", { name: "Save portfolio" }).click();
  await expect(saved.getByRole("status").first()).toContainText("Saved");

  const results = saved.getByTestId("saved-results");
  await expect(results.locator('[data-position-value="market_value:AAPL"]')).toHaveText("1,300.00", COLD);
  const unknown = results.locator('[data-position-value="market_value:ZZZZ"]');
  await expect(unknown).toHaveAttribute("data-status", "missing_data");
  await expect(unknown).toHaveAttribute("title", /Tiingo has no ticker ZZZZ/);
  await expect(results.locator('[data-position-value="cost_basis:ZZZZ"]')).toHaveText("60.00");
  const volatility = results.locator('[data-metric-value="annualized_volatility:portfolio"]');
  await expect(volatility).toHaveAttribute("data-status", "missing_data");
  await expect(volatility).toContainText("ZZZZ");
  await expect(results.locator('[data-metric-value="annualized_volatility:benchmark"]')).toHaveAttribute(
    "data-status",
    "ok",
  );
  await expect(results.getByRole("alert")).toHaveCount(0);
});
