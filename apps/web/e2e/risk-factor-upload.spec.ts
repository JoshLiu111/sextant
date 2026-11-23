import { readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, test, type Page } from "@playwright/test";

// Factor regressions on My data with a factor file the user uploaded (ADR 0003:
// Sextant ships no real factor data). Prices are the fake Tiingo's (e2e/fake-tiingo.mjs:
// AAPL, MSFT, SPY, 30 trading days from 2024-01-02), so the factor files here are
// daily, in the Kenneth R. French CSV layout, built so that Mkt-RF is SPY's own
// excess return: SPY must load 1.00 on the market factor.

type Row = { date: string; close: number; divCash: number };
const SPY: Row[] = JSON.parse(
  readFileSync(join(__dirname, "../../compute/tests/fixtures/tiingo/daily/spy.json"), "utf8"),
);
const RF = 0.02; // percent a day

function yyyymmdd(iso: string) {
  return iso.slice(0, 10).replaceAll("-", "");
}

/** Description lines, a `,col,...` header, YYYYMMDD rows in percent, a copyright footer. */
function kenFrenchCsv(columns: string[], rows: [string, number[]][]) {
  return [
    "This file was created by CMPT_ME_BEME_RETS_DAILY using the 202412 CRSP database.",
    "The Tbill return is the simple daily rate that, over the number of trading days",
    "",
    `,${columns.map((c) => c.padStart(8)).join(",")}`,
    ...rows.map(([date, values]) => `${date},${values.map((v) => v.toFixed(4).padStart(10)).join(",")}`),
    "",
    "Copyright 2024 Eugene F. Fama and Kenneth R. French",
    "",
  ].join("\r\n");
}

function threeFactorDaily(yearShift = 0) {
  const rows: [string, number[]][] = SPY.slice(1).map((day, i) => {
    const spyReturn = ((day.close + day.divCash) / SPY[i].close - 1) * 100;
    const date = String(Number(yyyymmdd(day.date)) - yearShift * 10000);
    return [date, [spyReturn - RF, 0.5 * Math.sin(1.7 * i), 0.4 * Math.cos(2.3 * i), RF]];
  });
  return kenFrenchCsv(["Mkt-RF", "SMB", "HML", "RF"], rows);
}

function momentumDaily() {
  const rows: [string, number[]][] = SPY.slice(1).map((day, i) => [yyyymmdd(day.date), [0.6 * Math.sin(0.9 * i + 1)]]);
  return kenFrenchCsv(["Mom"], rows);
}

const csvFile = (name: string, text: string) => ({ name, mimeType: "text/csv", buffer: Buffer.from(text) });

function uniqueEmail(label: string) {
  return `${label}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.test`;
}

async function signInWithKey(page: Page, email: string) {
  await page.goto("/settings");
  await page.getByRole("main").getByRole("link", { name: "Sign in with Google" }).click();
  await page.getByLabel("Email").fill(email);
  await page.getByRole("button", { name: "Continue" }).click();
  const section = page.getByRole("main").getByRole("region", { name: "Your Tiingo key" });
  await section.getByLabel("Tiingo API key").fill("good0000000000000000000000000000000abcd");
  await section.getByRole("button", { name: "Save key" }).click();
  await expect(section.getByRole("status")).toHaveText("Key saved.");
}

async function openRisk(page: Page) {
  await page.goto("/risk");
  const main = page.getByRole("main");
  await expect(main.locator('[data-metric-value="annualized_return:DEMO-A"]')).toHaveAttribute("data-status", "ok");
  return main;
}

async function openMyData(page: Page) {
  await signInWithKey(page, uniqueEmail("factors"));
  const main = await openRisk(page);
  await main.getByTestId("data-mode").getByText("My data").click();
  await expect(metric(page, "annualized_volatility:SPY")).toHaveAttribute("data-status", "ok");
  return main;
}

const metric = (page: Page, id: string) => page.getByRole("main").locator(`[data-metric-value="${id}"]`);
const panel = (page: Page) => page.getByRole("main").getByRole("region", { name: "Your factor files" });

test("the upload control is only offered in My data mode to a signed-in user", async ({ page }) => {
  let main = await openRisk(page);
  await expect(panel(page)).toHaveCount(0);
  await expect(main.getByTestId("factor-source")).toContainText("synthetic demo factors");

  await signInWithKey(page, uniqueEmail("factors-demo"));
  main = await openRisk(page);
  await expect(panel(page)).toHaveCount(0); // still on Demo data

  await main.getByTestId("data-mode").getByText("My data").click();
  await expect(panel(page).getByLabel("Upload a factor file")).toBeVisible();
  await expect(metric(page, "ff3_market:SPY")).toHaveAttribute("data-status", "missing_data");
  await expect(metric(page, "ff3_market:SPY")).toContainText("until you upload a factor file");

  await main.getByTestId("data-mode").getByText("Demo data").click();
  await expect(panel(page)).toHaveCount(0);
});

test("a user uploads Ken French daily files and gets FF3 and Carhart on their own prices", async ({ page }) => {
  await openMyData(page);
  const files = panel(page);
  const input = files.getByLabel("Upload a factor file");

  await input.setInputFiles(csvFile("prices.csv", "date,close\n2024-01-02,100\n"));
  await expect(files.getByRole("alert")).toContainText("Could not find a factor table");

  await input.setInputFiles(csvFile("F-F_Research_Data_Factors_daily.CSV", threeFactorDaily()));
  await expect(files.getByRole("status")).toContainText("F-F_Research_Data_Factors_daily.CSV");
  await expect(files.getByRole("alert")).toHaveCount(0);
  await expect(files.getByTestId("factor-file-three_factor")).toContainText("daily, 2024-01-03 to 2024-02-12");

  await expect(metric(page, "ff3_market:SPY")).toHaveAttribute("data-status", "ok");
  await expect(metric(page, "ff3_market:SPY")).toContainText("1.00");
  await expect(metric(page, "ff3_r_squared:AAPL")).toContainText("29 days");
  await expect(page.getByRole("main").getByTestId("factor-source")).toContainText("user-supplied");
  await expect(metric(page, "carhart_mom:AAPL")).toHaveAttribute("data-status", "missing_data");

  await input.setInputFiles(csvFile("F-F_Momentum_Factor_daily.CSV", momentumDaily()));
  await expect(files.getByTestId("factor-file-momentum")).toContainText("F-F_Momentum_Factor_daily.CSV");
  await expect(metric(page, "carhart_mom:AAPL")).toHaveAttribute("data-status", "ok");

  await files.getByRole("button", { name: "Remove 3-factor file" }).click();
  await expect(files.getByTestId("factor-file-three_factor")).toHaveCount(0);
  await expect(metric(page, "ff3_market:SPY")).toHaveAttribute("data-status", "missing_data");
});

test("a factor file that does not overlap the price range says so", async ({ page }) => {
  await openMyData(page);

  await panel(page).getByLabel("Upload a factor file").setInputFiles(csvFile("old.csv", threeFactorDaily(30)));

  await expect(metric(page, "ff3_market:SPY")).toHaveAttribute("data-status", "missing_data");
  await expect(metric(page, "ff3_market:SPY")).toContainText(
    "Your factor file covers 1994-01-03 to 1994-02-12, which does not overlap the price range",
  );
});
