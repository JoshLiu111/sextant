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
    // The card's heading; its explainer popover repeats the name.
    await expect(results.getByRole("heading", { name, exact: true })).toBeVisible();
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

  // The whole card opens its explainer: a click on the figure, not just the info button.
  const card = main.locator('[data-metric="vega"]');
  const explainer = card.getByTestId("explainer");
  await expect(card.getByRole("button", { name: "About Vega" })).toBeVisible();
  await card.click();
  await expect(explainer.locator(".explainer-pop")).toBeVisible();
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

// The view tabs (the shared URL-backed tablist, issue #70).
test.describe("view tabs", () => {
  test("an unknown tab in the link opens the first tab", async ({ page }) => {
    await page.goto("/options?tab=nonsense");
    const main = page.getByRole("main");
    const tabs = main.getByRole("tablist", { name: "Options Calculator views" });
    await expect(tabs.getByRole("tab", { name: "Single option" })).toHaveAttribute("aria-selected", "true");
    await expect(main.getByRole("tabpanel", { name: "Single option" })).toBeVisible();
  });

  test("arrow keys move between tabs, and the open tab goes into the URL", async ({ page }) => {
    await page.goto("/options");
    const main = page.getByRole("main");
    const single = main.getByRole("tab", { name: "Single option" });
    const strategy = main.getByRole("tab", { name: "Strategy builder" });
    const american = main.getByRole("tab", { name: "American (binomial)" });
    // Only the open tab is in the Tab order.
    await expect(single).toHaveAttribute("tabindex", "0");
    await expect(strategy).toHaveAttribute("tabindex", "-1");

    // Server-rendered: a key before hydration is lost, so retry until it lands.
    await expect(async () => {
      await single.focus();
      await page.keyboard.press("ArrowRight");
      await expect(strategy).toHaveAttribute("aria-selected", "true", { timeout: 1000 });
    }).toPass();
    await expect(strategy).toBeFocused();
    await expect(page).toHaveURL(/[?&]tab=strategy(&|$)/);

    await page.keyboard.press("End");
    await expect(american).toHaveAttribute("aria-selected", "true");
    await page.keyboard.press("ArrowRight");
    await expect(single).toHaveAttribute("aria-selected", "true");
    await page.keyboard.press("ArrowLeft");
    await expect(american).toHaveAttribute("aria-selected", "true");
    await page.keyboard.press("Home");
    await expect(single).toHaveAttribute("aria-selected", "true");
    await expect(page).toHaveURL(/[?&]tab=single(&|$)/);
  });
});
