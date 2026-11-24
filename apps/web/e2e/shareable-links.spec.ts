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

// EDGAR, FRED and Treasury come from the e2e fakes; a cold compute cache is slow.
const COLD = { timeout: 30_000 };

test.describe("Company Health Check", () => {
  test("a link with several companies and a price shows their ratios side by side", async ({ page }) => {
    const main = await open(page, "/company?companies=MSFT:400,AAPL&ticker=JPM", "Company Health Check");
    const ratios = main.getByTestId("ratios");
    await expect(ratios.getByLabel("Compare company 1", { exact: true })).toHaveValue("MSFT");
    await expect(ratios.getByLabel("Share price 1", { exact: true })).toHaveValue("400");
    await expect(ratios.getByLabel("Compare company 2", { exact: true })).toHaveValue("AAPL");
    // The price values only MSFT's latest year; AAPL has none.
    await expect(ratios.locator('[data-metric-value^="price_to_earnings:MSFT:"][data-status="ok"]')).toHaveCount(1, COLD);
    await expect(metric(ratios, "price_to_earnings:AAPL:2026-09-26")).toHaveAttribute("data-status", "missing_data");
    // The statements below follow `ticker`.
    await expect(main.getByLabel("Ticker")).toHaveValue("JPM");
    await expect(main.getByTestId("results").getByRole("heading", { name: /JPMORGAN/i })).toBeVisible(COLD);
  });

  test("submitting each form writes its own inputs to the URL", async ({ page }) => {
    const main = await open(page, "/company", "Company Health Check");
    const ratios = main.getByTestId("ratios");
    await expect(metric(ratios, "current_ratio:AAPL:2026-09-26")).toHaveAttribute("data-status", "ok", COLD);
    await ratios.getByLabel("Share price 1", { exact: true }).fill("250");
    await ratios.getByRole("button", { name: "Show ratios" }).click();
    await expect(page).toHaveURL(/[?&]companies=AAPL:250(&|$)/);

    await main.getByLabel("Ticker").fill("MSFT");
    await main.getByRole("button", { name: "Show statements" }).click();
    await expect(page).toHaveURL(/[?&]ticker=MSFT(&|$)/);
    await expect(page).toHaveURL(/[?&]companies=AAPL:250(&|$)/);
  });

  test("the statements ticker in the URL doesn't leak into the ratios on reload", async ({ page }) => {
    const main = await open(page, "/company", "Company Health Check");
    const ratios = main.getByTestId("ratios");
    await expect(metric(ratios, "current_ratio:AAPL:2026-09-26")).toHaveAttribute("data-status", "ok", COLD);
    await main.getByLabel("Ticker").fill("MSFT");
    await main.getByRole("button", { name: "Show statements" }).click();
    await expect(page).toHaveURL(/[?&]ticker=MSFT(&|$)/);

    await page.reload();
    await expect(main.getByLabel("Ticker")).toHaveValue("MSFT");
    // No `companies` param: the ratios fall back to their default company.
    await expect(ratios.getByLabel("Compare company 1", { exact: true })).toHaveValue("AAPL");
  });

  test("a duplicate company shows the normal validation error", async ({ page }) => {
    const main = await open(page, "/company?companies=AAPL,AAPL", "Company Health Check");
    await expect(main.getByTestId("field-error-companies.1.ticker")).toBeVisible(COLD);
  });
});

