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
  await expect(results.getByTestId("demo-badge")).toContainText("Demo data");
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

// The demo portfolio's results are split into tabs (issue #70), with the open tab in the URL.
test.describe("result tabs", () => {
  const FIGURES = ["annualized_return", "annualized_volatility", "max_drawdown", "sharpe"];
  const top = async (l: ReturnType<Main["locator"]>) => (await l.boundingBox())?.y ?? 0;

  test("the overview opens first: key figures, then the chart, then the metric cards", async ({ page }) => {
    const main = await openPortfolio(page);
    const tabs = main.getByRole("tablist", { name: "Portfolio results" });
    await expect(tabs.getByRole("tab", { name: "Overview" })).toHaveAttribute("aria-selected", "true");

    const overview = main.getByRole("tabpanel", { name: "Overview" });
    const strip = overview.getByTestId("key-figures");
    for (const id of FIGURES) {
      await expect(strip.locator(`[data-key-figure="${id}:portfolio"]`)).toHaveAttribute("data-status", "ok");
    }
    await expect(strip.locator("[data-key-figure]")).toHaveCount(4);
    const chart = overview.getByRole("img", { name: /cumulative return/i });
    await expect(chart).toBeVisible();
    await expect(metric(overview, "sortino:benchmark")).toHaveAttribute("data-status", "ok");

    expect(await top(strip)).toBeLessThan(await top(chart));
    expect(await top(chart)).toBeLessThan(await top(metric(overview, "beta:portfolio")));
  });

  test("each construction view has its own tab, and the tab round-trips through the URL", async ({ page }) => {
    const main = await openPortfolio(page);
    await main.getByRole("tab", { name: "Rebalancing" }).click();
    await expect(page).toHaveURL(/[?&]tab=rebalancing(&|$)/);
    const rebalancing = main.getByRole("tabpanel", { name: "Rebalancing" });
    await expect(rebalancing.getByRole("region", { name: "Rebalancing backtest" })).toBeVisible();
    await expect(main.getByRole("region", { name: "Efficient frontier" })).toHaveCount(0);
    await expect(main.getByTestId("key-figures")).toHaveCount(0);
    // Calculation info stays reachable below the tab panel.
    await expect(main.getByTestId("calculation-id")).toContainText("calc_");

    await page.goto("/portfolio?tab=frontier");
    await expect(main.getByRole("tab", { name: "Efficient frontier" })).toHaveAttribute("aria-selected", "true");
    await expect(main.getByRole("region", { name: "Efficient frontier" })).toBeVisible();
    await expect(main.getByRole("region", { name: "Rebalancing backtest" })).toHaveCount(0);
  });

  test("an unknown tab in the link opens the overview", async ({ page }) => {
    await page.goto("/portfolio?tab=nonsense");
    const main = page.getByRole("main");
    await expect(main.getByRole("tab", { name: "Overview" })).toHaveAttribute("aria-selected", "true");
    await expect(main.getByTestId("key-figures")).toBeVisible();
  });

  test("the input form stays in view on desktop", async ({ page }) => {
    const main = await openPortfolio(page);
    await expect(main.getByRole("form", { name: "Inputs" })).toHaveCSS("position", "sticky");
  });
});
