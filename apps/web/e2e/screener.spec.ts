import { expect, test, type Page } from "@playwright/test";

// Compute serves EDGAR frames and filing feeds from recorded fixtures
// (apps/compute/tests/fixtures/edgar) through e2e/fake-edgar.mjs; the default
// year is pinned to 2025 (SCREENER_DEFAULT_YEAR in playwright.config.ts).
// Default screen: revenue growth >= 10%, gross margin >= 40%, ROE >= 15%,
// which matches 9 of the 37 recorded companies.

async function openScreener(page: Page, { waitForResults = true } = {}) {
  await page.goto("/screener");
  const main = page.getByRole("main");
  await expect(main.getByRole("heading", { level: 1, name: "Screener & Calendar" })).toBeVisible();
  // A cold screen fetches ~20 frames through the 5 requests/second EDGAR limiter.
  if (waitForResults) await expect(main.getByTestId("screen-summary")).toBeVisible({ timeout: 30_000 });
  return main;
}

type Main = Awaited<ReturnType<typeof openScreener>>;
const results = (main: Main) => main.getByRole("table", { name: "Screen results" });
const rowTickers = (main: Main) => results(main).locator("[data-ticker]").evaluateAll((rows) => rows.map((r) => r.getAttribute("data-ticker")));

test("smoke: the default screen runs on load and shows results", async ({ page }) => {
  const main = await openScreener(page);

  await expect(results(main).getByRole("row", { name: /NVIDIA CORP/ })).toBeVisible();
  await expect(main.getByTestId("screen-summary")).toContainText("9 of 37 companies match");
  expect(await rowTickers(main)).toEqual(["AMZN", "GOOGL", "MSFT", "NVDA", "META", "LLY", "AVGO", "NFLX", "ADBE"]);
  const nvda = results(main).getByRole("row", { name: /NVIDIA CORP/ });
  await expect(nvda.locator('[data-metric-value="revenue_growth"]')).toHaveText("65.5%");
  await expect(nvda.locator('[data-metric-value="revenue"]')).toHaveText("215,938");
});

test("the page says how many companies were excluded for missing data and why", async ({ page }) => {
  const main = await openScreener(page);

  const summary = main.getByTestId("screen-summary");
  await expect(summary).toContainText("9 excluded for missing data");
  await expect(summary.getByText(/Gross margin: 9/)).toBeVisible();
  await expect(summary).toContainText("Gross Profit is not reported for 2025.");
  await expect(summary).toContainText("Equity is zero or negative");
});

test("results sort by any column", async ({ page }) => {
  const main = await openScreener(page);
  await expect(results(main).getByRole("row", { name: /NVIDIA CORP/ })).toBeVisible();

  await results(main).getByRole("button", { name: "Return on equity" }).click();
  await expect(results(main).getByRole("columnheader", { name: /Return on equity/ })).toHaveAttribute("aria-sort", "descending");
  await expect.poll(() => rowTickers(main)).toEqual(["LLY", "NVDA", "ADBE", "NFLX", "GOOGL", "AVGO", "META", "MSFT", "AMZN"]);

  await results(main).getByRole("button", { name: "Return on equity" }).click();
  await expect(results(main).getByRole("columnheader", { name: /Return on equity/ })).toHaveAttribute("aria-sort", "ascending");
  await expect.poll(async () => (await rowTickers(main))[0]).toBe("AMZN");

  await results(main).getByRole("button", { name: "Ticker" }).click();
  await expect.poll(() => rowTickers(main)).toEqual(["ADBE", "AMZN", "AVGO", "GOOGL", "LLY", "META", "MSFT", "NFLX", "NVDA"]);
});

test("criteria can be changed, removed and added", async ({ page }) => {
  const main = await openScreener(page);
  await expect(results(main).getByRole("row", { name: /NVIDIA CORP/ })).toBeVisible();
  const criteria = main.getByRole("group", { name: "Criteria" });

  // Change: gross margin at least 75%.
  await criteria.getByLabel("Value for criterion 2").fill("75");
  await main.getByRole("button", { name: "Run screen" }).click();
  await expect.poll(() => rowTickers(main)).toEqual(["META", "LLY", "ADBE"]);

  // Remove the ROE and gross margin criteria: only revenue growth >= 10% is left.
  await criteria.getByRole("button", { name: "Remove criterion 3" }).click();
  await criteria.getByRole("button", { name: "Remove criterion 2" }).click();
  await main.getByRole("button", { name: "Run screen" }).click();
  await expect(main.getByTestId("screen-summary")).toContainText("15 of 36 companies match");
  await expect(results(main).getByRole("columnheader", { name: /Return on equity/ })).toHaveCount(0);

  // Add: debt ratio at most 30%.
  await main.getByRole("button", { name: "Add criterion" }).click();
  await criteria.getByLabel("Metric for criterion 2").selectOption("debt_ratio");
  await criteria.getByLabel("Condition for criterion 2").selectOption("max");
  await criteria.getByLabel("Value for criterion 2").fill("30");
  await main.getByRole("button", { name: "Run screen" }).click();
  await expect.poll(() => rowTickers(main)).toEqual(["NVDA", "AMD"]);
  await expect(results(main).getByRole("columnheader", { name: /Debt ratio/ })).toBeVisible();
});

