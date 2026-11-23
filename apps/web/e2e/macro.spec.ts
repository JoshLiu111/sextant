import { expect, test, type Page } from "@playwright/test";

// Compute talks to the fake FRED (e2e/fake-fred.mjs), which serves the recorded
// responses in apps/compute/tests/fixtures/fred. Values below come from them.
const INDICATORS = [
  { key: "gdp_growth", name: "Real GDP growth", value: "2.30%", source: "U.S. Bureau of Economic Analysis", frequency: "Quarterly" },
  { key: "cpi_inflation", name: "CPI inflation", value: "2.60%", source: "U.S. Bureau of Labor Statistics", frequency: "Monthly" },
  { key: "unemployment_rate", name: "Unemployment rate", value: "4.50%", source: "U.S. Bureau of Labor Statistics", frequency: "Monthly" },
  { key: "fed_funds_rate", name: "Federal funds rate", value: "3.58%", source: "Board of Governors of the Federal Reserve System", frequency: "Monthly" },
];

const FRED_NOTICE =
  "This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of St. Louis.";

// A cold cache fetches 8 FRED responses (shared by concurrent tests). Kept well
// under Playwright's 30 s test timeout so a slow fill fails with a clear message.
const COLD = { timeout: 20_000 };

async function openMacro(page: Page) {
  await page.goto("/macro");
  const main = page.getByRole("main");
  await expect(main.getByRole("heading", { level: 1, name: "Macro Dashboard" })).toBeVisible();
  return main;
}

test("smoke: open the page and see the four indicators with their latest value", async ({ page }) => {
  const main = await openMacro(page);

  for (const ind of INDICATORS) {
    const value = main.locator(`[data-metric-value="latest:${ind.key}"]`);
    await expect(value).toHaveAttribute("data-status", "ok", COLD);
    await expect(value).toContainText(ind.value);
    await expect(main.locator(`[data-indicator="${ind.key}"]`).getByRole("heading", { name: ind.name })).toBeVisible();
  }
});

test("each indicator shows its source, units, frequency and last update", async ({ page }) => {
  const main = await openMacro(page);
  await expect(main.locator('[data-metric-value="latest:cpi_inflation"]')).toHaveAttribute("data-status", "ok", COLD);

  for (const ind of INDICATORS) {
    const meta = main.locator(`[data-indicator="${ind.key}"]`).getByTestId("series-meta");
    await expect(meta).toContainText(ind.source);
    await expect(meta).toContainText(ind.frequency);
    await expect(meta).toContainText("Last updated");
  }
  const cpi = main.locator('[data-indicator="cpi_inflation"]').getByTestId("series-meta");
  await expect(cpi).toContainText("Percent Change from Year Ago");
  await expect(cpi).toContainText("2026-11-13");
  await expect(cpi.getByRole("link", { name: "CPIAUCSL" })).toHaveAttribute(
    "href",
    "https://fred.stlouisfed.org/series/CPIAUCSL",
  );
});

test("hovering a history chart shows the exact value", async ({ page }) => {
  const main = await openMacro(page);
  await expect(main.locator('[data-metric-value="latest:unemployment_rate"]')).toHaveAttribute(
    "data-status",
    "ok",
    COLD,
  );

  const chart = main.getByRole("img", { name: /Unemployment rate history/ });
  await chart.hover();
  await expect(main.getByTestId("chart-tooltip")).toContainText("%");
});

test("the footer shows the FRED notice and a link to the FRED API Terms of Use", async ({ page }) => {
  await openMacro(page);

  const fred = page.getByRole("contentinfo").locator('[data-attribution="fred"]');
  await expect(fred).toContainText(FRED_NOTICE);
  await expect(fred.getByRole("link", { name: "FRED API Terms of Use" })).toHaveAttribute(
    "href",
    "https://fred.stlouisfed.org/docs/api/terms_of_use.html",
  );
});

test("pages that don't use FRED don't show the FRED notice", async ({ page }) => {
  for (const path of ["/", "/options", "/risk"]) {
    await page.goto(path);
    await expect(page.getByRole("contentinfo").getByTestId("attribution-slot")).toBeAttached();
    await expect(page.getByRole("contentinfo").locator('[data-attribution="fred"]')).toHaveCount(0);
  }
});

test("a FRED outage asks the visitor to retry", async ({ page }) => {
  await page.route("**/api/compute/macro/indicators", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({
        error: { code: "source_unavailable", message: "The data source is down.", fields: {} },
      }),
    }),
  );
  const main = await openMacro(page);

  await expect(main.getByTestId("error-notice")).toContainText("Data source temporarily unavailable, please retry.");
});

test.describe("mobile width", () => {
  test.use({ viewport: { width: 375, height: 740 } });

  test("the page fits without horizontal scroll", async ({ page }) => {
    const main = await openMacro(page);
    await expect(main.locator('[data-metric-value="latest:gdp_growth"]')).toHaveAttribute("data-status", "ok", COLD);

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(0);
  });
});
