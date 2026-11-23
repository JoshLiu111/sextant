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
});
