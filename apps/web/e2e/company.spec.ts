import { expect, test, type Page } from "@playwright/test";

// Compute serves EDGAR from recorded fixtures (apps/compute/tests/fixtures/edgar)
// through e2e/fake-edgar.mjs, so these tests never touch sec.gov.
// Default ticker AAPL; its latest fixture year is FY2026 (ended 2026-09-26).

async function openCompany(page: Page) {
  await page.goto("/company");
  const main = page.getByRole("main");
  await expect(main.getByRole("heading", { level: 1, name: "Company Health Check" })).toBeVisible();
  return main;
}

type Main = Awaited<ReturnType<typeof openCompany>>;
const cell = (main: Main, id: string) => main.locator(`[data-metric-value="${id}"]`);

test("smoke: submit the default ticker and see all three statements", async ({ page }) => {
  const main = await openCompany(page);
  await expect(main.getByLabel("Ticker")).toHaveValue("AAPL");

  await main.getByRole("button", { name: "Show statements" }).click();

  const results = main.getByTestId("results");
  await expect(results.getByRole("heading", { name: "Apple Inc." })).toBeVisible();
  for (const name of ["Income statement", "Balance sheet", "Cash flow statement"]) {
    await expect(results.getByRole("table", { name })).toBeVisible();
  }
  const income = results.getByRole("table", { name: "Income statement" });
  for (const fy of ["FY2022", "FY2023", "FY2024", "FY2025", "FY2026"]) {
    await expect(income.getByRole("columnheader", { name: new RegExp(fy) })).toBeVisible();
  }
  await expect(cell(results, "revenue:2026-09-26")).toHaveText("478,834");
  await expect(cell(results, "total_assets:2026-09-26")).toHaveText("404,548");
  await expect(cell(results, "operating_cash_flow:2026-09-26")).toHaveText("145,097");
  await expect(cell(results, "eps_diluted:2026-09-26")).toHaveText("8.98");
});

test("every value links to its source filing", async ({ page }) => {
  const main = await openCompany(page);

  const revenue = cell(main, "revenue:2026-09-26");
  await expect(revenue).toHaveAttribute("data-status", "ok");
  await expect(revenue).toHaveAttribute(
    "href",
    "https://www.sec.gov/Archives/edgar/data/320193/000032019326000026/0000320193-26-000026-index.htm",
  );
  await expect(revenue).toHaveAttribute("title", /10-K filed 2026-11-03/);
  const header = main.getByRole("table", { name: "Income statement" }).getByRole("columnheader", { name: /FY2026/ });
  await expect(header).toContainText("10-K filed 2026-11-03");
  await expect(header.getByRole("link")).toHaveAttribute("href", /sec\.gov\/Archives\/edgar\/data\/320193\//);
});

test("missing line items say not reported, and the rest of the statements render", async ({ page }) => {
  const main = await openCompany(page);
  await expect(cell(main, "revenue:2026-09-26")).toHaveAttribute("data-status", "ok");

  await main.getByLabel("Ticker").fill("JPM");
  await main.getByRole("button", { name: "Show statements" }).click();

  const cogs = cell(main, "cost_of_revenue:2025-12-31");
  await expect(cogs).toHaveAttribute("data-status", "missing_data");
  await expect(cogs).toHaveText("Not reported by this company");
  await expect(cogs).toHaveAttribute("title", "Cost of Revenue is not reported by this company.");
  const row = main.getByRole("row", { name: /Cost of Revenue/ });
  await expect(row.getByRole("rowheader")).toHaveText("Cost of Revenue");
  await expect(cell(main, "net_income:2025-12-31")).toHaveAttribute("data-status", "ok");
  await expect(main.getByRole("table", { name: "Cash flow statement" })).toBeVisible();
});

test("an unknown ticker is shown inline", async ({ page }) => {
  const main = await openCompany(page);
  await expect(cell(main, "revenue:2026-09-26")).toHaveAttribute("data-status", "ok");

  await main.getByLabel("Ticker").fill("ZZZZ");
  await main.getByRole("button", { name: "Show statements" }).click();

  await expect(main.getByTestId("field-error-ticker")).toContainText("Unknown ticker ZZZZ");
  await expect(main.getByLabel("Ticker")).toHaveAttribute("aria-invalid", "true");
});

test("an EDGAR outage asks the visitor to retry", async ({ page }) => {
  await page.route("**/api/compute/company/statements", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ error: { code: "source_unavailable", message: "down", fields: {} } }),
    }),
  );
  const main = await openCompany(page);

  await expect(main.getByTestId("error-notice")).toContainText("Data source temporarily unavailable, please retry.");
});

test("the footer shows the SEC attribution on this page", async ({ page }) => {
  await openCompany(page);

  await expect(page.getByRole("contentinfo").locator('[data-attribution="sec"]')).toBeVisible();
});

test("the statements have an explainer", async ({ page }) => {
  const main = await openCompany(page);

  await expect(main.getByTestId("explainer")).toHaveCount(1);
});

test.describe("mobile width", () => {
  test.use({ viewport: { width: 375, height: 740 } });

  test("the page fits without horizontal scroll", async ({ page }) => {
    const main = await openCompany(page);
    await expect(cell(main, "revenue:2026-09-26")).toHaveAttribute("data-status", "ok");

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(0);
  });
});
