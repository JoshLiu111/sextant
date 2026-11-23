import { expect, test, type Locator, type Page } from "@playwright/test";

// Compute talks to the fake World Bank (e2e/fake-world-bank.mjs) and fake ECB
// (e2e/fake-ecb.mjs), which serve the recordings in apps/compute/tests/fixtures/
// {world_bank,ecb}. Values below come from them: WDI last updated 2026-11-11
// (latest year 2025; no 2025 US CPI yet), ECB rates last changed 2026-09-16,
// HICP latest 2026-10.

// A cold cache fetches 6 World Bank and 4 ECB responses, shared by concurrent tests.
const COLD = { timeout: 20_000 };

async function openComparison(page: Page, query = "") {
  await page.goto(`/macro${query}`);
  const section = page.getByRole("main").getByTestId("countries");
  await expect(section.getByRole("heading", { level: 2, name: "Compare countries" })).toBeVisible();
  return section;
}

function value(section: Locator, id: string) {
  return section.locator(`[data-metric-value="${id}"]`);
}

test("the comparison starts with four large economies, side by side", async ({ page }) => {
  const section = await openComparison(page);

  await expect(value(section, "latest:gdp_growth:DEU")).toHaveAttribute("data-status", "ok", COLD);
  await expect(value(section, "latest:gdp_growth:USA")).toContainText("2.16%");
  await expect(value(section, "latest:gdp_growth:DEU")).toContainText("Germany");
  await expect(value(section, "latest:gdp_growth:DEU")).toContainText("0.24%");
  await expect(value(section, "latest:unemployment_rate:JPN")).toContainText("2.45%");
  await expect(value(section, "latest:inflation:GBR")).toContainText("3.88%");
  // The latest year published is shown with each value: no 2025 US CPI yet.
  await expect(value(section, "latest:inflation:USA")).toContainText("2.95%");
  await expect(value(section, "latest:inflation:USA")).toContainText("2024");

  for (const name of ["United States", "Germany", "Japan", "United Kingdom"]) {
    await expect(section.getByRole("checkbox", { name })).toBeChecked();
  }
  const chart = section.getByRole("img", { name: "GDP growth by country" });
  await chart.focus();
  const tooltip = section.getByTestId("chart-tooltip");
  await expect(tooltip).toContainText(/Year: \d{4}/);
  await expect(tooltip).toContainText(/Germany: -?\d+\.\d%/);
});

test("picking countries updates the comparison and the URL, and the URL restores it", async ({ page }) => {
  const section = await openComparison(page);
  await expect(value(section, "latest:gdp_growth:USA")).toHaveAttribute("data-status", "ok", COLD);

  await section.getByRole("checkbox", { name: "China" }).check();
  await section.getByRole("checkbox", { name: "Germany" }).uncheck();

  await expect(page).toHaveURL(/[?&]countries=USA%2CJPN%2CGBR%2CCHN$|[?&]countries=USA,JPN,GBR,CHN$/);
  await expect(value(section, "latest:gdp_growth:CHN")).toContainText("4.96%", COLD);
  await expect(value(section, "latest:gdp_growth:DEU")).toHaveCount(0);

  await page.reload();
  const restored = page.getByRole("main").getByTestId("countries");
  await expect(restored.getByRole("checkbox", { name: "China" })).toBeChecked();
  await expect(restored.getByRole("checkbox", { name: "Germany" })).not.toBeChecked();
  await expect(value(restored, "latest:gdp_growth:CHN")).toContainText("4.96%", COLD);
});

test("a shared link opens the comparison it names, including the euro area aggregate", async ({ page }) => {
  const section = await openComparison(page, "?countries=EMU,IND");

  await expect(section.getByRole("checkbox", { name: "Euro area" })).toBeChecked();
  await expect(section.getByRole("checkbox", { name: "India" })).toBeChecked();
  await expect(section.getByRole("checkbox", { name: "United States" })).not.toBeChecked();
  await expect(value(section, "latest:unemployment_rate:EMU")).toContainText("6.28%", COLD);
  await expect(value(section, "latest:gdp_growth:IND")).toContainText("7.57%");
});

test("at most six countries can be compared", async ({ page }) => {
  const section = await openComparison(page, "?countries=USA,DEU,JPN,GBR,FRA,ITA");

  await expect(section.getByRole("checkbox", { name: "Canada" })).toBeDisabled();
  await expect(section.getByRole("checkbox", { name: "France" })).toBeEnabled();
  await section.getByRole("checkbox", { name: "France" }).uncheck();
  await expect(section.getByRole("checkbox", { name: "Canada" })).toBeEnabled();
});

