import { expect, test, type Page } from "@playwright/test";
import { openRiskTab } from "./risk-helpers";

// Risk & Performance results tabs and key figures (issue #70).

async function openRisk(page: Page, path = "/risk") {
  await page.goto(path);
  const main = page.getByRole("main");
  await expect(main.getByRole("heading", { level: 1, name: "Risk & Performance" })).toBeVisible();
  return main;
}

test("the overview opens first with four key figures for the charted ticker", async ({ page }) => {
  const main = await openRisk(page);
  const tabs = main.getByRole("tablist", { name: "Risk & Performance results" });
  await expect(tabs.getByRole("tab")).toHaveText([
    "Overview",
    "Rolling & distribution",
    "Model checks",
    "Technical analysis",
  ]);
  await expect(tabs.getByRole("tab", { name: "Overview" })).toHaveAttribute("aria-selected", "true");

  const strip = main.getByTestId("key-figures");
  for (const id of ["annualized_return", "annualized_volatility", "max_drawdown", "sharpe"]) {
    await expect(strip.locator(`[data-key-figure="${id}:DEMO-A"]`)).toHaveAttribute("data-status", "ok");
  }
  await expect(strip.locator("[data-key-figure]")).toHaveCount(4);
  // The same values as the metric cards below.
  const card = await main.locator('[data-metric-value="max_drawdown:DEMO-A"]').textContent();
  expect(card).toContain(await strip.locator('[data-key-figure="max_drawdown:DEMO-A"] dd').textContent());

  // The strip follows the underwater chart's ticker.
  await main.getByLabel("Underwater chart for").selectOption("DEMO-D");
  await expect(strip.locator('[data-key-figure="max_drawdown:DEMO-D"]')).toHaveAttribute("data-status", "ok");
  await expect(main.getByRole("img", { name: /underwater/i })).toBeVisible();
});

test("each tab holds its section, and the open tab round-trips through the URL", async ({ page }) => {
  const main = await openRisk(page);
  await expect(main.locator('[data-metric-value="sharpe:DEMO-A"]')).toHaveAttribute("data-status", "ok");
  await expect(main.getByRole("region", { name: "Rolling metrics" })).toHaveCount(0);

  await openRiskTab(main, "Rolling & distribution");
  await expect(page).toHaveURL(/[?&]tab=rolling(&|$)/);
  await expect(main.getByRole("region", { name: "Rolling metrics" })).toBeVisible();
  await expect(main.getByRole("region", { name: "Return distribution" })).toBeVisible();
  await expect(main.getByTestId("key-figures")).toHaveCount(0);

  await openRiskTab(main, "Model checks");
  await expect(page).toHaveURL(/[?&]tab=checks(&|$)/);
  await expect(main.getByTestId("model-checks")).toBeVisible();

  await openRiskTab(main, "Technical analysis");
  await expect(page).toHaveURL(/[?&]tab=technical(&|$)/);
  await expect(main.getByTestId("technical-analysis")).toBeVisible();

  // Calculation info and AI Explain stay below every tab.
  await expect(main.getByTestId("calculation-id")).toContainText("calc_");

  // Submitting the form keeps the open tab in the link.
  await main.getByRole("button", { name: "Calculate" }).click();
  await expect(page).toHaveURL(/[?&]tab=technical(&|$)/);
  await expect(page).toHaveURL(/[?&]tickers=/);

  await page.reload();
  await expect(main.getByRole("tab", { name: "Technical analysis" })).toHaveAttribute("aria-selected", "true");
  await expect(main.getByTestId("technical-analysis")).toBeVisible();
});

test("an unknown tab in the link opens the overview", async ({ page }) => {
  const main = await openRisk(page, "/risk?tab=nonsense");
  await expect(main.getByRole("tab", { name: "Overview" })).toHaveAttribute("aria-selected", "true");
  await expect(main.getByTestId("key-figures")).toBeVisible();
});

test("the input form stays in view on desktop", async ({ page }) => {
  const main = await openRisk(page);
  const form = main.locator('form[aria-labelledby="risk-inputs"]');
  await expect(form).toHaveCSS("position", "sticky");
});
