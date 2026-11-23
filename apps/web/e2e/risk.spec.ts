import { expect, test, type Page } from "@playwright/test";

// Defaults: DEMO-A, DEMO-B, DEMO-D vs DEMO-MKT, 2021-01-01 to 2025-12-31 (synthetic demo data).
const DEFAULT_TICKERS = ["DEMO-A", "DEMO-B", "DEMO-D", "DEMO-MKT"];
const VAR_METRICS = [
  "var",
  "cvar",
  "parametric_var",
  "parametric_cvar",
  "cornish_fisher_var",
  "cornish_fisher_cvar",
];
const PERCENT_METRICS = [
  "annualized_return",
  "annualized_volatility",
  "max_drawdown",
  ...VAR_METRICS,
  "treynor",
  "alpha",
  "upside_capture",
  "downside_capture",
];
const RATIO_METRICS = ["sharpe", "sortino", "beta"];
// The benchmark has no active return, so its information ratio is missing_data by design.
const ACTIVE_METRICS = ["information_ratio"];
const METRICS = [...PERCENT_METRICS, ...RATIO_METRICS, ...ACTIVE_METRICS];

async function openRisk(page: Page) {
  await page.goto("/risk");
  const main = page.getByRole("main");
  await expect(main.getByRole("heading", { level: 1, name: "Risk & Performance" })).toBeVisible();
  return main;
}

type Main = Awaited<ReturnType<typeof openRisk>>;
const metric = (main: Main, id: string) => main.locator(`[data-metric-value="${id}"]`);

test("smoke: open the page, submit the defaults, see the results and the Demo badge", async ({ page }) => {
  const main = await openRisk(page);

  await main.getByRole("button", { name: "Calculate" }).click();

  const results = main.getByTestId("results");
  for (const ticker of DEFAULT_TICKERS) {
    for (const id of PERCENT_METRICS) {
      await expect(metric(results, `${id}:${ticker}`)).toHaveAttribute("data-status", "ok");
      await expect(metric(results, `${id}:${ticker}`)).toContainText("%");
    }
    for (const id of RATIO_METRICS) {
      await expect(metric(results, `${id}:${ticker}`)).toHaveAttribute("data-status", "ok");
      await expect(metric(results, `${id}:${ticker}`)).toContainText(/\d\.\d{2}/);
    }
  }
  for (const ticker of DEFAULT_TICKERS.filter((t) => t !== "DEMO-MKT")) {
    await expect(metric(results, `information_ratio:${ticker}`)).toHaveAttribute("data-status", "ok");
  }
  await expect(metric(results, "information_ratio:DEMO-MKT")).toHaveAttribute("data-status", "missing_data");
  await expect(main.getByTestId("demo-badge")).toBeVisible();
  await expect(main.getByTestId("demo-badge")).toContainText("Demo data");
  await expect(main.getByTestId("calculation-id")).toContainText("calc_");
});

test("the underwater chart marks the start and end of the max drawdown", async ({ page }) => {
  const main = await openRisk(page);

  await main.getByLabel("Underwater chart for").selectOption("DEMO-D");

  const chart = main.getByRole("img", { name: /underwater/i });
  await expect(chart).toBeVisible();
  // DEMO-D's injected crash bottoms on 2022-04-11, the deepest point in the default range.
  // The third marker is its recovery (see risk-timescale.spec.ts).
  await expect(chart.getByTestId("chart-marker")).toHaveCount(3);
  await expect(chart.getByText("Max drawdown start")).toBeAttached();
  await expect(chart.getByText("Max drawdown end")).toBeAttached();
  await expect(main.getByTestId("drawdown-window")).toContainText("2022-04-11");

  await chart.hover();
  await expect(main.getByTestId("chart-tooltip")).toContainText("DEMO-D");
});

test("the footer credits the demo data", async ({ page }) => {
  await openRisk(page);

  await expect(page.getByRole("contentinfo").locator('[data-attribution="demo"]')).toBeVisible();
});

test("an unknown ticker is shown inline next to the tickers input", async ({ page }) => {
  const main = await openRisk(page);
  await expect(metric(main, "annualized_return:DEMO-A")).toHaveAttribute("data-status", "ok");

  await main.getByLabel("Tickers").fill("DEMO-A, DEMO-ZZ");

  await expect(main.getByTestId("field-error-tickers")).toContainText("Unknown ticker DEMO-ZZ");
  await expect(main.getByLabel("Tickers")).toHaveAttribute("aria-invalid", "true");
  await expect(main.getByRole("heading", { level: 1, name: "Risk & Performance" })).toBeVisible();
});

