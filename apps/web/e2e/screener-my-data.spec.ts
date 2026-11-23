import { expect, test, type Page } from "@playwright/test";

// Screener price criteria (story 84) on the user's own Tiingo prices. EDGAR
// frames come from e2e/fake-edgar.mjs (default year 2025: the default screen
// matches AMZN, GOOGL, MSFT, NVDA, META, LLY, AVGO, NFLX, ADBE). Prices come
// from e2e/fake-tiingo.mjs (keys starting with "good" are valid), with the
// 52-week window pinned to end 2026-11-20 (SCREENER_PRICES_AS_OF). 52-week
// change: NVDA +50%, GOOGL +40%, AMZN and AVGO +20%, LLY +15%, META and NFLX
// -10%; MSFT has no prices in the window and ADBE none at all.

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

async function openScreener(page: Page) {
  await page.goto("/screener");
  const main = page.getByRole("main");
  // A cold screen fetches ~20 frames through the EDGAR limiter; by then the key list has loaded too.
  await expect(main.getByTestId("screen-summary")).toBeVisible({ timeout: 30_000 });
  return main;
}

type Main = Awaited<ReturnType<typeof openScreener>>;
const results = (main: Main) => main.getByRole("table", { name: "Screen results" });
const rowTickers = (main: Main) =>
  results(main)
    .locator("[data-ticker]")
    .evaluateAll((rows) => rows.map((r) => r.getAttribute("data-ticker")));
const metricOptions = (main: Main) =>
  main
    .getByLabel("Metric for criterion 1")
    .locator("option")
    .evaluateAll((options) => options.map((o) => o.textContent));

test("visitors and users without a key get no price criteria", async ({ page }) => {
  let main = await openScreener(page);
  expect(await metricOptions(main)).not.toContain("52-week change");
  await expect(main.getByTestId("price-criteria-note")).toContainText("sign in and add a price data key");

  await signIn(page, uniqueEmail("screen-nokey"), { withKey: false });
  main = await openScreener(page);
  expect(await metricOptions(main)).not.toContain("52-week change");
});

test("a user with a Tiingo key screens on fundamentals and 52-week change together", async ({ page }) => {
  await signIn(page, uniqueEmail("screen-mydata"), { withKey: true });
  const main = await openScreener(page);
  await expect(main.getByTestId("price-criteria-note")).toContainText("Tiingo");
  await expect.poll(() => metricOptions(main)).toContain("52-week change");

  await main.getByRole("button", { name: "Add criterion" }).click();
  await main.getByLabel("Metric for criterion 4").selectOption({ label: "52-week change" });
  await main.getByLabel("Value for criterion 4").fill("18");
  await main.getByRole("button", { name: "Run screen" }).click();

  await expect.poll(() => rowTickers(main)).toEqual(["AMZN", "GOOGL", "NVDA", "AVGO"]);
  const nvda = results(main).locator('[data-ticker="NVDA"]');
  await expect(nvda.locator('[data-metric-value="change_52w"]')).toHaveText("50.0%");
  await expect(nvda.locator('[data-metric-value="revenue_growth"]')).toHaveText("65.5%");
  const summary = main.getByTestId("screen-summary");
  await expect(summary).toContainText("Tiingo has no ticker ADBE.");
  await expect(summary).toContainText("No Tiingo prices for MSFT");
  await expect(main.getByTestId("prices-info")).toContainText("Prices: Tiingo, as of 2026-11-20");

  // Sorting by the price column works like any other column.
  await results(main).getByRole("button", { name: "52-week change" }).click();
  await expect.poll(() => rowTickers(main)).toEqual(["NVDA", "GOOGL", "AMZN", "AVGO"]);
});
