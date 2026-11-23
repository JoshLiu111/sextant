import { readFile } from "node:fs/promises";
import { expect, test, type Page } from "@playwright/test";

// Risk & Performance on My data: a signed-in user with a saved Tiingo key
// switches from Demo data to their own Tiingo prices. Tiingo is the fake in
// e2e/fake-tiingo.mjs (keys starting with "good" are valid; it knows AAPL, MSFT
// and SPY, 30 trading days from 2024-01-02; AAPL has a 4:1 split and a 10% max drawdown).

function uniqueEmail(label: string) {
  return `${label}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.test`;
}

async function signIn(page: Page, email: string, { withKey }: { withKey: boolean }) {
  await page.goto("/settings");
  await page.getByRole("main").getByRole("link", { name: "Sign in with Google" }).click();
  await page.getByLabel("Email").fill(email);
  await page.getByRole("button", { name: "Continue" }).click();
  const section = page.getByRole("main").getByRole("region", { name: "Your Tiingo key" });
  await expect(section.getByLabel("Tiingo API key")).toBeVisible();
  if (withKey) {
    await section.getByLabel("Tiingo API key").fill("good0000000000000000000000000000000abcd");
    await section.getByRole("button", { name: "Save key" }).click();
    await expect(section.getByRole("status")).toHaveText("Key saved.");
  }
}

async function openRisk(page: Page) {
  await page.goto("/risk");
  const main = page.getByRole("main");
  // Wait for the first (demo) result so the page is hydrated and the key list has loaded.
  await expect(main.locator('[data-metric-value="annualized_return:DEMO-A"]')).toHaveAttribute("data-status", "ok");
  return main;
}

/** Download the Export CSV file and split it into rows of cells (no quoted fields expected here). */
async function exportCsv(page: Page) {
  const button = page.getByRole("main").getByRole("button", { name: /Export CSV/ });
  const [file] = await Promise.all([page.waitForEvent("download"), button.click()]);
  const text = (await readFile((await file.path())!, "utf8")).replace(/^\uFEFF/, "");
  return { name: file.suggestedFilename(), text, rows: text.trimEnd().split("\r\n").map((r) => r.split(",")) };
}

const metric = (page: Page, id: string) => page.getByRole("main").locator(`[data-metric-value="${id}"]`);

test("visitors and users without a key get no toggle and stay on demo data", async ({ page }) => {
  let main = await openRisk(page);
  await expect(main.getByTestId("demo-badge")).toBeVisible();
  await expect(main.getByTestId("data-mode")).toHaveCount(0);

  await signIn(page, uniqueEmail("nokey"), { withKey: false });
  main = await openRisk(page);
  await expect(main.getByTestId("demo-badge")).toBeVisible();
  await expect(main.getByTestId("data-mode")).toHaveCount(0);
});

test("a user with a Tiingo key switches to My data and sees metrics from their own prices", async ({ page }) => {
  await signIn(page, uniqueEmail("mydata"), { withKey: true });
  const main = await openRisk(page);
  const toggle = main.getByTestId("data-mode");
  await expect(toggle.getByLabel("Demo data")).toBeChecked();

  await toggle.getByText("My data").click();

  await expect(toggle.getByLabel("My data")).toBeChecked();
  await expect(main.getByLabel("Tickers")).toHaveValue("AAPL, MSFT");
  await expect(main.getByRole("textbox", { name: "Benchmark" })).toHaveValue("SPY");
  await expect(main.getByTestId("my-data-note")).toContainText("Tiingo");
  for (const ticker of ["AAPL", "MSFT", "SPY"]) {
    await expect(metric(page, `annualized_volatility:${ticker}`)).toHaveAttribute("data-status", "ok");
  }
  // The 4:1 split is adjusted away: the max drawdown is the 120 -> 108 dip, not a 75% "crash".
  await expect(metric(page, "max_drawdown:AAPL")).toContainText("10.00%");
  await expect(main.getByTestId("demo-badge")).toHaveCount(0);
  await expect(main.getByText("Source: Tiingo")).toBeVisible();

  // Export CSV works on My data: real prices, so no "Synthetic demo data" column.
  const csv = await exportCsv(page);
  expect(csv.name).toBe("sextant-risk-metrics-AAPL_MSFT.csv");
  expect(csv.text).not.toContain("Synthetic demo data");
  expect(csv.rows[0][0]).toBe("Ticker");
  expect(csv.rows.map((r) => r[0])).toEqual(["Ticker", "AAPL", "MSFT", "SPY"]);
  const aapl = csv.rows.find((r) => r[0] === "AAPL")!;
  expect(Number(aapl[csv.rows[0].indexOf("Max drawdown")])).toBeCloseTo(0.1, 6);

  // An unknown real ticker only affects its own metrics.
  await main.getByLabel("Tickers").fill("AAPL, ZZZZ");
  await expect(metric(page, "annualized_return:ZZZZ")).toHaveAttribute("data-status", "missing_data");
  await expect(metric(page, "annualized_return:ZZZZ")).toContainText("Tiingo has no ticker ZZZZ.");
  await expect(metric(page, "annualized_return:AAPL")).toHaveAttribute("data-status", "ok");

  // Back to Demo data: the demo inputs and the Demo badge return.
  await toggle.getByText("Demo data").click();
  await expect(main.getByLabel("Tickers")).toHaveValue("DEMO-A, DEMO-B, DEMO-D");
  await expect(main.getByTestId("demo-badge")).toBeVisible();
});
