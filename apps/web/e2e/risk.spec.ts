import { expect, test, type Page } from "@playwright/test";

// Defaults: DEMO-A, DEMO-B, DEMO-D vs DEMO-MKT, 2021-01-01 to 2025-12-31 (synthetic demo data).
const DEFAULT_TICKERS = ["DEMO-A", "DEMO-B", "DEMO-D", "DEMO-MKT"];
const METRICS = ["annualized_return", "annualized_volatility", "max_drawdown"];

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
    for (const id of METRICS) {
      await expect(metric(results, `${id}:${ticker}`)).toHaveAttribute("data-status", "ok");
      await expect(metric(results, `${id}:${ticker}`)).toContainText("%");
    }
  }
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
  await expect(chart.getByTestId("chart-marker")).toHaveCount(2);
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

  const cards = main.locator("[data-metric]");
  await expect(cards).toHaveCount(METRICS.length);
  for (let i = 0; i < METRICS.length; i++) {
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
