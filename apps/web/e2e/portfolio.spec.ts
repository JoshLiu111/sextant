import { expect, test, type Page } from "@playwright/test";

const PERCENT_METRICS = ["annualized_return", "annualized_volatility", "max_drawdown", "var", "cvar"];
const RATIO_METRICS = ["sharpe", "sortino", "beta"];

async function openPortfolio(page: Page) {
  await page.goto("/portfolio");
  const main = page.getByRole("main");
  await expect(main.getByRole("heading", { level: 1, name: "My Portfolio" })).toBeVisible();
  return main;
}

type Main = Awaited<ReturnType<typeof openPortfolio>>;
const metric = (main: Main, id: string) => main.locator(`[data-metric-value="${id}"]`);

test("smoke: open the page, submit the defaults, see the results and the Demo badge", async ({ page }) => {
  const main = await openPortfolio(page);

  await main.getByRole("button", { name: "Calculate" }).click();

  const results = main.getByTestId("results");
  for (const who of ["portfolio", "benchmark"]) {
    for (const id of PERCENT_METRICS) {
      await expect(metric(results, `${id}:${who}`)).toHaveAttribute("data-status", "ok");
      await expect(metric(results, `${id}:${who}`)).toContainText("%");
    }
    for (const id of RATIO_METRICS) {
      await expect(metric(results, `${id}:${who}`)).toHaveAttribute("data-status", "ok");
      await expect(metric(results, `${id}:${who}`)).toContainText(/\d\.\d{2}/);
    }
  }
  const chart = main.getByRole("img", { name: /cumulative return/i });
  await expect(chart).toBeVisible();
  await chart.hover();
  await expect(main.getByTestId("chart-tooltip")).toContainText("Portfolio");
  await expect(main.getByTestId("chart-tooltip")).toContainText("DEMO-MKT");
  await expect(main.getByTestId("demo-badge")).toContainText("Demo data");
  await expect(main.getByTestId("calculation-id")).toContainText("calc_");
  await expect(page.getByRole("contentinfo").locator('[data-attribution="demo"]')).toBeVisible();
});

test("a preset loads its holdings with one click", async ({ page }) => {
  const main = await openPortfolio(page);
  await expect(metric(main, "annualized_volatility:portfolio")).toHaveAttribute("data-status", "ok");
  const before = await metric(main, "annualized_volatility:portfolio").textContent();

  await main.getByRole("button", { name: "60/40" }).click();

  await expect(main.getByLabel("Ticker 1")).toHaveValue("DEMO-C");
  await expect(main.getByLabel("Weight 1 (%)")).toHaveValue("60");
  await expect(main.getByLabel("Ticker 2")).toHaveValue("DEMO-E");
  await expect(main.getByLabel("Weight 2 (%)")).toHaveValue("40");
  await expect(main.getByLabel("Ticker 3")).toHaveCount(0);
  await expect(metric(main, "annualized_volatility:portfolio")).not.toHaveText(before ?? "");

  await main.getByRole("button", { name: "All Weather" }).click();
  await expect(main.getByLabel("Ticker 4")).toBeVisible();
  await expect(main.getByTestId("weight-total")).toContainText("100%");
});

test("weights that do not add up to 100% show a clear error", async ({ page }) => {
  const main = await openPortfolio(page);
  await expect(metric(main, "annualized_volatility:portfolio")).toHaveAttribute("data-status", "ok");

  await main.getByLabel("Weight 1 (%)").fill("10");

  await expect(main.getByTestId("field-error-holdings")).toContainText("Weights must add up to 100%");
  await expect(main.getByTestId("weight-total")).not.toContainText("100%");
});

test("a holding can be added, edited and removed", async ({ page }) => {
  const main = await openPortfolio(page);
  await expect(metric(main, "annualized_volatility:portfolio")).toHaveAttribute("data-status", "ok");
  await main.getByRole("button", { name: "60/40" }).click();

  await main.getByRole("button", { name: "Add holding" }).click();
  await main.getByLabel("Ticker 3").fill("DEMO-ZZ");
  await main.getByLabel("Weight 1 (%)").fill("50");
  await main.getByLabel("Weight 3 (%)").fill("10");

  await expect(main.getByTestId("field-error-holdings.2.ticker")).toContainText("Unknown ticker DEMO-ZZ");
  await expect(main.getByLabel("Ticker 3")).toHaveAttribute("aria-invalid", "true");

  await main.getByRole("button", { name: "Remove holding 3" }).click();
  await main.getByLabel("Weight 1 (%)").fill("60");
  await expect(main.getByTestId("field-error-holdings.2.ticker")).toHaveCount(0);
  await expect(metric(main, "annualized_volatility:portfolio")).toHaveAttribute("data-status", "ok");
  await expect(main.getByTestId("error-notice")).toHaveCount(0);
});

test.describe("mobile width", () => {
  test.use({ viewport: { width: 375, height: 740 } });

  test("the page fits without horizontal scroll", async ({ page }) => {
    const main = await openPortfolio(page);
    await expect(metric(main, "max_drawdown:portfolio")).toHaveAttribute("data-status", "ok");

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(0);
  });
});
