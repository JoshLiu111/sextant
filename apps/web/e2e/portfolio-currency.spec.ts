import { expect, test, type Locator, type Page } from "@playwright/test";

// Reporting currency of a saved portfolio: holdings in other currencies convert at
// each date's Frankfurter rate. Rates come from e2e/fake-frankfurter.mjs, which
// serves the recorded responses in apps/compute/tests/fixtures/frankfurter.

function uniqueEmail(label: string) {
  return `${label}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.test`;
}

type Holding = { ticker: string; quantity: string; cost: string; currency: string };

async function signedInWithPortfolio(page: Page, holdings: Holding[]) {
  await page.goto("/portfolio");
  await page.getByRole("banner").getByRole("link", { name: "Sign in with Google" }).click();
  await page.getByLabel("Email").fill(uniqueEmail("currency"));
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page).toHaveURL(/\/portfolio$/);
  const saved = page.getByRole("main").getByRole("region", { name: "Your portfolios" });
  await saved.getByLabel("Portfolio name").fill("Two currencies");
  for (const [i, h] of holdings.entries()) {
    if (i > 0) await saved.getByRole("button", { name: "Add holding" }).click();
    await saved.getByLabel(`Ticker ${i + 1}`).fill(h.ticker);
    await saved.getByLabel(`Quantity ${i + 1}`).fill(h.quantity);
    await saved.getByLabel(`Cost price ${i + 1}`).fill(h.cost);
    await saved.getByLabel(`Currency ${i + 1}`).fill(h.currency);
  }
  await saved.getByRole("button", { name: "Save portfolio" }).click();
  await expect(saved.getByRole("status").first()).toContainText("Saved");
  return saved;
}

async function amount(cell: Locator): Promise<number> {
  await expect(cell).toHaveAttribute("data-status", "ok");
  return Number((await cell.innerText()).replace(/,/g, ""));
}

test("a holding in euros is valued in the reporting currency at the closing date's rate", async ({ page }) => {
  const saved = await signedInWithPortfolio(page, [
    { ticker: "DEMO-C", quantity: "1", cost: "50", currency: "USD" },
    { ticker: "DEMO-D", quantity: "2", cost: "40", currency: "EUR" },
  ]);
  await expect(page.getByRole("contentinfo")).toContainText("Exchange rates: Frankfurter (frankfurter.dev).");

  const reporting = saved.getByLabel("Reporting currency");
  await expect(reporting).toHaveValue("USD");
  await saved.getByLabel("End date").fill("2024-06-28");
  const value = saved.locator('[data-position-value="market_value:DEMO-D"]');

  await reporting.fill("EUR");
  await expect(saved.getByRole("table", { name: "Positions" }).locator("caption")).toContainText("(EUR)");
  const inEuros = await amount(value);
  await reporting.fill("USD");
  await expect(saved.getByRole("table", { name: "Positions" }).locator("caption")).toContainText("(USD)");
  const inDollars = await amount(value);

  // EUR -> USD on 2024-06-28 was 1.0703 (recorded), not today's rate.
  expect(inDollars).toBeCloseTo(inEuros * 1.0703, 1);
  await expect(saved.locator('[data-metric-value="market_value:portfolio"]')).toContainText("USD");
  await expect(saved.getByTestId("portfolio-returns").locator('[data-metric-value="twr:portfolio"]')).toHaveAttribute(
    "data-status",
    "ok",
  );
});

test("a currency Frankfurter does not publish shows why its values are missing", async ({ page }) => {
  const saved = await signedInWithPortfolio(page, [
    { ticker: "DEMO-C", quantity: "1", cost: "50", currency: "USD" },
    { ticker: "DEMO-D", quantity: "2", cost: "40", currency: "XYZ" },
  ]);

  await expect(saved.locator('[data-metric-value="market_value:portfolio"]')).toContainText(
    "Frankfurter has no exchange rates for XYZ.",
  );
  await expect(saved.locator('[data-position-value="market_value:DEMO-C"]')).toHaveAttribute("data-status", "ok");
  await expect(saved.locator('[data-position-value="market_value:DEMO-D"]')).toHaveAttribute(
    "data-status",
    "missing_data",
  );
});
