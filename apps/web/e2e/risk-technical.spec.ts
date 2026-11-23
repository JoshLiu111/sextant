import { expect, test, type Page } from "@playwright/test";

// The panel follows the Risk & Performance selection: DEMO-A, DEMO-B, DEMO-D vs DEMO-MKT,
// 2021-01-01 to 2025-12-31 (synthetic demo data trades Mon-Fri, so 2021-01-01 is the first date shown).

async function openRisk(page: Page) {
  await page.goto("/risk");
  const main = page.getByRole("main");
  await expect(main.locator('[data-metric-value="annualized_return:DEMO-A"]')).toHaveAttribute("data-status", "ok", {
    timeout: 30_000,
  });
  return main;
}

type Main = Awaited<ReturnType<typeof openRisk>>;
const priceChart = (main: Main) => main.getByRole("img", { name: /^Price chart/ });
const cell = (main: Main, a: string, b: string) => main.locator(`[data-correlation="${a}:${b}"]`);

test("the price chart shows the default indicators, defined from the first visible date", async ({ page }) => {
  const main = await openRisk(page);

  const chart = priceChart(main);
  await expect(chart).toBeVisible();
  await expect(main.getByTestId("indicator-legend-price")).toContainText("SMA (50)");
  await expect(main.getByRole("img", { name: /^RSI panel/ })).toBeVisible();

  // Hover left of the plot, which snaps to the first visible date: it already has an SMA value,
  // because the lookback before the start date was fetched.
  await chart.hover({ position: { x: 20, y: 60 } });
  const tooltip = main.getByTestId("chart-tooltip");
  await expect(tooltip).toContainText("2021-01-01");
  await expect(tooltip).toContainText(/SMA \(50\): [\d,]+\.\d{2}/);
});

test("indicators toggle on and off and their parameters change the chart", async ({ page }) => {
  const main = await openRisk(page);
  await expect(main.getByTestId("indicator-legend-price")).toContainText("SMA (50)");

  await main.getByLabel("SMA window (days)").fill("20");
  await expect(main.getByTestId("indicator-legend-price")).toContainText("SMA (20)");

  await main.getByLabel("Bollinger Bands", { exact: true }).check();
  await expect(main.getByTestId("indicator-legend-price")).toContainText("Upper band");

  await main.getByLabel("MACD", { exact: true }).check();
  await expect(main.getByRole("img", { name: /^MACD panel/ })).toBeVisible();

  await main.getByLabel("RSI", { exact: true }).uncheck();
  await expect(main.getByRole("img", { name: /^RSI panel/ })).toHaveCount(0);

  await main.getByLabel("Indicator chart for").selectOption("DEMO-B");
  await expect(main.getByTestId("indicator-legend-price")).toContainText("DEMO-B");
});

test("invalid indicator parameters are shown inline", async ({ page }) => {
  const main = await openRisk(page);
  await main.getByLabel("MACD", { exact: true }).check();

  await main.getByLabel("MACD slow window (days)").fill("5");

  await expect(main.getByTestId("field-error-macd_slow")).toContainText("longer than the fast window");
});

test("every indicator panel and the heatmap have an explainer", async ({ page }) => {
  const main = await openRisk(page);
  const panel = main.getByTestId("technical-analysis");
  for (const label of ["Bollinger Bands", "MACD", "EMA"]) await panel.getByLabel(label, { exact: true }).check();

  for (const name of ["Moving averages", "Bollinger Bands", "RSI", "MACD", "Correlation heatmap"]) {
    await expect(panel.getByTestId("explainer").filter({ hasText: `About ${name}` })).toHaveCount(1);
  }
});

test("the heatmap is hoverable and the index hugger is highly correlated with the benchmark", async ({ page }) => {
  const main = await openRisk(page);
  await main.getByLabel("Tickers").fill("DEMO-A, DEMO-C");

  const hugger = cell(main, "DEMO-C", "DEMO-MKT");
  await expect(hugger).toHaveAttribute("data-status", "ok");
  await expect(cell(main, "DEMO-A", "DEMO-A")).toContainText("1.00");

  await hugger.hover();
  const tooltip = main.getByTestId("heatmap-tooltip");
  await expect(tooltip).toContainText("DEMO-C vs DEMO-MKT");
  const value = parseFloat(/(-?\d\.\d+)/.exec((await tooltip.textContent()) ?? "")?.[1] ?? "NaN");
  expect(value).toBeGreaterThan(0.9);
});

test.describe("mobile width", () => {
  test.use({ viewport: { width: 375, height: 740 } });

  test("the indicator charts and heatmap fit without horizontal scroll", async ({ page }) => {
    const main = await openRisk(page);
    await expect(cell(main, "DEMO-MKT", "DEMO-A")).toHaveAttribute("data-status", "ok");
    await expect(priceChart(main)).toBeVisible();

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(0);
  });
});
