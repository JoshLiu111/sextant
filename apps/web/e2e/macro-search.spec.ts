import { expect, test, type Page } from "@playwright/test";

// Search FRED and add series to the Macro Dashboard (stories 78, 94). Compute
// talks to the fake FRED (e2e/fake-fred.mjs), which serves the recorded search,
// tags and series responses in apps/compute/tests/fixtures/fred.
const COLD = { timeout: 30_000 };

async function openYourSeries(page: Page, path = "/macro") {
  await page.goto(path);
  const main = page.getByRole("main");
  await expect(main.getByRole("heading", { level: 1, name: "Macro Dashboard" })).toBeVisible();
  // Wait for a first result so hydration doesn't race the inputs.
  await expect(main.locator('[data-metric-value="latest:unemployment_rate"]')).toHaveAttribute(
    "data-status",
    "ok",
    COLD,
  );
  return main.getByTestId("custom-series");
}

async function search(section: Awaited<ReturnType<typeof openYourSeries>>, query: string) {
  await section.getByLabel("Search FRED").fill(query);
  await section.getByRole("button", { name: "Search" }).click();
}

test("search offers public-domain series only, with units, frequency and last update", async ({ page }) => {
  const section = await openYourSeries(page);
  await search(section, "unemployment");

  const results = section.getByRole("list", { name: "Search results" });
  await expect(results.locator("[data-series-hit]")).toHaveCount(2, COLD);
  // LRUN64TTUSM156S (OECD, copyrighted) is in FRED's answer but never offered.
  await expect(results.locator('[data-series-hit="LRUN64TTUSM156S"]')).toHaveCount(0);
  const nsa = results.locator('[data-series-hit="UNRATENSA"]');
  await expect(nsa).toContainText("Unemployment Rate");
  await expect(nsa).toContainText("Percent");
  await expect(nsa).toContainText("Monthly (NSA)");
  await expect(nsa).toContainText("2026-11-06 13:48 UTC");
  await expect(section.getByText(/copyrighted series are excluded/)).toBeVisible();
});

test("a search with only copyrighted matches says nothing can be offered", async ({ page }) => {
  const section = await openYourSeries(page);
  await search(section, "high yield");

  await expect(section.getByTestId("search-empty")).toContainText("high yield", COLD);
});

test("an added series shows its value, source, units, frequency and last update, and can be removed", async ({
  page,
}) => {
  const section = await openYourSeries(page);
  await search(section, "payroll");
  await section.getByRole("button", { name: "Add PAYEMS" }).click();

  const card = section.locator('[data-indicator="fred:PAYEMS"]');
  const value = card.locator('[data-metric-value="latest:PAYEMS"]');
  await expect(value).toHaveAttribute("data-status", "ok", COLD);
  await expect(value).toContainText("157,995");
  await expect(card.getByRole("heading", { name: "All Employees, Total Nonfarm" })).toBeVisible();
  const meta = card.getByTestId("series-meta");
  await expect(meta).toContainText("U.S. Bureau of Labor Statistics");
  await expect(meta).toContainText("Thousands of Persons");
  await expect(meta).toContainText("Monthly (SA)");
  await expect(meta).toContainText("2026-11-06 13:48 UTC");
  await expect(meta.getByRole("link", { name: "PAYEMS" })).toHaveAttribute(
    "href",
    "https://fred.stlouisfed.org/series/PAYEMS",
  );
  await expect(card.getByRole("img", { name: "All Employees, Total Nonfarm history" })).toBeVisible();
  await expect(section.getByRole("button", { name: "Add PAYEMS" })).toBeDisabled();
  await expect(page).toHaveURL(/[?&]series=PAYEMS(&|$)/);

  await card.getByRole("button", { name: "Remove PAYEMS" }).click();
  await expect(card).toHaveCount(0);
  await expect(page).not.toHaveURL(/series=/);
});

test("a shared URL reproduces the same board", async ({ page }) => {
  const section = await openYourSeries(page, "/macro?series=UNRATENSA,PAYEMS&start=2020-01-01");

  const cards = section.locator("[data-indicator^='fred:']");
  await expect(cards).toHaveCount(2);
  await expect(section.locator('[data-metric-value="latest:UNRATENSA"]')).toContainText("4.10%", COLD);
  await expect(section.locator('[data-metric-value="latest:PAYEMS"]')).toContainText("157,995", COLD);
  expect(await cards.evaluateAll((els) => els.map((e) => e.getAttribute("data-indicator")))).toEqual([
    "fred:UNRATENSA",
    "fred:PAYEMS",
  ]);
  // The board's chart range comes along too.
  await expect(page.getByRole("main").getByLabel("History from")).toHaveValue("2020-01-01");
  await expect(section.getByRole("img", { name: "All Employees, Total Nonfarm history" })).toBeVisible();
});

test("a shared URL naming a copyrighted series shows it as missing, not its data", async ({ page }) => {
  const section = await openYourSeries(page, "/macro?series=T10Y2Y");

  const value = section.locator('[data-metric-value="latest:T10Y2Y"]');
  await expect(value).toHaveAttribute("data-status", "missing_data", COLD);
  await expect(value).toContainText("not in the public domain");
  await expect(section.getByRole("button", { name: "Remove T10Y2Y" })).toBeVisible();
});