test("a reversed date range is shown inline next to the end date", async ({ page }) => {
  const main = await openRisk(page);
  await expect(metric(main, "annualized_return:DEMO-A")).toHaveAttribute("data-status", "ok");

  await main.getByLabel("End date").fill("2020-01-01");

  await expect(main.getByTestId("field-error-end")).toContainText("End date must be after the start date.");
});

test("VaR and CVaR update when the confidence level changes", async ({ page }) => {
  const main = await openRisk(page);
  const varB = metric(main, "var:DEMO-B");
  await expect(varB).toHaveAttribute("data-status", "ok");
  await expect(main.getByLabel("VaR confidence level (%)")).toHaveValue("95");
  const at95 = await varB.textContent();
  const cvarAt95 = await metric(main, "cvar:DEMO-B").textContent();

  await main.getByLabel("VaR confidence level (%)").fill("99");

  await expect(varB).not.toHaveText(at95 ?? "");
  await expect(metric(main, "cvar:DEMO-B")).not.toHaveText(cvarAt95 ?? "");
  const percent = (text: string | null) => parseFloat(/(-?[\d.]+)%/.exec(text ?? "")?.[1] ?? "NaN");
  expect(percent(await varB.textContent())).toBeGreaterThan(percent(at95));
});

test("changing the confidence level recomputes every VaR and CVaR variant", async ({ page }) => {
  const main = await openRisk(page);
  const percent = (text: string | null) => parseFloat(/(-?[\d.]+)%/.exec(text ?? "")?.[1] ?? "NaN");
  await expect(metric(main, "cornish_fisher_cvar:DEMO-B")).toHaveAttribute("data-status", "ok");
  const at95: Record<string, number> = {};
  for (const id of VAR_METRICS) at95[id] = percent(await metric(main, `${id}:DEMO-B`).textContent());

  await main.getByLabel("VaR confidence level (%)").fill("99");

  for (const id of VAR_METRICS) {
    await expect
      .poll(async () => percent(await metric(main, `${id}:DEMO-B`).textContent()), { message: id })
      .toBeGreaterThan(at95[id]);
  }
});

test("an out-of-range confidence level is shown inline", async ({ page }) => {
  const main = await openRisk(page);
  await expect(metric(main, "var:DEMO-A")).toHaveAttribute("data-status", "ok");

  await main.getByLabel("VaR confidence level (%)").fill("100");

  await expect(main.getByTestId("field-error-confidence")).toContainText("between 50% and 99.9%");
});

test("a data source outage asks the visitor to retry", async ({ page }) => {
  await page.route("**/api/compute/risk/metrics", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({
        error: { code: "source_unavailable", message: "The data source is down.", fields: {} },
      }),
    }),
  );
  const main = await openRisk(page);

  const notice = main.getByTestId("error-notice");
  await expect(notice).toContainText("Data source temporarily unavailable, please retry.");
});

test("every metric has an explainer", async ({ page }) => {
  const main = await openRisk(page);
  await expect(metric(main, "max_drawdown:DEMO-A")).toHaveAttribute("data-status", "ok");

  for (const id of METRICS) await expect(main.locator(`[data-metric="${id}"]`)).toHaveCount(1);
  // Every card on the page (including the distribution's skewness and kurtosis) has one explainer.
  const cards = main.locator("[data-metric]");
  const count = await cards.count();
  expect(count).toBeGreaterThanOrEqual(METRICS.length);
  for (let i = 0; i < count; i++) {
    await expect(cards.nth(i).getByTestId("explainer")).toHaveCount(1);
  }
  await expect(main.locator("[data-metric-value]")).toHaveCount(
    await main.locator("[data-metric] [data-metric-value]").count(),
  );
});

test.describe("mobile width", () => {
  test.use({ viewport: { width: 375, height: 740 } });

  test("the page fits without horizontal scroll", async ({ page }) => {
    const main = await openRisk(page);
    await expect(metric(main, "max_drawdown:DEMO-A")).toHaveAttribute("data-status", "ok");

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(0);
  });
});
