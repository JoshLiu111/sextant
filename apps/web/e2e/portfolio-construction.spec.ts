import { expect, test, type Locator, type Page } from "@playwright/test";

const RISK_METRICS = ["annualized_return", "annualized_volatility", "max_drawdown", "var", "cvar", "sharpe", "sortino", "beta"];

async function openPortfolio(page: Page) {
  await page.goto("/portfolio");
  const main = page.getByRole("main");
  await expect(main.getByRole("heading", { level: 1, name: "My Portfolio" })).toBeVisible();
  return main;
}

const metric = (scope: Locator, id: string) => scope.locator(`[data-metric-value="${id}"]`);

/** The first results wait on a cold dev compile and cold demo data. */
const COLD = { timeout: 20_000 };

const percent = (text: string | null) => Number((text ?? "").replace(/[^\d.-]/g, ""));

test("the rebalancing backtest shows both strategies side by side on demo data, signed out", async ({ page }) => {
  const main = await openPortfolio(page);
  const backtest = main.getByRole("region", { name: "Rebalancing backtest" });

  for (const who of ["rebalanced", "buy_and_hold"]) {
    for (const id of RISK_METRICS) {
      await expect(metric(backtest, `${id}:${who}`)).toHaveAttribute("data-status", "ok", COLD);
    }
  }
  // Quarterly by default: 20 quarter ends from 2021 to 2025, less the last one.
  await expect(metric(backtest, "rebalance_count:rebalanced")).toContainText("19");
  await expect(backtest.getByTestId("demo-badge")).toContainText("Demo data");

  const chart = backtest.getByRole("img", { name: /rebalanced vs buy and hold/i });
  await expect(chart).toBeVisible();
  await chart.hover();
  await expect(backtest.getByTestId("chart-tooltip")).toContainText("Rebalanced");
  await expect(backtest.getByTestId("chart-tooltip")).toContainText("Buy and hold");

  await backtest.getByLabel("Rebalancing rule").selectOption("monthly");
  await expect(metric(backtest, "rebalance_count:rebalanced")).toContainText("59");
});

test("a drift threshold no holding reaches never rebalances, so the two strategies match", async ({ page }) => {
  const main = await openPortfolio(page);
  const backtest = main.getByRole("region", { name: "Rebalancing backtest" });
  await expect(metric(backtest, "rebalance_count:rebalanced")).toHaveAttribute("data-status", "ok", COLD);

  await backtest.getByLabel("Rebalancing rule").selectOption("drift");
  await backtest.getByLabel("Drift threshold (%)").fill("50");

  await expect(metric(backtest, "rebalance_count:rebalanced")).toContainText("0");
  await expect(metric(backtest, "turnover:rebalanced")).toContainText("0.00%");
  for (const id of RISK_METRICS) {
    const held = (await metric(backtest, `${id}:buy_and_hold`).textContent()) ?? "";
    await expect(metric(backtest, `${id}:rebalanced`)).toHaveText(held.replace("Buy and hold", "Rebalanced"));
  }

  await backtest.getByLabel("Drift threshold (%)").fill("0");
  await expect(backtest.getByTestId("field-error-drift_threshold")).toContainText("above 0%");
});

test("the efficient frontier marks the max-Sharpe, min-variance and current portfolios", async ({ page }) => {
  const main = await openPortfolio(page);
  const frontier = main.getByRole("region", { name: "Efficient frontier" });

  const chart = frontier.getByRole("img", { name: /efficient frontier/i });
  await expect(chart).toBeVisible(COLD);
  for (const who of ["max_sharpe", "min_variance", "current"]) {
    await expect(frontier.locator(`[data-frontier-point="${who}"]`)).toHaveCount(1);
  }
  await expect(frontier.getByTestId("demo-badge")).toContainText("Demo data");

  // Weights are long-only and add up to 100% for every suggested portfolio.
  for (const who of ["max_sharpe", "min_variance", "current"]) {
    let total = 0;
    for (const ticker of ["DEMO-A", "DEMO-B", "DEMO-E"]) {
      const cell = metric(frontier, `weight:${ticker}:${who}`);
      await expect(cell).toHaveAttribute("data-status", "ok");
      const w = percent(await cell.textContent());
      expect(w).toBeGreaterThanOrEqual(0);
      total += w;
    }
    expect(total).toBeCloseTo(100, 0);
  }
  const minVol = percent(await metric(frontier, "volatility:min_variance").textContent());
  for (const who of ["max_sharpe", "current"]) {
    expect(percent(await metric(frontier, `volatility:${who}`).textContent())).toBeGreaterThanOrEqual(minVol);
  }
  await expect(frontier.getByRole("cell", { name: "DEMO-A" })).toBeVisible();

  // The frontier follows the demo portfolio's holdings.
  await main.getByRole("button", { name: "60/40" }).click();
  await expect(frontier.getByRole("cell", { name: "DEMO-C" })).toBeVisible();
  await expect(metric(frontier, "weight:DEMO-C:current")).toContainText("60.00%");
});

test("a frontier with a single holding explains that it needs two", async ({ page }) => {
  const main = await openPortfolio(page);
  const frontier = main.getByRole("region", { name: "Efficient frontier" });
  await expect(metric(frontier, "volatility:min_variance")).toHaveAttribute("data-status", "ok", COLD);

  await main.getByRole("button", { name: "Remove holding 3" }).click();
  await main.getByRole("button", { name: "Remove holding 2" }).click();
  await main.getByLabel("Weight 1 (%)").fill("100");

  await expect(frontier.getByTestId("error-notice")).toContainText("at least two holdings");
});
