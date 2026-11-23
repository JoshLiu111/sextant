import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";

// The earnings calendar and dividend history on /screener, served from the
// recorded EDGAR fixtures (submissions recorded 2026-11-22, companyfacts
// dividend tags) through e2e/fake-edgar.mjs. "Today" is pinned to 2026-11-22
// (SCREENER_TODAY in playwright.config.ts).

async function open(page: Page) {
  await page.goto("/screener");
  return page.getByRole("main");
}

type Main = Awaited<ReturnType<typeof open>>;
const calendar = (main: Main) => main.getByRole("table", { name: "Earnings calendar" });
const dividends = (main: Main) => main.getByRole("table", { name: "Dividend history" });

test("the earnings calendar lists recent releases with links to the 8-K and upcoming estimates", async ({ page }) => {
  const main = await open(page);

  await expect(main.getByTestId("earnings-range")).toHaveText("Earnings releases from 2026-10-23 to 2027-01-21", { timeout: 30_000 });
  const aapl = calendar(main).locator('[data-ticker="AAPL"]');
  await expect(aapl).toContainText("2026-11-02");
  await expect(aapl).toContainText("Apple Inc.");
  await expect(aapl).toHaveAttribute("data-status", "reported");
  await expect(aapl.getByRole("link", { name: "8-K filed 2026-11-02" })).toHaveAttribute(
    "href",
    "https://www.sec.gov/Archives/edgar/data/320193/000032019326000024/0000320193-26-000024-index.htm",
  );

  const jpm = calendar(main).locator('[data-ticker="JPM"]');
  await expect(jpm).toHaveAttribute("data-status", "expected");
  await expect(jpm).toContainText("2027-01-12");
  await expect(jpm).toContainText("Expected (estimate)");
  await expect(jpm.getByRole("link", { name: "Based on 8-K filed 2026-01-13" })).toBeVisible();
});

test("the calendar filters by date range and companies", async ({ page }) => {
  const main = await open(page);
  await expect(main.getByTestId("earnings-range")).toBeVisible({ timeout: 30_000 });

  await main.getByLabel("Companies").fill("AAPL, MSFT");
  await main.getByLabel("From", { exact: true }).fill("2026-01-01");
  await main.getByLabel("To", { exact: true }).fill("2026-06-30");
  await main.getByRole("button", { name: "Show calendar" }).click();

  await expect(main.getByTestId("earnings-range")).toHaveText("Earnings releases from 2026-01-01 to 2026-06-30");
  const rows = calendar(main).locator("tbody tr");
  await expect.poll(() => rows.evaluateAll((trs) => trs.map((tr) => tr.getAttribute("data-ticker")))).toEqual([
    "MSFT",
    "AAPL",
    "MSFT",
    "AAPL",
  ]);
  await expect(calendar(main).getByRole("link", { name: "8-K filed 2026-04-30" })).toBeVisible();
});

test("an inverted date range is shown on the field", async ({ page }) => {
  const main = await open(page);
  await expect(main.getByTestId("earnings-range")).toBeVisible({ timeout: 30_000 });

  await main.getByLabel("From", { exact: true }).fill("2026-06-01");
  await main.getByLabel("To", { exact: true }).fill("2026-01-01");
  await main.getByRole("button", { name: "Show calendar" }).click();

  await expect(main.getByText("The end date must be on or after the start date.")).toBeVisible();
});

test("dividend history shows declared dividends per share by fiscal quarter and year", async ({ page }) => {
  const main = await open(page);

  await expect(main.getByTestId("dividends-heading")).toHaveText("Apple Inc. (AAPL)", { timeout: 30_000 });
  const fy2026 = dividends(main).locator('[data-fiscal-year="2026"]');
  await expect(fy2026.locator('[data-period="Q1 FY2026"]')).toHaveText("0.26");
  await expect(fy2026.locator('[data-period="Q4 FY2026"]')).toHaveText("0.27*");
  await expect(fy2026.locator('[data-period="FY2026"]')).toHaveText("1.06");
  await expect(fy2026.locator('[data-period="FY2026"]')).toHaveAttribute("title", "FY2026 · Source: 10-K filed 2026-11-03");
  await expect(main.getByText("Fourth quarter derived")).toBeVisible();

  await main.getByLabel("Dividend ticker").fill("JPM");
  await main.getByRole("button", { name: "Show dividends" }).click();
  await expect(main.getByTestId("dividends-heading")).toHaveText("JPMORGAN CHASE & CO (JPM)");
  await expect(dividends(main).locator('[data-period="FY2025"]')).toHaveText("5.80");
});

test("a company that pays no dividend says so", async ({ page }) => {
  const main = await open(page);
  await expect(main.getByTestId("dividends-heading")).toBeVisible({ timeout: 30_000 });

  await main.getByLabel("Dividend ticker").fill("AMZN");
  await main.getByRole("button", { name: "Show dividends" }).click();

  await expect(main.getByTestId("dividends-note")).toHaveText(
    "AMAZON COM INC (AMZN) has reported no per-share dividends in its XBRL filings.",
  );
  await expect(dividends(main)).toHaveCount(0);
});

test("an unknown dividend ticker is shown on the field", async ({ page }) => {
  const main = await open(page);
  await expect(main.getByTestId("dividends-heading")).toBeVisible({ timeout: 30_000 });

  await main.getByLabel("Dividend ticker").fill("ZZZZ");
  await main.getByRole("button", { name: "Show dividends" }).click();

  await expect(main.getByText(/Unknown ticker ZZZZ/).first()).toBeVisible();
  await expect(main.getByLabel("Dividend ticker")).toHaveAttribute("aria-invalid", "true");
});

test("dividend history and the calendar export to CSV", async ({ page }) => {
  const main = await open(page);
  await expect(main.getByTestId("dividends-heading")).toHaveText("Apple Inc. (AAPL)", { timeout: 30_000 });

  const download = page.waitForEvent("download");
  await main.getByRole("button", { name: "Export CSV: Dividend history" }).click();
  const file = await download;
  expect(file.suggestedFilename()).toBe("sextant-screener-dividends-AAPL.csv");
  const text = readFileSync((await file.path())!, "utf8");
  expect(text).toContain("Period,Start,End,Dividend per share (USD),Derived,Form,Filed");
  expect(text).toContain("FY2026,2025-09-28,2026-09-26,1.06,,10-K,2026-11-03");
  expect(text).toContain("Q4 FY2026,2026-06-28,2026-09-26,0.27,yes,10-K,2026-11-03");

  await expect(main.getByTestId("earnings-range")).toBeVisible({ timeout: 30_000 });
  const calendarDownload = page.waitForEvent("download");
  await main.getByRole("button", { name: "Export CSV: Earnings calendar" }).click();
  expect((await calendarDownload).suggestedFilename()).toBe("sextant-screener-earnings-2026-10-23_2027-01-21.csv");
});
