import { expect, test, type Page } from "@playwright/test";

// Compute serves EDGAR from recorded fixtures through e2e/fake-edgar.mjs.
// Default ticker MSFT, base year FY2026. Free cash flow to the firm =
// OCF 182,935M + interest 3,051M x (1 - 19.40% tax) - capex 115,948M = 69,446M.
// Short-term investments 55,908M join cash in the equity bridge.
// With the default assumptions the DCF gives $163.73 per share.

async function openValuation(page: Page, query = "") {
  await page.goto(`/valuation${query}`);
  const main = page.getByRole("main");
  await expect(main.getByRole("heading", { level: 1, name: "Valuation Calculator" })).toBeVisible();
  return main;
}

type Main = Awaited<ReturnType<typeof openValuation>>;
const value = (main: Main, id: string) => main.locator(`[data-metric-value="${id}"]`);

test("smoke: submit the defaults and see the DCF, WACC breakdown and sensitivity table", async ({ page }) => {
  const main = await openValuation(page);
  await expect(main.getByLabel("Ticker")).toHaveValue("MSFT");

  await main.getByRole("button", { name: "Value company" }).click();

  const results = main.getByTestId("results");
  await expect(results.getByRole("heading", { name: "MICROSOFT CORP" })).toBeVisible();
  await expect(value(results, "intrinsic_value_per_share")).toHaveAttribute("data-status", "ok");
  await expect(value(results, "intrinsic_value_per_share")).toContainText("$163.73");
  await expect(value(results, "free_cash_flow")).toContainText("$69.45B");
  await expect(value(results, "short_term_investments")).toContainText("$55.91B");
  for (const id of ["enterprise_value", "equity_value", "cost_of_equity", "cost_of_debt", "tax_rate", "wacc"]) {
    await expect(value(results, id)).toHaveAttribute("data-status", "ok");
  }
  await expect(value(results, "wacc")).toContainText("9.22%");
  const grid = results.getByRole("table", { name: "Sensitivity: value per share" });
  await expect(grid).toBeVisible();
  await expect(grid.locator('[data-metric-value="sensitivity:2:2"]')).toHaveText("$163.73");
  await expect(grid.locator("[data-metric-value^='sensitivity:']")).toHaveCount(25);
});

test("changing an assumption updates the results", async ({ page }) => {
  const main = await openValuation(page);
  await expect(value(main, "intrinsic_value_per_share")).toContainText("$163.73");

  await main.getByLabel("Growth rate (%)").fill("8");

  await expect(value(main, "intrinsic_value_per_share")).toContainText("$185.06");
});

test("overriding a WACC component updates the WACC", async ({ page }) => {
  const main = await openValuation(page);
  await expect(value(main, "wacc")).toContainText("9.22%");

  await main.getByLabel("Cost of equity (%)").fill("12");

  await expect(value(main, "cost_of_equity")).toContainText("12.00%");
  await expect(value(main, "cost_of_equity")).toContainText("Your override");
  await expect(value(main, "wacc")).not.toContainText("9.22%");
});

test("terminal growth at or above the discount rate is a clear inline error", async ({ page }) => {
  const main = await openValuation(page);
  await expect(value(main, "intrinsic_value_per_share")).toHaveAttribute("data-status", "ok");

  await main.getByLabel("Discount rate (%)").fill("2");

  await expect(main.getByTestId("field-error-terminal_growth")).toHaveText(
    "Terminal growth must be below the discount rate.",
  );
  await expect(main.getByLabel("Terminal growth (%)")).toHaveAttribute("aria-invalid", "true");
});

test("missing statement inputs show missing data naming the item", async ({ page }) => {
  const main = await openValuation(page, "?ticker=JPM");
  await expect(main.getByLabel("Ticker")).toHaveValue("JPM");

  await expect(value(main, "free_cash_flow")).toHaveAttribute("data-status", "missing_data");
  await expect(value(main, "free_cash_flow")).toContainText("Capital Expenditure is not reported by this company.");
  await expect(value(main, "intrinsic_value_per_share")).toHaveAttribute("data-status", "missing_data");
});

test("the ticker URL parameter picks the company", async ({ page }) => {
  const main = await openValuation(page, "?ticker=wmt");

  await expect(main.getByRole("heading", { name: "Walmart Inc." })).toBeVisible();
});

test("every input and output has an explainer, and the footer shows the SEC attribution", async ({ page }) => {
  const main = await openValuation(page);
  await expect(value(main, "intrinsic_value_per_share")).toHaveAttribute("data-status", "ok");

  for (const label of ["Ticker", "Growth rate (%)", "Beta", "Equity risk premium (%)", "Share price ($)"]) {
    await expect(main.getByText(`About ${label.replace(/ \(.*\)$/, "").toLowerCase()}`, { exact: true })).toHaveCount(1);
  }
  for (const card of ["intrinsic_value_per_share", "wacc", "cost_of_debt", "capital_structure", "free_cash_flow"]) {
    await expect(main.locator(`[data-metric="${card}"]`).getByTestId("explainer")).toHaveCount(1);
  }
  await expect(main.locator('[data-testid="sensitivity"]').getByTestId("explainer")).toHaveCount(1);
  await expect(page.getByRole("contentinfo").locator('[data-attribution="sec"]')).toBeVisible();
});

test.describe("mobile width", () => {
  test.use({ viewport: { width: 375, height: 740 } });

  test("the page fits without horizontal scroll", async ({ page }) => {
    const main = await openValuation(page);
    await expect(value(main, "intrinsic_value_per_share")).toHaveAttribute("data-status", "ok");

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(0);
  });
});
