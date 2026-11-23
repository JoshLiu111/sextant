import { expect, test, type Page } from "@playwright/test";

// Position P&L of a saved portfolio after importing trades. Sign-in uses the
// fake OIDC provider (e2e/fake-oidc.mjs); each test signs in with its own email.

function uniqueEmail(label: string) {
  return `${label}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.test`;
}

async function signedInWithPortfolio(page: Page) {
  await page.goto("/portfolio");
  await page.getByRole("banner").getByRole("link", { name: "Sign in with Google" }).click();
  await page.getByLabel("Email").fill(uniqueEmail("positions"));
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page).toHaveURL(/\/portfolio$/);
  const saved = page.getByRole("main").getByRole("region", { name: "Your portfolios" });
  await saved.getByLabel("Portfolio name").fill("Brokerage");
  await saved.getByLabel("Ticker 1").fill("DEMO-C");
  await saved.getByLabel("Quantity 1").fill("1");
  await saved.getByLabel("Cost price 1").fill("50");
  await saved.getByRole("button", { name: "Save portfolio" }).click();
  await expect(saved.getByRole("status").first()).toContainText("Saved");
  return saved;
}

// DEMO-A: 10 @ 100 + 1 fee, sell 4 @ 120 less 1 fee: realized 479 - 4 x 100.1 = 78.60.
// DEMO-B: 4 @ 50, sold 4 @ 45 less 1 fee: realized -21.00, and no longer held.
const TRADES = `Date,Ticker,Side,Quantity,Price,Fees
2024-01-05,DEMO-A,buy,10,100,1
2024-02-01,DEMO-B,buy,4,50,0
2024-03-01,DEMO-A,sell,4,120,1
2024-03-04,DEMO-B,sell,4,45,1
`;

test("after importing trades, each position shows its value, weight and realized P&L", async ({ page }) => {
  const saved = await signedInWithPortfolio(page);
  const importer = saved.getByRole("region", { name: "Import transactions" });
  await importer.getByLabel("CSV file").setInputFiles({ name: "t.csv", mimeType: "text/csv", buffer: Buffer.from(TRADES) });
  await importer.getByRole("button", { name: "Import 4 transactions" }).click();
  await expect(importer.getByRole("status")).toHaveText("Imported 4 transactions.");

  const table = saved.getByRole("table", { name: "Positions" });
  await expect(table.getByRole("columnheader")).toHaveText([
    "Ticker",
    "Quantity",
    "Cost basis",
    "Market value",
    "Weight",
    "Unrealized P&L",
    "Realized P&L",
  ]);
  const row = (ticker: string) => table.locator(`tr[data-ticker="${ticker}"]`);
  await expect(table.locator("tbody tr")).toHaveCount(3);
  await expect(row("DEMO-A").locator('[data-position-value="quantity:DEMO-A"]')).toHaveText("6");
  await expect(row("DEMO-A").locator('[data-position-value="realized_pnl:DEMO-A"]')).toHaveText("78.60");
  await expect(row("DEMO-B").locator('[data-position-value="quantity:DEMO-B"]')).toHaveText("0");
  await expect(row("DEMO-B").locator('[data-position-value="weight:DEMO-B"]')).toHaveText("0.00%");
  await expect(row("DEMO-B").locator('[data-position-value="realized_pnl:DEMO-B"]')).toHaveText("-21.00");
  const totals = table.locator("tfoot tr");
  await expect(totals.locator('[data-position-value="realized_pnl:portfolio"]')).toHaveText("57.60");
  await expect(totals.locator('[data-position-value="cost_basis:portfolio"]')).toHaveText("650.60");
  await expect(totals).toContainText("100.00%");
  await expect(saved.locator('[data-metric="realized_pnl"] [data-metric-value="realized_pnl:portfolio"]')).toContainText("57.60");
});
