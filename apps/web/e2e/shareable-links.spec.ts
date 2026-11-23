import { expect, test, type Locator, type Page } from "@playwright/test";

// Spec story 10: every tool's inputs live in the URL query string, so a copied
// address bar reproduces the same inputs and results. Missing params fall back
// to the tool's defaults; bad ones show the tool's normal validation error.

const metric = (scope: Locator, id: string) => scope.locator(`[data-metric-value="${id}"]`);

async function open(page: Page, url: string, h1: string) {
  await page.goto(url);
  const main = page.getByRole("main");
  await expect(main.getByRole("heading", { level: 1, name: h1 })).toBeVisible();
  return main;
}

test.describe("Options Calculator", () => {
  test("a link with non-default inputs shows results computed from them", async ({ page }) => {
    // S = 110 (others default: K = 100, T = 1, sigma = 20%, r = 5%, q = 0) -> call 17.66.
    const main = await open(page, "/options?spot=110", "Options Calculator");
    await expect(main.getByLabel("Spot price")).toHaveValue("110");
    await expect(main.getByLabel("Strike price")).toHaveValue("100");
    await expect(metric(main, "call_price")).toContainText("17.66");
  });

  test("submitting writes the inputs to the URL", async ({ page }) => {
    const main = await open(page, "/options", "Options Calculator");
    await expect(metric(main, "call_price")).toContainText("10.45");
    await main.getByLabel("Volatility").fill("30");
    await main.getByRole("button", { name: "Calculate" }).click();
    await expect(page).toHaveURL(/[?&]volatility=30(&|$)/);
    await expect(page).toHaveURL(/[?&]spot=100(&|$)/);

    await page.reload();
    await expect(main.getByLabel("Volatility")).toHaveValue("30");
    await expect(metric(main, "call_price")).toContainText("14.23");
  });

  test("an out-of-range value shows the normal validation error", async ({ page }) => {
    const main = await open(page, "/options?volatility=-5", "Options Calculator");
    await expect(main.getByTestId("field-error-volatility")).toBeVisible();
  });
});

test.describe("Valuation Calculator", () => {
  test("a link with non-default inputs shows results computed from them", async ({ page }) => {
    // MSFT with 8% growth (other assumptions default): $178.68 per share.
    const main = await open(page, "/valuation?ticker=msft&growth_rate=8", "Valuation Calculator");
    await expect(main.getByLabel("Ticker")).toHaveValue("MSFT");
    await expect(main.getByLabel("Growth rate (%)")).toHaveValue("8");
    await expect(metric(main, "intrinsic_value_per_share")).toContainText("$178.68");
  });

  test("submitting writes the ticker and every assumption to the URL", async ({ page }) => {
    const main = await open(page, "/valuation", "Valuation Calculator");
    await expect(metric(main, "intrinsic_value_per_share")).toContainText("$158.11");
    await main.getByLabel("Growth rate (%)").fill("8");
    await main.getByRole("button", { name: "Value company" }).click();
    await expect(page).toHaveURL(/[?&]ticker=MSFT(&|$)/);
    await expect(page).toHaveURL(/[?&]growth_rate=8(&|$)/);
    await expect(page).toHaveURL(/[?&]terminal_growth=2\.5(&|$)/);

    await page.reload();
    await expect(metric(main, "intrinsic_value_per_share")).toContainText("$178.68");
  });

  test("an out-of-range value shows the normal validation error", async ({ page }) => {
    const main = await open(page, "/valuation?forecast_years=50", "Valuation Calculator");
    await expect(main.getByTestId("field-error-forecast_years")).toBeVisible();
  });
});

test.describe("Risk & Performance", () => {
  test("a link with non-default inputs shows results computed from them", async ({ page }) => {
    // DEMO-D's injected crash: exactly 45% from 2022-02-28 to the 2022-04-11 bottom.
    const main = await open(page, "/risk?tickers=DEMO-D&start=2022-02-28&end=2022-04-11", "Risk & Performance");
    await expect(main.getByLabel("Tickers")).toHaveValue("DEMO-D");
    await expect(main.getByLabel("Benchmark")).toHaveValue("DEMO-MKT");
    await expect(metric(main, "max_drawdown:DEMO-D")).toContainText("45.00%");
    await expect(metric(main, "max_drawdown:DEMO-A")).toHaveCount(0);
  });

  test("submitting writes the inputs to the URL", async ({ page }) => {
    const main = await open(page, "/risk", "Risk & Performance");
    await expect(metric(main, "max_drawdown:DEMO-A")).toHaveAttribute("data-status", "ok");
    await main.getByLabel("Tickers").fill("DEMO-D");
    await main.getByRole("button", { name: "Calculate" }).click();
    await expect(page).toHaveURL(/[?&]tickers=DEMO-D(&|$)/);
    await expect(page).toHaveURL(/[?&]benchmark=DEMO-MKT(&|$)/);
  });

  test("an out-of-range value shows the normal validation error", async ({ page }) => {
    const main = await open(page, "/risk?confidence=200", "Risk & Performance");
    await expect(main.getByTestId("field-error-confidence")).toBeVisible();
  });
});

test.describe("My Portfolio (demo)", () => {
  test("a link with non-default inputs shows results computed from them", async ({ page }) => {
    const main = await open(page, "/portfolio?holdings=DEMO-D:100&start=2022-02-28&end=2022-04-11", "My Portfolio");
    const demo = main.getByRole("region", { name: "Demo portfolio" });
    await expect(demo.getByLabel("Ticker 1")).toHaveValue("DEMO-D");
    await expect(demo.getByLabel("Weight 1 (%)")).toHaveValue("100");
    await expect(demo.getByLabel("Ticker 2")).toHaveCount(0);
    await expect(metric(demo, "max_drawdown:portfolio")).toContainText("45.00%");
  });

  test("submitting writes the demo inputs to the URL", async ({ page }) => {
    const main = await open(page, "/portfolio", "My Portfolio");
    const demo = main.getByRole("region", { name: "Demo portfolio" });
    await expect(metric(demo, "max_drawdown:portfolio")).toHaveAttribute("data-status", "ok");
    await demo.getByRole("button", { name: "60/40" }).click();
    await demo.getByRole("button", { name: "Calculate" }).click();
    await expect(page).toHaveURL(/[?&]holdings=DEMO-C:60,DEMO-E:40(&|$)/);
  });

  test("weights that don't add up show the normal validation error", async ({ page }) => {
    const main = await open(page, "/portfolio?holdings=DEMO-A:50", "My Portfolio");
    await expect(main.getByTestId("field-error-holdings")).toContainText("add up to 50%");
  });
});