test.describe("Macro Dashboard", () => {
  test("a link with a later start date shows history from that date", async ({ page }) => {
    const main = await open(page, "/macro?start=2023-01-01", "Macro Dashboard");
    await expect(main.getByLabel("History from")).toHaveValue("2023-01-01");
    const spread = main.getByRole("img", { name: "10Y–2Y spread history" });
    await expect(spread.getByTestId("chart-band").first()).toBeAttached(COLD);
    // The 2019 inversion is before the start; the long 2022–24 one is cut at it.
    await expect(spread.locator('[data-testid="chart-band"][data-band-start="2019-08-27"]')).toHaveCount(0);
    await expect(spread.locator('[data-testid="chart-band"][data-band-end="2024-08-26"]')).toHaveAttribute(
      "data-band-start",
      "2023-01-03",
    );
  });

  test("submitting writes the start date to the URL", async ({ page }) => {
    const main = await open(page, "/macro", "Macro Dashboard");
    // Wait for a first result so hydration doesn't race the fill.
    await expect(main.getByRole("img", { name: "10Y–2Y spread history" })).toBeVisible(COLD);
    await main.getByLabel("History from").fill("2020-01-01");
    await main.getByRole("button", { name: "Update charts" }).click();
    await expect(page).toHaveURL(/[?&]start=2020-01-01(&|$)/);
  });

  test("an out-of-range start date shows the normal validation error", async ({ page }) => {
    const main = await open(page, "/macro?start=1980-01-01", "Macro Dashboard");
    await expect(main.getByTestId("field-error-start")).toContainText("1990-01-02", COLD);
  });
});

