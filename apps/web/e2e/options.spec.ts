import { expect, test, type Page } from "@playwright/test";

// Defaults: S = K = 100, T = 1y, sigma = 20%, r = 5%, q = 0% -> call 10.45, put 5.57.
async function openCalculator(page: Page) {
  await page.goto("/options");
  const main = page.getByRole("main");
  await expect(main.getByRole("heading", { level: 1, name: "Options Calculator" })).toBeVisible();
  return main;
}

const metric = (main: ReturnType<Page["getByRole"]>, id: string) => main.locator(`[data-metric-value="${id}"]`);

test("smoke: open the page, submit the defaults, see the results", async ({ page }) => {
  const main = await openCalculator(page);

  await main.getByRole("button", { name: "Calculate" }).click();

  const results = main.getByTestId("results");
  await expect(results).toBeVisible();
  await expect(metric(results, "call_price")).toContainText("10.45");
  await expect(metric(results, "put_price")).toContainText("5.57");
});

test("results show on load without any user action", async ({ page }) => {
  const main = await openCalculator(page);
  const results = main.getByTestId("results");

  await expect(metric(results, "call_price")).toContainText("10.45");
  for (const name of ["Delta", "Gamma", "Vega", "Theta", "Rho"]) {
    await expect(results.getByText(name, { exact: true })).toBeVisible();
  }
  await expect(metric(results, "call_delta")).toContainText("0.6368");
  await expect(main.getByRole("img", { name: /payoff/i })).toBeVisible();
  await expect(main.getByTestId("calculation-id")).toContainText("calc_");
});

test("changing an input updates the results", async ({ page }) => {
  const main = await openCalculator(page);
  await expect(metric(main, "call_price")).toContainText("10.45");

  await main.getByLabel("Volatility (%)").fill("30");

  await expect(metric(main, "call_price")).toContainText("14.23");
});

test("a market price solves for implied volatility; an impossible one explains why", async ({ page }) => {
  const main = await openCalculator(page);
  const iv = metric(main, "implied_volatility");
  await expect(iv).toContainText("Enter a market price");

  await main.getByLabel("Market price").fill("10.4506");
  await expect(iv).toContainText("20.00%");

  await main.getByLabel("Market price").fill("0.01");
  await expect(iv).toContainText("No implied volatility");
  await expect(metric(main, "call_price")).toContainText("10.45");
});

test("invalid input shows an inline error next to the field", async ({ page }) => {
  const main = await openCalculator(page);

  const vol = main.getByLabel("Volatility (%)");
  await vol.fill("-5");

  await expect(vol).toHaveAttribute("aria-invalid", "true");
  await expect(main.getByTestId("field-error-volatility")).toContainText("greater than 0%");
  await expect(main.getByRole("heading", { level: 1, name: "Options Calculator" })).toBeVisible();

  await vol.fill("20");
  await expect(main.getByTestId("field-error-volatility")).toHaveCount(0);
  await expect(metric(main, "call_price")).toContainText("10.45");
});

test("every metric has an explainer", async ({ page }) => {
  const main = await openCalculator(page);
  const metrics = main.locator("[data-metric]");
  await expect(metrics.first()).toBeVisible();

  // Prices (2), Greeks (5) and implied volatility (1), each a card with its own explainer.
  const count = await metrics.count();
  expect(count).toBe(8);
  for (let i = 0; i < count; i++) {
    await expect(metrics.nth(i).getByTestId("explainer")).toHaveCount(1);
  }
  // Every displayed value sits inside an explained card.
  await expect(main.locator("[data-metric-value]")).toHaveCount(
    await main.locator("[data-metric] [data-metric-value]").count(),
  );

  const explainer = main.locator('[data-metric="vega"]').getByTestId("explainer");
  await explainer.getByText("About Vega").click();
  await expect(explainer).toContainText("What it is");
  await expect(explainer).toContainText("How it's computed");
  await expect(explainer).toContainText("How to read it");
  await expect(explainer).toContainText("1 volatility point");
});

test("hovering the chart shows exact values", async ({ page }) => {
  const main = await openCalculator(page);
  const chart = main.getByRole("img", { name: /payoff/i });
  await expect(chart).toBeVisible();

  await chart.hover();

  const tooltip = main.getByTestId("chart-tooltip");
  await expect(tooltip).toBeVisible();
  await expect(tooltip).toContainText("Spot");
  await expect(tooltip).toContainText("Payoff at expiry");
  await expect(tooltip).toContainText("Value today");
  await expect(tooltip).toContainText(/\d+\.\d{2}/);
});

test.describe("mobile width", () => {
  test.use({ viewport: { width: 375, height: 740 } });

  test("the calculator fits without horizontal scroll", async ({ page }) => {
    const main = await openCalculator(page);
    await expect(metric(main, "call_price")).toContainText("10.45");

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(0);
  });
});
