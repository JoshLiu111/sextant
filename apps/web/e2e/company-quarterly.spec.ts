import { expect, test, type Page } from "@playwright/test";

// Quarterly statements and ratios, and the ratio drill-down, on /company with
// the recorded EDGAR fixtures (10-K and 10-Q facts) served by e2e/fake-edgar.mjs.
// AAPL: Q3 FY2026 ended 2026-06-27, Q4 FY2026 (= FY2026) on 2026-09-26.

const COLD = { timeout: 30_000 }; // the first load compiles the page and parses the fixtures

async function openCompany(page: Page, path = "/company") {
  await page.goto(path);
  const main = page.getByRole("main");
  await expect(main.getByRole("heading", { level: 1, name: "Company Health Check" })).toBeVisible();
  return main;
}

test("toggle to quarterly: fiscal-quarter columns, Q4 derived from the year, TTM ratios", async ({ page }) => {
  const main = await openCompany(page);
  const ratios = main.getByTestId("ratios");
  await expect(ratios.locator('[data-metric-value="current_ratio:AAPL:2026-09-26"]')).toHaveText("1.02", COLD);

  await main.getByRole("radio", { name: "Quarterly" }).check();
  await expect(page).toHaveURL(/frequency=quarterly/);

  const statements = main.getByTestId("results");
  const income = statements.getByRole("table", { name: "Income statement" });
  await expect(income.getByRole("columnheader", { name: /Q4 FY2026/ })).toBeVisible();
  await expect(income.getByRole("columnheader", { name: /Q1 FY2026/ })).toBeVisible();
  // Q4 revenue = FY2026 (478,834) minus the nine months to Q3 (364,357).
  const q4Revenue = statements.locator('[data-metric-value="revenue:2026-09-26"]');
  await expect(q4Revenue).toHaveText("114,477");
  await expect(q4Revenue).toHaveAttribute("title", /minus the nine months to 2026-06-27/);

  const efficiency = ratios.getByRole("table", { name: "Efficiency" });
  await expect(efficiency.getByRole("columnheader", { name: "Q3 FY2026" })).toBeVisible();
  await expect(ratios.locator('[data-metric-value="asset_turnover:AAPL:2026-06-27"]')).toHaveText("1.31");
  await expect(efficiency.getByRole("rowheader", { name: /Asset turnover/ }).getByText("TTM")).toBeVisible();
  await expect(ratios.getByText(/use trailing twelve months/)).toBeVisible();
});

test("a quarterly link loads quarterly, and the drill-down lists the four quarters", async ({ page }) => {
  const main = await openCompany(page, "/company?frequency=quarterly");
  const ratios = main.getByTestId("ratios");
  await expect(main.getByRole("radio", { name: "Quarterly" })).toBeChecked(COLD);
  await expect(ratios.locator('[data-metric-value="asset_turnover:AAPL:2026-06-27"]')).toHaveText("1.31", COLD);

  await ratios.getByRole("button", { name: "Show the inputs of Asset turnover for Q3 FY2026" }).click();
  const dialog = page.getByRole("dialog", { name: "Asset turnover · AAPL · Q3 FY2026" });
  await expect(dialog).toBeVisible();
  await expect(dialog.locator("math")).toBeVisible();
  await expect(dialog.locator("math")).toContainText("Revenue");
  await expect(dialog.locator("math")).toContainText("Average total assets");
  await expect(dialog.getByText("1.31", { exact: true })).toBeVisible();
  const inputs = dialog.getByRole("table", { name: "Inputs" });
  await expect(inputs.getByRole("rowheader", { name: "Revenue" })).toBeVisible();
  await expect(inputs.getByText("466,823", { exact: true })).toBeVisible();
  for (const quarter of ["Q4 FY2025", "Q1 FY2026", "Q2 FY2026", "Q3 FY2026"]) {
    await expect(inputs.getByText(quarter).first()).toBeVisible();
  }
  await expect(inputs.getByRole("link", { name: "10-K filed 2025-10-31" })).toHaveAttribute(
    "href",
    /^https:\/\/www\.sec\.gov\/Archives\/edgar\/data\/320193\//,
  );
  await dialog.getByRole("button", { name: "Close" }).click();
  await expect(dialog).toBeHidden();
});

test("drill into an annual ratio: formula, inputs and their 10-K", async ({ page }) => {
  const main = await openCompany(page);
  const ratios = main.getByTestId("ratios");
  await expect(ratios.locator('[data-metric-value="current_ratio:AAPL:2026-09-26"]')).toHaveText("1.02", COLD);

  await ratios.getByRole("button", { name: "Show the inputs of Current ratio for FY2026" }).click();
  const dialog = page.getByRole("dialog", { name: "Current ratio · AAPL · FY2026" });
  await expect(dialog.locator("math")).toBeVisible();
  await expect(dialog.locator("math")).toContainText("Current assets");
  await expect(dialog.locator("math")).toContainText("Current liabilities");
  const inputs = dialog.getByRole("table", { name: "Inputs" });
  await expect(inputs.getByRole("rowheader", { name: "Total Current Assets" })).toBeVisible();
  await expect(inputs.getByText("173,857", { exact: true })).toBeVisible();
  await expect(inputs.getByRole("link", { name: "10-K filed 2026-11-03" }).first()).toBeVisible();
});

test("the toggle keeps the shared-link inputs in the URL", async ({ page }) => {
  const main = await openCompany(page, "/company?companies=MSFT&ticker=MSFT");
  const ratios = main.getByTestId("ratios");
  const liquidity = ratios.getByRole("table", { name: "Liquidity" });
  await expect(liquidity.getByRole("columnheader", { name: "FY2026", exact: true })).toBeVisible(COLD);

  await main.getByRole("radio", { name: "Quarterly" }).check();
  await expect(page).toHaveURL(/companies=MSFT/);
  await expect(page).toHaveURL(/frequency=quarterly/);
  await expect(liquidity.getByRole("columnheader", { name: "Q1 FY2027" })).toBeVisible();
  await main.getByRole("radio", { name: "Annual" }).check();
  await expect(page).not.toHaveURL(/frequency=/);
  await expect(liquidity.getByRole("columnheader", { name: "FY2026", exact: true })).toBeVisible();
});
