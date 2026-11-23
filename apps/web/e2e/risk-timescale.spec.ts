import { expect, test, type Page } from "@playwright/test";

// Risk & Performance time-scale views (#24): return periods, rolling curves,
// the marked underwater chart and the return distribution.

async function openRisk(page: Page) {
  await page.goto("/risk");
  const main = page.getByRole("main");
  await expect(main.getByRole("heading", { level: 1, name: "Risk & Performance" })).toBeVisible();
  // Wait for the first result before changing inputs (hydration can race a fill).
  await expect(metric(main, "annualized_volatility:DEMO-A")).toHaveAttribute("data-status", "ok");
  return main;
}

type Main = Awaited<ReturnType<typeof openRisk>>;
const metric = (main: Main, id: string) => main.locator(`[data-metric-value="${id}"]`);

test("switching the return period recomputes the period statistics", async ({ page }) => {
  const main = await openRisk(page);
  const vol = metric(main, "annualized_volatility:DEMO-B");
  const daily = await vol.textContent();
  const dailyVar = await metric(main, "var:DEMO-B").textContent();
  const dailyReturn = await metric(main, "annualized_return:DEMO-B").textContent();
  await expect(main.getByTestId("period-note")).toContainText("daily returns");

  await main.getByLabel("Return period").selectOption("monthly");

  await expect(main.getByTestId("period-note")).toContainText("monthly returns");
  await expect(main.getByTestId("period-note")).toContainText("12");
  await expect(vol).not.toHaveText(daily ?? "");
  await expect(metric(main, "var:DEMO-B")).not.toHaveText(dailyVar ?? "");
  // Annualized return describes the whole path, so it does not depend on the period.
  await expect(metric(main, "annualized_return:DEMO-B")).toHaveText(dailyReturn ?? "");
});

test("rolling curves are hoverable and their window is adjustable", async ({ page }) => {
  const main = await openRisk(page);
  const rolling = main.getByRole("region", { name: "Rolling metrics" });

  for (const name of [/rolling volatility/i, /rolling sharpe/i, /rolling beta/i]) {
    await expect(rolling.getByRole("img", { name })).toBeVisible();
  }
  await expect(rolling.getByTestId("rolling-window-note")).toContainText("63 trading days");

  await rolling.getByRole("img", { name: /rolling volatility/i }).hover();
  const tooltip = rolling.getByTestId("chart-tooltip");
  await expect(tooltip).toContainText("DEMO-A");
  await expect(tooltip).toContainText("%");

  await main.getByLabel("Rolling window (trading days)").fill("126");
  await expect(rolling.getByTestId("rolling-window-note")).toContainText("126 trading days");

  await main.getByLabel("Rolling window (trading days)").fill("5");
  await expect(main.getByTestId("field-error-rolling_window")).toContainText("between 20 and 756");
});

test("the underwater chart marks the injected crash as the max drawdown, with its recovery", async ({ page }) => {
  const main = await openRisk(page);

  await main.getByLabel("Underwater chart for").selectOption("DEMO-D");

  const chart = main.getByRole("img", { name: /underwater/i });
  await expect(chart.getByTestId("chart-marker")).toHaveCount(3);
  await expect(chart.getByText("Max drawdown start")).toBeAttached();
  await expect(chart.getByText("Max drawdown end")).toBeAttached();
  await expect(chart.getByText("Recovered")).toBeAttached();
  const band = chart.getByTestId("chart-band");
  await expect(band).toHaveCount(1);
  await expect(main.getByTestId("drawdown-window")).toContainText("2022-04-11");
  const end = await band.getAttribute("data-band-end");
  await expect(main.getByTestId("drawdown-window")).toContainText(`recovered ${end}`);
});

test("the return distribution shows a histogram and positive excess kurtosis for the fat-tailed ticker", async ({
  page,
}) => {
  const main = await openRisk(page);
  await main.getByLabel("Tickers").fill("DEMO-A, DEMO-F");
  const kurtosis = metric(main, "excess_kurtosis:DEMO-F");
  await expect(kurtosis).toHaveAttribute("data-status", "ok");
  // The card shows the ticker label, then the value with two decimals.
  const shown = /(-?\d+\.\d{2})/.exec((await kurtosis.textContent()) ?? "")?.[1];
  expect(parseFloat(shown ?? "NaN")).toBeGreaterThan(0);
  await expect(metric(main, "skewness:DEMO-F")).toHaveAttribute("data-status", "ok");

  const distribution = main.getByRole("region", { name: "Return distribution" });
  await distribution.getByLabel("Distribution for").selectOption("DEMO-F");
  const histogram = distribution.getByRole("img", { name: /histogram/i });
  await expect(histogram).toBeVisible();
  expect(await histogram.getByTestId("histogram-bar").count()).toBeGreaterThan(5);

  await histogram.hover();
  await expect(distribution.getByTestId("chart-tooltip")).toContainText("returns");
});