test.describe("Screener", () => {
  type Main = Awaited<ReturnType<typeof open>>;
  const rowTickers = (main: Main) =>
    main
      .getByRole("table", { name: "Screen results" })
      .locator("[data-ticker]")
      .evaluateAll((rows) => rows.map((r) => r.getAttribute("data-ticker")));

  test("a link with criteria and a sort shows the matching companies in that order", async ({ page }) => {
    const main = await open(
      page,
      "/screener?criteria=revenue_growth:min:10,debt_ratio:max:30&sort=ticker&direction=asc",
      "Screener & Calendar",
    );
    const criteria = main.getByRole("group", { name: "Criteria" });
    await expect(criteria.getByLabel("Metric for criterion 2")).toHaveValue("debt_ratio");
    await expect(criteria.getByLabel("Condition for criterion 2")).toHaveValue("max");
    await expect(criteria.getByLabel("Value for criterion 2")).toHaveValue("30");
    await expect(criteria.getByLabel("Metric for criterion 3")).toHaveCount(0);
    await expect(main.getByTestId("screen-summary")).toBeVisible(COLD);
    await expect.poll(() => rowTickers(main)).toEqual(["AMD", "NVDA"]);
  });

  test("running a screen and sorting write the inputs to the URL", async ({ page }) => {
    const main = await open(page, "/screener", "Screener & Calendar");
    await expect(main.getByTestId("screen-summary")).toBeVisible(COLD);
    const criteria = main.getByRole("group", { name: "Criteria" });
    await criteria.getByLabel("Value for criterion 2").fill("75");
    await main.getByRole("button", { name: "Run screen" }).click();
    await expect(page).toHaveURL(/[?&]criteria=revenue_growth:min:10,gross_margin:min:75,roe:min:15(&|$)/);

    await main.getByRole("table", { name: "Screen results" }).getByRole("button", { name: "Ticker" }).click();
    await expect(page).toHaveURL(/[?&]sort=ticker&direction=asc(&|$)/);
    await page.reload();
    await expect.poll(() => rowTickers(main), COLD).toEqual(["ADBE", "LLY", "META"]);
  });

  test("a link to one company's filings shows that company's filings", async ({ page }) => {
    const main = await open(page, "/screener?tab=filings&filings_ticker=AAPL&filings_form=10-K", "Screener & Calendar");
    await expect(main.getByLabel("Company ticker")).toHaveValue("AAPL");
    await expect(main.getByLabel("Form type")).toHaveValue("10-K");
    const filings = main.getByRole("table", { name: "Latest SEC filings" });
    await expect(main.getByTestId("filings-heading")).toContainText("Apple Inc.", COLD);
    await expect(filings.getByRole("row")).toHaveCount(2);
    await expect(filings.getByRole("row").nth(1)).toContainText("10-K - Annual report");
  });

  test("a link to an earnings calendar range and a dividend ticker shows them", async ({ page }) => {
    const main = await open(
      page,
      "/screener?tab=earnings&earnings_tickers=AAPL,MSFT&earnings_start=2026-01-01&earnings_end=2026-06-30&dividends_ticker=JPM",
      "Screener & Calendar",
    );
    await expect(main.getByLabel("Companies")).toHaveValue("AAPL,MSFT");
    await expect(main.getByTestId("earnings-range")).toHaveText("Earnings releases from 2026-01-01 to 2026-06-30", COLD);
    await expect(main.getByRole("table", { name: "Earnings calendar" }).locator("tbody tr")).toHaveCount(4);
    await main.getByRole("tab", { name: "Dividend history" }).click();
    await expect(main.getByTestId("dividends-heading")).toHaveText("JPMORGAN CHASE & CO (JPM)", COLD);

    await main.getByLabel("Dividend ticker").fill("msft");
    await main.getByRole("button", { name: "Show dividends" }).click();
    await expect(page).toHaveURL(/[?&]dividends_ticker=MSFT(&|$)/);
    await expect(page).toHaveURL(/[?&]earnings_start=2026-01-01(&|$)/);
  });

  test("a bad calendar range in a link shows the normal validation error", async ({ page }) => {
    const main = await open(page, "/screener?tab=earnings&earnings_start=2026-06-01&earnings_end=2026-01-01", "Screener & Calendar");
    await expect(main.getByTestId("field-error-end")).toHaveText("The end date must be on or after the start date.", COLD);
  });

  test("a bad criterion value shows the normal validation error", async ({ page }) => {
    const main = await open(page, "/screener?criteria=revenue_growth:min:", "Screener & Calendar");
    await expect(main.getByTestId("field-error-criteria.0.value")).toBeVisible(COLD);
  });
});

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

  test("a strategy link opens the strategy tab with its legs", async ({ page }) => {
    // Iron condor 80/90/110/120 around S = 100 -> credit 4.4155.
    const legs = "put:long:1:80,put:short:1:90,call:short:1:110,call:long:1:120";
    const main = await open(page, `/options?tab=strategy&legs=${legs}`, "Options Calculator");
    await expect(main.getByRole("tab", { name: "Strategy builder" })).toHaveAttribute("aria-selected", "true");
    await expect(main.getByTestId("strategy-leg")).toHaveCount(4);
    await expect(main.getByLabel("Strike 4")).toHaveValue("120");
    await expect(metric(main, "net_cost")).toContainText("-4.4155");
  });

  test("submitting a strategy writes the tab, market inputs and legs to the URL", async ({ page }) => {
    const main = await open(page, "/options", "Options Calculator");
    await main.getByRole("tab", { name: "Strategy builder" }).click();
    await expect(page).toHaveURL(/[?&]tab=strategy(&|$)/);
    await main.getByRole("button", { name: "Iron condor" }).click();
    await main.getByRole("button", { name: "Calculate" }).click();
    await expect(page).toHaveURL(/[?&]legs=put:long:1:80,put:short:1:90,call:short:1:110,call:long:1:120(&|$)/);
    await expect(page).toHaveURL(/[?&]spot=100(&|$)/);

    await page.reload();
    await expect(main.getByTestId("strategy-leg")).toHaveCount(4);
    await expect(metric(main, "net_cost")).toContainText("-4.4155");
  });

  test("a strategy leg without a strike shows the normal validation error", async ({ page }) => {
    const main = await open(page, "/options?tab=strategy&legs=call:long:1:", "Options Calculator");
    await expect(main.getByTestId("field-error-legs.0.strike")).toBeVisible();
  });

  test("an American link prices its inputs and a bad step count shows the field error", async ({ page }) => {
    // S = 110: the Black-Scholes European call next to the tree is 17.66, as on the single-option tab.
    let main = await open(page, "/options?tab=american&spot=110", "Options Calculator");
    await expect(main.getByRole("tab", { name: "American (binomial)" })).toHaveAttribute("aria-selected", "true");
    await expect(main.getByLabel("Spot price")).toHaveValue("110");
    await expect(metric(main, "european_call")).toContainText("17.66");

    await main.getByLabel("Steps", { exact: true }).fill("200");
    await main.getByRole("button", { name: "Calculate" }).click();
    await expect(page).toHaveURL(/[?&]steps=200(&|$)/);

    main = await open(page, "/options?tab=american&steps=0", "Options Calculator");
    await expect(main.getByTestId("field-error-steps")).toBeVisible();
  });
});

