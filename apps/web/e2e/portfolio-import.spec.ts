import { expect, test, type Locator, type Page } from "@playwright/test";

// Importing transactions from CSV into a saved portfolio. Sign-in uses the
// fake OIDC provider (e2e/fake-oidc.mjs); each test signs in with its own email.

function uniqueEmail(label: string) {
  return `${label}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.test`;
}

async function signedInWithPortfolio(page: Page) {
  await page.goto("/portfolio");
  await page.getByRole("banner").getByRole("link", { name: "Sign in with Google" }).click();
  await page.getByLabel("Email").fill(uniqueEmail("import"));
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

async function upload(region: Locator, name: string, csv: string) {
  await region.getByLabel("CSV file").setInputFiles({ name, mimeType: "text/csv", buffer: Buffer.from(csv) });
}

const BROKER_CSV = `Trade Date,Symbol,Action,Quantity,Price,Commission
2024-01-05,DEMO-A,Buy,10,100.00,1.00
2024-13-40,DEMO-B,Buy,4,25,0
2024-02-01,DEMO-B,Buy,4,25,0
2024-03-01,DEMO-A,Hold,1,120,0
`;

test("a user previews a broker CSV, sees the bad rows, and imports the rest into the portfolio", async ({ page }) => {
  const saved = await signedInWithPortfolio(page);
  const importer = saved.getByRole("region", { name: "Import transactions" });

  await upload(importer, "trades.csv", BROKER_CSV);

  // The mapping is guessed from the broker's headers.
  await expect(importer.getByLabel("Column for Date")).toHaveValue("Trade Date");
  await expect(importer.getByLabel("Column for Ticker")).toHaveValue("Symbol");
  await expect(importer.getByLabel("Column for Buy/sell")).toHaveValue("Action");
  await expect(importer.getByLabel("Column for Fees")).toHaveValue("Commission");
  await expect(importer.getByLabel("Column for Currency")).toHaveValue("");

  const preview = importer.getByRole("table", { name: "First rows of the file" });
  await expect(preview.getByRole("columnheader")).toHaveText(["Line", "Trade Date", "Symbol", "Action", "Quantity", "Price", "Commission"]);
  await expect(preview.getByRole("row").nth(1)).toContainText("DEMO-A");

  const errors = importer.getByTestId("import-errors");
  await expect(errors.getByRole("listitem")).toHaveCount(2);
  await expect(errors.getByRole("listitem").nth(0)).toContainText("Line 3");
  await expect(errors.getByRole("listitem").nth(1)).toContainText("Line 5");
  await expect(errors.getByRole("listitem").nth(1)).toContainText("Hold");
  await expect(importer.getByTestId("import-summary")).toHaveText("2 rows will be imported, 2 will be skipped.");

  await importer.getByRole("button", { name: "Import 2 transactions" }).click();

  await expect(importer.getByRole("status")).toHaveText("Imported 2 transactions.");
  await expect(saved.getByLabel("Ticker 2")).toHaveValue("DEMO-A");
  await expect(saved.getByLabel("Quantity 2")).toHaveValue("10");
  await expect(saved.getByLabel("Cost price 2")).toHaveValue("100.1");
  await expect(saved.getByLabel("Ticker 3")).toHaveValue("DEMO-B");
  await expect(saved.locator('[data-metric-value="cost_basis:portfolio"]')).toContainText("1,151.00");

  // The import is stored: it survives a reload.
  await page.reload();
  await expect(saved.getByLabel("Ticker 3")).toHaveValue("DEMO-B");
});

test("a user maps the columns of an unfamiliar file before importing", async ({ page }) => {
  const saved = await signedInWithPortfolio(page);
  const importer = saved.getByRole("region", { name: "Import transactions" });

  await upload(importer, "mine.csv", "When,What,Direction,How many,At\n2024-05-01,DEMO-E,buy,3,20\n");

  await expect(importer.getByText("Choose a column for every required field")).toBeVisible();
  await expect(importer.getByRole("button", { name: /^Import \d/ })).toHaveCount(0);

  await importer.getByLabel("Column for Date").selectOption("When");
  await importer.getByLabel("Column for Ticker").selectOption("What");
  await importer.getByLabel("Column for Buy/sell").selectOption("Direction");
  await importer.getByLabel("Column for Quantity").selectOption("How many");
  await importer.getByLabel("Column for Price").selectOption("At");

  await expect(importer.getByTestId("import-summary")).toHaveText("1 row will be imported.");
  await importer.getByRole("button", { name: "Import 1 transaction" }).click();
  await expect(importer.getByRole("status")).toHaveText("Imported 1 transaction.");
  await expect(saved.getByLabel("Ticker 2")).toHaveValue("DEMO-E");
});

test("without a provider key, the preview says stock splits were not checked", async ({ page }) => {
  const saved = await signedInWithPortfolio(page);
  const importer = saved.getByRole("region", { name: "Import transactions" });

  await upload(importer, "trades.csv", "Date,Ticker,Side,Quantity,Price\n2024-01-02,AAPL,buy,10,400\n");

  await expect(importer.getByTestId("import-summary")).toHaveText("1 row will be imported.");
  const warnings = importer.getByTestId("import-warnings");
  await expect(warnings).toContainText("Stock splits were not checked for AAPL");
  await expect(warnings).toContainText("Tiingo or FMP key");
  await expect(importer.getByTestId("import-splits")).toHaveCount(0);
});