test("each World Bank indicator shows its source, units, frequency and last update", async ({ page }) => {
  const section = await openComparison(page);
  await expect(value(section, "latest:inflation:USA")).toHaveAttribute("data-status", "ok", COLD);

  const meta = section.locator('[data-indicator="country:inflation"]').getByTestId("series-meta");
  await expect(meta).toContainText("World Bank, World Development Indicators");
  await expect(meta).toContainText("International Monetary Fund, International Financial Statistics");
  await expect(meta.getByRole("link", { name: "FP.CPI.TOTL.ZG" })).toHaveAttribute(
    "href",
    "https://data.worldbank.org/indicator/FP.CPI.TOTL.ZG",
  );
  await expect(meta).toContainText("Percent change from a year earlier");
  await expect(meta).toContainText("Annual");
  await expect(meta).toContainText("2026-11-11");
});

test("the euro area section shows the key ECB rates and HICP inflation", async ({ page }) => {
  await page.goto("/macro");
  const section = page.getByRole("main").getByTestId("euro-area");
  await expect(section.getByRole("heading", { level: 2, name: "Euro area" })).toBeVisible();

  await expect(value(section, "latest:deposit_facility_rate")).toHaveAttribute("data-status", "ok", COLD);
  await expect(value(section, "latest:deposit_facility_rate")).toContainText("2.50%");
  await expect(value(section, "latest:deposit_facility_rate")).toContainText("Since 2026-09-16");
  await expect(value(section, "latest:main_refinancing_rate")).toContainText("2.65%");
  await expect(value(section, "latest:marginal_lending_rate")).toContainText("2.90%");
  await expect(value(section, "latest:hicp_inflation")).toContainText("4.00%");

  const rates = section.locator('[data-indicator="ecb_rates"]').getByTestId("series-meta");
  await expect(rates).toContainText("European Central Bank");
  await expect(rates).toContainText("Percent per annum");
  await expect(rates).toContainText("On change (Governing Council decisions)");
  await expect(rates).toContainText("2026-09-10 14:22 UTC");
  const hicp = section.locator('[data-indicator="hicp_inflation"]').getByTestId("series-meta");
  await expect(hicp).toContainText("Eurostat (via the ECB)");
  await expect(hicp).toContainText("Annual rate of change, percent");
  await expect(hicp).toContainText("Monthly");
  await expect(hicp).toContainText("2026-10");
  await expect(hicp).toContainText("2026-11-18 10:32 UTC");

  await expect(section.getByRole("img", { name: "Key ECB interest rates history" })).toBeVisible();
  await expect(section.getByRole("img", { name: "Euro area HICP inflation history" })).toBeVisible();
});

test("the footer credits the World Bank (CC BY 4.0) and the ECB on the macro page only", async ({ page }) => {
  await page.goto("/macro");
  const footer = page.getByRole("contentinfo");

  const worldBank = footer.locator('[data-attribution="world_bank"]');
  await expect(worldBank).toContainText("The World Bank: World Development Indicators");
  await expect(worldBank.getByRole("link", { name: "CC BY 4.0", exact: true })).toHaveAttribute(
    "href",
    "https://creativecommons.org/licenses/by/4.0/",
  );
  await expect(footer.locator('[data-attribution="ecb"]')).toContainText("Source: ECB statistics.");
  await expect(footer.locator('[data-attribution="ecb"]')).toContainText("Eurostat");

  await page.goto("/options");
  await expect(page.getByRole("contentinfo").locator('[data-attribution="world_bank"]')).toHaveCount(0);
  await expect(page.getByRole("contentinfo").locator('[data-attribution="ecb"]')).toHaveCount(0);
});

test("a World Bank outage only affects the comparison", async ({ page }) => {
  await page.route("**/api/compute/macro/countries", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ error: { code: "source_unavailable", message: "The data source is down.", fields: {} } }),
    }),
  );
  const section = await openComparison(page);

  await expect(section.getByTestId("error-notice")).toContainText("Data source temporarily unavailable, please retry.");
  const euro = page.getByRole("main").getByTestId("euro-area");
  await expect(value(euro, "latest:deposit_facility_rate")).toHaveAttribute("data-status", "ok", COLD);
});

test.describe("mobile width", () => {
  test.use({ viewport: { width: 375, height: 740 } });

  test("the comparison and euro area charts fit without horizontal scroll", async ({ page }) => {
    const section = await openComparison(page);
    await expect(value(section, "latest:gdp_growth:USA")).toHaveAttribute("data-status", "ok", COLD);
    await expect(
      value(page.getByRole("main").getByTestId("euro-area"), "latest:hicp_inflation"),
    ).toHaveAttribute("data-status", "ok", COLD);

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(0);
  });
});