test.describe("Valuation Calculator", () => {
  test("a link with non-default inputs shows results computed from them", async ({ page }) => {
    // MSFT with 8% growth (other assumptions default): $185.06 per share.
    const main = await open(page, "/valuation?ticker=msft&growth_rate=8", "Valuation Calculator");
    await expect(main.getByLabel("Ticker")).toHaveValue("MSFT");
    await expect(main.getByLabel("Growth rate (%)")).toHaveValue("8");
    await expect(metric(main, "intrinsic_value_per_share")).toContainText("$185.06");
  });

  test("submitting writes the ticker and every assumption to the URL", async ({ page }) => {
    const main = await open(page, "/valuation", "Valuation Calculator");
    await expect(metric(main, "intrinsic_value_per_share")).toContainText("$163.73");
    await main.getByLabel("Growth rate (%)").fill("8");
    await main.getByRole("button", { name: "Value company" }).click();
    await expect(page).toHaveURL(/[?&]ticker=MSFT(&|$)/);
    await expect(page).toHaveURL(/[?&]growth_rate=8(&|$)/);
    await expect(page).toHaveURL(/[?&]terminal_growth=2\.5(&|$)/);

    await page.reload();
    await expect(metric(main, "intrinsic_value_per_share")).toContainText("$185.06");
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
    await expect(main.getByRole("textbox", { name: "Benchmark" })).toHaveValue("DEMO-MKT");
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

  test("the technical indicators and their parameters round-trip through the URL", async ({ page }) => {
    const main = await open(page, "/risk?indicators=ema,macd&ema_window=30&macd_fast=8", "Risk & Performance");
    const legend = main.getByTestId("indicator-legend-price");
    await expect(legend).toContainText("EMA (30)", COLD);
    await expect(legend).not.toContainText("SMA");
    await expect(main.getByLabel("SMA", { exact: true })).not.toBeChecked();
    await expect(main.getByLabel("RSI", { exact: true })).not.toBeChecked();
    await expect(main.getByLabel("MACD fast window (days)")).toHaveValue("8");
    await expect(main.getByRole("img", { name: /^MACD panel/ })).toBeVisible();

    // No submit button: each change is written straight away.
    await main.getByLabel("RSI", { exact: true }).check();
    await main.getByLabel("EMA window (days)").fill("40");
    await expect(page).toHaveURL(/[?&]indicators=ema,rsi,macd(&|$)/);
    await expect(page).toHaveURL(/[?&]ema_window=40(&|$)/);
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

  test("the rebalancing rule and drift threshold round-trip through the URL", async ({ page }) => {
    const main = await open(page, "/portfolio?tab=rebalancing&rule=drift&drift_threshold=10", "My Portfolio");
    const rebalancing = main.getByRole("region", { name: "Rebalancing backtest" });
    await expect(rebalancing.getByLabel("Rebalancing rule")).toHaveValue("drift");
    await expect(rebalancing.getByLabel("Drift threshold (%)")).toHaveValue("10");
    await expect(rebalancing.locator('[data-metric-value="rebalance_count:rebalanced"]')).toHaveAttribute(
      "data-status",
      "ok",
      COLD,
    );

    await rebalancing.getByLabel("Rebalancing rule").selectOption("monthly");
    await expect(page).toHaveURL(/[?&]rule=monthly(&|$)/);
    await expect(page).toHaveURL(/[?&]tab=rebalancing(&|$)/);
  });

  test("weights that don't add up show the normal validation error", async ({ page }) => {
    const main = await open(page, "/portfolio?holdings=DEMO-A:50", "My Portfolio");
    await expect(main.getByTestId("field-error-holdings")).toContainText("add up to 50%");
  });
});
