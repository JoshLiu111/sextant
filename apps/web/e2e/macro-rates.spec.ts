import { expect, test, type Page } from "@playwright/test";

// Compute talks to the fake Treasury (e2e/fake-treasury.mjs), which serves the
// recorded CSVs in apps/compute/tests/fixtures/treasury. Values below come from
// them: the latest curve is 2026-11-20, a month earlier 2026-10-20, a year
// earlier 2025-11-20.

// A cold cache fetches one CSV per year (2018 to today).
const COLD = { timeout: 30_000 };

async function openRates(page: Page) {
  await page.goto("/macro");
  const main = page.getByRole("main");
  await expect(main.getByRole("heading", { level: 2, name: "US Treasury yields" })).toBeVisible();
  await expect(main.locator('[data-metric-value="latest:spread_10y_2y"]')).toHaveAttribute("data-status", "ok", COLD);
  return main;
}

test("the latest 2-year, 10-year and 10Y-2Y spread are shown", async ({ page }) => {
  const main = await openRates(page);

  await expect(main.locator('[data-metric-value="latest:yield_2y"]')).toContainText("4.63%");
  await expect(main.locator('[data-metric-value="latest:yield_10y"]')).toContainText("4.92%");
  await expect(main.locator('[data-metric-value="latest:spread_10y_2y"]')).toContainText("0.29 pp");
});

test("the yield curve overlays the latest, 1-month-ago and 1-year-ago curves with hover values", async ({ page }) => {
  const main = await openRates(page);
  const chart = main.getByRole("img", { name: "US Treasury yield curve" });

  // Focusing starts at the middle maturity of the 14 published (2 yr); arrows step through them.
  await chart.focus();
  const tooltip = main.getByTestId("chart-tooltip");
  await expect(tooltip).toContainText("Maturity: 2 yr");
  await expect(tooltip).toContainText("Latest (2026-11-20): 4.63%");
  await expect(tooltip).toContainText("1 month earlier (2026-10-20): 4.79%");
  await expect(tooltip).toContainText("1 year earlier (2025-11-20): 3.55%");

  await chart.press("ArrowRight");
  await expect(tooltip).toContainText("Maturity: 3 yr");
  await expect(tooltip).toContainText("Latest (2026-11-20): 4.65%");

  await chart.hover();
  await expect(tooltip).toContainText("Latest (2026-11-20)");
});

test("the 10Y-2Y spread history shades the inversion periods", async ({ page }) => {
  const main = await openRates(page);
  const chart = main.getByRole("img", { name: "10Y–2Y spread history" });

  const bands = chart.getByTestId("chart-band");
  await expect(bands.first()).toBeAttached();
  await expect(chart.locator('[data-testid="chart-band"][data-band-start="2019-08-27"]')).toHaveAttribute(
    "data-band-end",
    "2019-08-29",
  );
  const longest = chart.locator('[data-testid="chart-band"][data-band-start="2022-07-06"]');
  await expect(longest).toHaveAttribute("data-band-end", "2024-08-26");

  await longest.hover();
  const tooltip = main.getByTestId("chart-tooltip");
  await expect(tooltip.getByTestId("chart-tooltip-band")).toContainText("Inverted (10Y below 2Y): 2022-07-06 – 2024-08-26");
  await expect(tooltip).toContainText(/10Y–2Y term spread: -\d\.\d\d pp/);
});

test("each rates series shows its source, units, frequency and last update", async ({ page }) => {
  const main = await openRates(page);

  for (const [key, units] of [
    ["yield_curve", "Percent"],
    ["spread_10y_2y", "Percentage points"],
  ]) {
    const meta = main.locator(`[data-indicator="${key}"]`).getByTestId("series-meta");
    await expect(meta).toContainText("U.S. Department of the Treasury");
    await expect(meta.getByRole("link", { name: "Daily Treasury Par Yield Curve Rates" })).toHaveAttribute(
      "href",
      /home\.treasury\.gov/,
    );
    await expect(meta).toContainText(units);
    await expect(meta).toContainText("Daily (business days)");
    await expect(meta).toContainText("2026-11-20");
    await expect(meta).toContainText(/Last updated\s*\d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC/);
  }
});

test("the footer credits the Treasury next to FRED", async ({ page }) => {
  await page.goto("/macro");

  const footer = page.getByRole("contentinfo");
  await expect(footer.locator('[data-attribution="treasury"]')).toContainText(
    "Source: U.S. Department of the Treasury, Daily Treasury Par Yield Curve Rates. Not endorsed by the U.S. Treasury.",
  );
  await expect(footer.locator('[data-attribution="fred"]')).toBeAttached();
});

test("a Treasury outage asks to retry without hiding the FRED indicators", async ({ page }) => {
  await page.route("**/api/compute/macro/rates", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ error: { code: "source_unavailable", message: "The data source is down.", fields: {} } }),
    }),
  );
  await page.goto("/macro");
  const main = page.getByRole("main");

  await expect(main.getByTestId("rates").getByTestId("error-notice")).toContainText(
    "Data source temporarily unavailable, please retry.",
  );
  await expect(main.locator('[data-metric-value="latest:gdp_growth"]')).toHaveAttribute("data-status", "ok", COLD);
});

test.describe("mobile width", () => {
  test.use({ viewport: { width: 375, height: 740 } });

  test("the rates charts fit without horizontal scroll", async ({ page }) => {
    await openRates(page);

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(0);
  });
});
