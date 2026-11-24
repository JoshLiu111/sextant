import { expect, test, type Page } from "@playwright/test";
import { openRiskTab } from "./risk-helpers";

// Defaults: DEMO-A, DEMO-B, DEMO-D vs DEMO-MKT, 2021-01-01 to 2025-12-31, 95% (synthetic demo data).
const METHODS = ["backtest_var", "backtest_parametric_var", "backtest_cornish_fisher_var"];
// The first result can be slow when every worker opens /risk at once (dev compile, cold cache).
const FIRST_RESULT = 20_000;

async function openRisk(page: Page) {
  await page.goto("/risk");
  const main = page.getByRole("main");
  await expect(main.getByRole("heading", { level: 1, name: "Risk & Performance" })).toBeVisible();
  await openRiskTab(main, "Model checks");
  const checks = main.getByTestId("model-checks");
  await expect(checks.locator('[data-backtest="backtest_var:DEMO-A"]')).toHaveAttribute("data-status", "ok", {
    timeout: FIRST_RESULT,
  });
  return checks;
}

test("the VaR backtest shows breaches, expected breaches, Kupiec and a reading for every method", async ({ page }) => {
  const checks = await openRisk(page);

  const table = checks.getByRole("table", { name: /VaR backtest/ });
  await expect(table).toBeVisible();
  for (const header of ["Breaches", "Expected", "Kupiec LR", "p-value", "Reading"]) {
    await expect(table.getByRole("columnheader", { name: header })).toBeVisible();
  }
  for (const id of METHODS) {
    const row = table.locator(`[data-backtest="${id}:DEMO-A"]`);
    await expect(row).toHaveAttribute("data-status", "ok");
    await expect(row.getByTestId("reading")).toHaveText(/^(Accept|Reject) at 95%$/);
  }
  // 1,303 returns less the 250-day window = 1,053 tested days; 5% of them is 52.65.
  await expect(table.locator('[data-backtest="backtest_var:DEMO-A"]')).toContainText("52.7");
  await expect(checks.getByTestId("explainer")).toHaveCount(2);
});

test("the backtest follows the ticker picker and the confidence level", async ({ page }) => {
  const checks = await openRisk(page);
  const main = page.getByRole("main");
  await expect(checks.locator('[data-backtest="backtest_var:DEMO-A"]')).toHaveAttribute("data-status", "ok");

  await checks.getByLabel("Model checks for").selectOption("DEMO-B");
  await main.getByLabel("VaR confidence level (%)").fill("99");

  const row = checks.locator('[data-backtest="backtest_parametric_var:DEMO-B"]');
  await expect(row.getByTestId("reading")).toHaveText(/at 99%$/);
});

test("the GARCH chart shows the conditional volatility with the fitted parameters", async ({ page }) => {
  const checks = await openRisk(page);

  const chart = checks.getByRole("img", { name: /GARCH/ });
  await expect(chart).toBeVisible();
  const params = checks.getByTestId("garch-parameters");
  for (const name of ["ω (daily)", "α", "β", "α + β", "Long-run volatility", "Next-day volatility"]) {
    await expect(params.getByText(name, { exact: true })).toBeVisible();
  }
  await expect(params.locator('[data-garch="persistence"]')).toHaveText(/^0\.9\d{3}$/);

  await chart.hover();
  await expect(page.getByTestId("chart-tooltip")).toContainText("DEMO-A");
});

test("a range too short for the fit shows the reason instead of the GARCH chart", async ({ page }) => {
  const checks = await openRisk(page);
  await expect(checks.getByRole("img", { name: /GARCH/ })).toBeVisible();

  await page.getByRole("main").getByLabel("Start date").fill("2025-06-01");

  await expect(checks.getByTestId("garch-missing")).toContainText("needs at least 250 daily returns");
  await expect(checks.locator('[data-backtest="backtest_var:DEMO-A"]')).toHaveAttribute("data-status", "missing_data");
  await openRiskTab(page.getByRole("main"), "Overview");
  await expect(page.getByRole("main").locator('[data-metric-value="var:DEMO-A"]')).toHaveAttribute(
    "data-status",
    "ok",
  );
});