test("each row opens the company in Company Health Check and the Valuation Calculator", async ({ page }) => {
  const main = await openScreener(page);
  const msft = results(main).getByRole("row", { name: /MICROSOFT CORP/ });

  await expect(msft.getByRole("link", { name: "Valuation" })).toHaveAttribute("href", "/valuation?ticker=MSFT");
  await expect(msft.getByRole("link", { name: "Health check" })).toHaveAttribute(
    "href",
    "/company?companies=MSFT&ticker=MSFT",
  );

  await msft.getByRole("link", { name: "Health check" }).click();
  await expect(page).toHaveURL(/\/company\?companies=MSFT&ticker=MSFT$/);
  const company = page.getByRole("main");
  await expect(company.getByLabel("Ticker")).toHaveValue("MSFT");
  await expect(company.getByTestId("results").getByRole("heading", { name: "MICROSOFT CORP" })).toBeVisible();
  await expect(company.getByTestId("ratios").getByLabel("Compare company 1", { exact: true })).toHaveValue("MSFT");
  await expect(company.locator('[data-metric-value^="current_ratio:MSFT:"]').first()).toHaveAttribute("data-status", "ok");
});

test("the Valuation link opens the Valuation Calculator with that company's results", async ({ page }) => {
  const main = await openScreener(page);
  const msft = results(main).getByRole("row", { name: /MICROSOFT CORP/ });

  await msft.getByRole("link", { name: "Valuation" }).click();
  await expect(page).toHaveURL(/\/valuation\?ticker=MSFT$/);
  const valuation = page.getByRole("main");
  await expect(valuation.getByLabel("Ticker")).toHaveValue("MSFT");
  await expect(valuation.getByTestId("results").getByRole("heading", { name: "MICROSOFT CORP" })).toBeVisible();
  // MSFT on the default assumptions (see valuation.spec.ts).
  await expect(valuation.locator('[data-metric-value="intrinsic_value_per_share"]')).toContainText("$158.11");
});

test("the latest filings list works market-wide and for one company", async ({ page }) => {
  const main = await openScreener(page);
  const filings = main.getByRole("table", { name: "Latest SEC filings" });

  await expect(filings.getByRole("row")).toHaveCount(41); // header + 40 filings
  const first = filings.getByRole("row").nth(1);
  await expect(first).toContainText("SCHEDULE 13D/A");
  await expect(first).toContainText("2026-11-20");
  await expect(first.getByRole("link")).toHaveAttribute(
    "href",
    "https://www.sec.gov/Archives/edgar/data/2117604/000211760426000001/0002117604-26-000001-index.htm",
  );

  await main.getByLabel("Form type").selectOption("10-K");
  await main.getByRole("button", { name: "Show filings" }).click();
  await expect(filings.getByRole("row")).toHaveCount(29);
  await expect(filings.getByRole("row").nth(2)).toContainText("PTC INC.");

  await main.getByLabel("One company").check();
  await main.getByLabel("Company ticker").fill("AAPL");
  await main.getByRole("button", { name: "Show filings" }).click();
  await expect(main.getByTestId("filings-heading")).toContainText("Apple Inc.");
  await expect(filings.getByRole("row")).toHaveCount(2);
  await expect(filings.getByRole("row").nth(1)).toContainText("10-K - Annual report");
  await expect(filings.getByRole("row").nth(1).getByRole("link")).toHaveAttribute(
    "href",
    "https://www.sec.gov/Archives/edgar/data/320193/000032019326000026/0000320193-26-000026-index.htm",
  );
});

test("an unknown company ticker is shown inline", async ({ page }) => {
  const main = await openScreener(page);
  await expect(main.getByRole("table", { name: "Latest SEC filings" }).getByRole("row").nth(1)).toBeVisible();

  await main.getByLabel("One company").check();
  await main.getByLabel("Company ticker").fill("ZZZZ");
  await main.getByRole("button", { name: "Show filings" }).click();

  await expect(main.getByTestId("field-error-ticker")).toContainText("Unknown ticker ZZZZ");
});

test("an EDGAR outage asks the visitor to retry", async ({ page }) => {
  await page.route("**/api/compute/screener/screen", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ error: { code: "source_unavailable", message: "down", fields: {} } }),
    }),
  );
  const main = await openScreener(page, { waitForResults: false });

  await expect(main.getByTestId("error-notice").first()).toContainText("Data source temporarily unavailable, please retry.");
});

test("the footer shows the SEC attribution and the screen has an explainer", async ({ page }) => {
  const main = await openScreener(page);

  await expect(page.getByRole("contentinfo").locator('[data-attribution="sec"]')).toBeVisible();
  await expect(main.getByTestId("explainer").first()).toBeVisible();
});

test.describe("mobile width", () => {
  test.use({ viewport: { width: 375, height: 740 } });

  test("the page fits without horizontal scroll", async ({ page }) => {
    const main = await openScreener(page);
    await expect(results(main).getByRole("row", { name: /NVIDIA CORP/ })).toBeVisible();

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(0);
  });
});
