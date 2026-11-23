import { expect, test, type Page } from "@playwright/test";

// Ratios and Altman Z on the /company page, computed from the recorded EDGAR
// fixtures served by e2e/fake-edgar.mjs. AAPL FY2026 ended 2026-09-26.

async function openRatios(page: Page) {
  await page.goto("/company");
  const main = page.getByRole("main");
  await expect(main.getByRole("heading", { level: 1, name: "Company Health Check" })).toBeVisible();
  return main.getByTestId("ratios");
}

type Section = Awaited<ReturnType<typeof openRatios>>;
const value = (section: Section, id: string) => section.locator(`[data-metric-value="${id}"]`);

test("smoke: submit the defaults and see the five ratio categories and Altman Z", async ({ page }) => {
  const ratios = await openRatios(page);
  await expect(ratios.getByLabel("Compare company 1", { exact: true })).toHaveValue("AAPL");

  await ratios.getByRole("button", { name: "Show ratios" }).click();

  for (const name of ["Efficiency", "Liquidity", "Profitability", "Solvency", "Valuation", "Altman Z-Score"]) {
    await expect(ratios.getByRole("table", { name })).toBeVisible();
  }
  const liquidity = ratios.getByRole("table", { name: "Liquidity" });
  for (const fy of ["FY2022", "FY2023", "FY2024", "FY2025", "FY2026"]) {
    await expect(liquidity.getByRole("columnheader", { name: fy })).toBeVisible();
  }
  await expect(value(ratios, "current_ratio:AAPL:2026-09-26")).toHaveText("1.02");
  await expect(value(ratios, "return_on_equity:AAPL:2026-09-26")).toHaveText("142.26%");
  await expect(value(ratios, "days_sales_outstanding:AAPL:2026-09-26")).toHaveText("31.9 days");
  const z = value(ratios, "altman_z:AAPL:2026-09-26");
  await expect(z).toContainText("2.59");
  await expect(z).toContainText("Grey zone");
});

test("each ratio has an explainer", async ({ page }) => {
  const ratios = await openRatios(page);
  await expect(value(ratios, "current_ratio:AAPL:2026-09-26")).toHaveAttribute("data-status", "ok");

  const row = ratios.getByRole("table", { name: "Liquidity" }).getByRole("rowheader", { name: /Current ratio/ });
  await row.getByText("About Current ratio").click();
  await expect(row.getByText("Current assets divided by current liabilities")).toBeVisible();
  expect(await ratios.getByTestId("explainer").count()).toBeGreaterThanOrEqual(36);
});

test("valuation multiples need a price, and use one when entered", async ({ page }) => {
  const ratios = await openRatios(page);
  const pe = value(ratios, "price_to_earnings:AAPL:2026-09-26");
  await expect(pe).toHaveAttribute("data-status", "missing_data");
  await expect(pe).toHaveAttribute("title", /share price is required/);

  await ratios.getByLabel("Share price 1", { exact: true }).fill("250");
  await ratios.getByRole("button", { name: "Show ratios" }).click();

  await expect(pe).toHaveText("27.84");
});

test("several companies are compared side by side", async ({ page }) => {
  const ratios = await openRatios(page);
  await expect(value(ratios, "current_ratio:AAPL:2026-09-26")).toHaveAttribute("data-status", "ok");

  await ratios.getByRole("button", { name: "Add company" }).click();
  await ratios.getByLabel("Compare company 2", { exact: true }).fill("JPM");
  await ratios.getByRole("button", { name: "Show ratios" }).click();

  await expect(value(ratios, "net_margin:JPM:2025-12-31")).toHaveAttribute("data-status", "ok");
  await expect(value(ratios, "net_margin:AAPL:2026-09-26")).toHaveAttribute("data-status", "ok");
  const current = value(ratios, "current_ratio:JPM:2025-12-31");
  await expect(current).toHaveAttribute("data-status", "missing_data");
  await expect(current).toHaveAttribute("title", /Current Assets is not reported/);
});

test("an unknown ticker is shown on its row", async ({ page }) => {
  const ratios = await openRatios(page);
  await expect(value(ratios, "current_ratio:AAPL:2026-09-26")).toHaveAttribute("data-status", "ok");

  await ratios.getByLabel("Compare company 1", { exact: true }).fill("ZZZZ");
  await ratios.getByRole("button", { name: "Show ratios" }).click();

  await expect(ratios.getByTestId("field-error-companies.0.ticker")).toContainText("Unknown ticker ZZZZ");
});
