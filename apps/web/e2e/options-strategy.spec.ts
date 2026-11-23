import { expect, test, type Locator, type Page } from "@playwright/test";

// Market defaults: S = 100, T = 1y, sigma = 20%, r = 5%, q = 0%.
// Default strategy: bull call spread, long 95 call / short 105 call -> debit 5.3251, max gain 4.6749.
async function openTab(page: Page, tab: string) {
  await page.goto("/options");
  const main = page.getByRole("main");
  await main.getByRole("tab", { name: tab }).click();
  return main;
}

const metric = (scope: Locator, id: string) => scope.locator(`[data-metric-value="${id}"]`);
const legRows = (main: Locator) => main.getByTestId("strategy-leg");

test("smoke: the strategy builder shows a default strategy's payoff and summed Greeks", async ({ page }) => {
  const main = await openTab(page, "Strategy builder");

  await main.getByRole("button", { name: "Calculate" }).click();

  const results = main.getByTestId("results");
  await expect(legRows(main)).toHaveCount(2);
  await expect(metric(results, "net_cost")).toContainText("5.3251");
  await expect(metric(results, "max_profit")).toContainText("4.6749");
  await expect(metric(results, "max_loss")).toContainText("5.3251");
  await expect(metric(results, "delta")).toContainText("0.1857");
  await expect(main.getByRole("img", { name: /strategy's profit/i })).toBeVisible();
  await expect(main.getByTestId("calculation-id")).toContainText("calc_");
});

test("presets load their legs; the iron condor has a capped gain and loss", async ({ page }) => {
  const main = await openTab(page, "Strategy builder");

  await main.getByRole("button", { name: "Iron condor" }).click();

  await expect(legRows(main)).toHaveCount(4);
  await expect(main.getByLabel("Strike 1")).toHaveValue("80");
  await expect(main.getByLabel("Position 2")).toHaveValue("short");
  await expect(main.getByLabel("Strike 4")).toHaveValue("120");
  await expect(metric(main, "net_cost")).toContainText("-4.4155");
  await expect(metric(main, "max_profit")).toContainText("4.4155");
  await expect(metric(main, "max_loss")).toContainText("5.5845");

  await main.getByRole("button", { name: "Straddle" }).click();
  await expect(legRows(main)).toHaveCount(2);
  await expect(metric(main, "max_profit")).toContainText("Unlimited");
  await expect(metric(main, "max_loss")).toContainText("16.0241");
});

test("legs can be added, edited and removed", async ({ page }) => {
  const main = await openTab(page, "Strategy builder");
  await expect(metric(main, "net_cost")).toContainText("5.3251");

  await main.getByRole("button", { name: "Remove leg 2" }).click();
  await expect(legRows(main)).toHaveCount(1);
  await main.getByRole("button", { name: "Add leg" }).click();
  await expect(legRows(main)).toHaveCount(2);
  await main.getByLabel("Instrument 2").selectOption("underlying");
  await expect(main.getByLabel("Strike 2")).toBeDisabled();

  await main.getByLabel("Strike 1").fill("");
  await expect(main.getByTestId("field-error-legs.0.strike")).toContainText("Enter a strike");
});

test("Greek curves can be plotted against spot or time to expiry", async ({ page }) => {
  const main = await openTab(page, "Strategy builder");
  const chart = main.getByRole("img", { name: /Greek/ });
  await expect(chart).toBeVisible();

  await main.getByLabel("Greek", { exact: true }).selectOption("gamma");
  await main.getByLabel("Plot against", { exact: true }).selectOption("time");
  await chart.hover();

  const tooltip = main.getByTestId("chart-tooltip");
  await expect(tooltip).toContainText("Time to expiry");
  await expect(tooltip).toContainText("Gamma");
});

test("American pricing shows the tree price next to Black-Scholes with the early-exercise premium", async ({ page }) => {
  const main = await openTab(page, "American (binomial)");
  const results = main.getByTestId("results");

  await expect(metric(results, "european_put")).toContainText("5.5735");
  await expect(metric(results, "american_put")).toContainText("6.0888");
  await expect(metric(results, "put_early_exercise_premium")).toContainText("0.5193");
  await expect(metric(results, "call_early_exercise_premium")).toContainText("0.0000");
  await expect(main.getByRole("img", { name: /steps/i })).toBeVisible();

  await main.getByLabel("Steps", { exact: true }).fill("0");
  await expect(main.getByTestId("field-error-steps")).toContainText("at least 1");
});

test.describe("mobile width", () => {
  test.use({ viewport: { width: 375, height: 740 } });

  test("the strategy builder fits without horizontal scroll", async ({ page }) => {
    const main = await openTab(page, "Strategy builder");
    await main.getByRole("button", { name: "Iron condor" }).click();
    await expect(metric(main, "max_loss")).toContainText("5.5845");

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(0);
  });
});
