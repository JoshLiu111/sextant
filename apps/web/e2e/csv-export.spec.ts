import { readFile } from "node:fs/promises";
import { expect, test, type Locator, type Page } from "@playwright/test";

// Every result table has an "Export CSV" button (story 9). These tests download
// the file and read it back. EDGAR comes from recorded fixtures (fake-edgar.mjs);
// Risk and Portfolio use the synthetic demo data.

/** Click an export button and return the download's file name and parsed rows. */
async function download(page: Page, button: Locator) {
  const [file] = await Promise.all([page.waitForEvent("download"), button.click()]);
  const text = await readFile((await file.path())!, "utf8");
  return { name: file.suggestedFilename(), rows: parseCsv(text.replace(/^\uFEFF/, "")) };
}

/** Minimal RFC 4180 reader: quoted fields, doubled quotes, CRLF rows. */
function parseCsv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = "";
  let quoted = false;
  const endField = () => {
    row.push(field);
    field = "";
  };
  const endRow = () => {
    endField();
    rows.push(row);
    row = [];
  };
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"' && text[i + 1] === '"') {
        field += '"';
        i++;
      } else if (ch === '"') quoted = false;
      else field += ch;
    } else if (ch === '"') quoted = true;
    else if (ch === ",") endField();
    else if (ch === "\n") endRow();
    else if (ch !== "\r") field += ch;
  }
  if (field !== "" || row.length) endRow();
  return rows;
}

const byFirstCell = (rows: string[][], first: string) => rows.find((r) => r[0] === first);

test("company statements export the underlying numbers, named after the ticker", async ({ page }) => {
  await page.goto("/company");
  const results = page.getByRole("main").getByTestId("results");
  const income = results.getByRole("region", { name: "Income statement" });
  await expect(income.locator('[data-metric-value="revenue:2026-09-26"]')).toHaveText("478,834", {
    timeout: 30_000,
  });

  const { name, rows } = await download(page, income.getByRole("button", { name: /Export CSV/ }));

  expect(name).toBe("sextant-company-income-statement-AAPL.csv");
  expect(rows[0][0]).toBe("Line item");
  expect(rows[0]).toContain("FY2026 (2026-09-26)");
  const col = rows[0].indexOf("FY2026 (2026-09-26)");
  // Raw USD, not the "478,834" millions shown on screen.
  expect(byFirstCell(rows, "Revenue")?.[col]).toBe("478834000000");
  expect(rows.some((r) => r.includes("Synthetic demo data"))).toBe(false);
});

test("a metric that is missing data exports as an empty cell", async ({ page }) => {
  await page.goto("/company?ticker=JPM");
  const results = page.getByRole("main").getByTestId("results");
  const income = results.getByRole("region", { name: "Income statement" });
  await expect(income.locator('[data-metric-value="cost_of_revenue:2025-12-31"]')).toHaveAttribute(
    "data-status",
    "missing_data",
    { timeout: 30_000 },
  );

  const { name, rows } = await download(page, income.getByRole("button", { name: /Export CSV/ }));

  expect(name).toBe("sextant-company-income-statement-JPM.csv");
  const col = rows[0].indexOf("FY2025 (2025-12-31)");
  expect(col).toBeGreaterThan(0);
  expect(byFirstCell(rows, "Cost of Revenue")?.[col]).toBe("");
  expect(byFirstCell(rows, "Revenue")?.[col]).toMatch(/^\d+$/);
});

test("demo data exports are marked as synthetic, with decimals instead of percent strings", async ({ page }) => {
  await page.goto("/risk");
  const main = page.getByRole("main");
  await expect(main.locator('[data-metric-value="max_drawdown:DEMO-D"]')).toHaveAttribute("data-status", "ok", {
    timeout: 30_000,
  });

  const { name, rows } = await download(page, main.getByRole("button", { name: /Export CSV/ }));

  expect(name).toBe("sextant-risk-metrics-DEMO-A_DEMO-B_DEMO-D.csv");
  expect(rows[0][0]).toBe("Data");
  expect(rows[0][1]).toBe("Ticker");
  expect(rows[0]).toContain("Max drawdown");
  for (const r of rows.slice(1)) expect(r[0]).toBe("Synthetic demo data");
  const demoD = rows.find((r) => r[1] === "DEMO-D")!;
  const mdd = Number(demoD[rows[0].indexOf("Max drawdown")]);
  // DEMO-D's injected crash: 49.1% over 2021–2025 (see ticket-3 notes), as a decimal.
  expect(mdd).toBeCloseTo(0.491, 3);
  expect(rows.map((r) => r[1])).toEqual(["Ticker", "DEMO-A", "DEMO-B", "DEMO-D", "DEMO-MKT"]);
});

test("screener results export raw values for the screen's year", async ({ page }) => {
  await page.goto("/screener");
  const results = page.getByRole("main").getByTestId("results");
  await expect(results.locator('[data-ticker="NVDA"] [data-metric-value="revenue"]')).toHaveText("215,938", {
    timeout: 30_000,
  });

  const { name, rows } = await download(page, results.getByRole("button", { name: /Export CSV/ }));

  expect(name).toBe("sextant-screener-results-2025.csv");
  expect(rows[0].slice(0, 2)).toEqual(["Ticker", "Company"]);
  const nvda = rows.find((r) => r[0] === "NVDA")!;
  expect(Math.round(Number(nvda[rows[0].indexOf("Revenue")]) / 1e6)).toBe(215_938);
  expect(Number(nvda[rows[0].indexOf("Revenue growth")])).toBeCloseTo(0.655, 3);
  expect(rows).toHaveLength(1 + 9);
});

test("every result table on each tool has an export button", async ({ page }) => {
  // [path, export buttons in main]
  const expected: [string, number][] = [
    ["/company", 3 + 9], // three statements; scores, Piotroski, five ratio categories, two DuPont tables
    ["/risk", 1],
    ["/portfolio", 1],
    ["/valuation", 2], // sensitivity, free cash flow
    // One table per tab: results, earnings calendar, dividend history, latest filings.
    ["/screener", 1],
    ["/screener?tab=earnings", 1],
    ["/screener?tab=dividends", 1],
    ["/screener?tab=filings", 1],
    ["/macro", 4 + 2], // four FRED indicators; yield curve, spread
  ];
  for (const [path, count] of expected) {
    await page.goto(path);
    await expect(page.getByRole("main").getByRole("button", { name: /Export CSV/ })).toHaveCount(count, {
      timeout: 30_000,
    });
  }
});

test("a saved portfolio exports its value, positions and returns, named after the portfolio", async ({ page }) => {
  await page.goto("/portfolio");
  await page.getByRole("banner").getByRole("link", { name: "Sign in with Google" }).click();
  await page.getByLabel("Email").fill(`csv-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.test`);
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page).toHaveURL(/\/portfolio$/);
  const saved = page.getByRole("main").getByRole("region", { name: "Your portfolios" });
  await saved.getByLabel("Portfolio name").fill("Brokerage");
  await saved.getByLabel("Ticker 1").fill("DEMO-C");
  await saved.getByLabel("Quantity 1").fill("2");
  await saved.getByLabel("Cost price 1").fill("50");
  await saved.getByRole("button", { name: "Save portfolio" }).click();
  await expect(saved.getByRole("status").first()).toContainText("Saved");
  // Saved: value, positions, returns, risk.
  const results = saved.getByTestId("saved-results");
  await expect(results.getByRole("button", { name: /Export CSV/ })).toHaveCount(4, { timeout: 30_000 });

  await expect(results.locator('[data-position-value="cost_basis:DEMO-C"]')).toHaveText("100.00");
  const positions = await download(page, results.getByRole("button", { name: "Export CSV: Positions" }));
  expect(positions.name).toBe("sextant-portfolio-positions-Brokerage.csv");
  // Demo tickers mark the file as synthetic; drop that leading column.
  expect(positions.rows[0][0]).toBe("Data");
  const p = positions.rows.map((row) => row.slice(1));
  expect(p[0]).toEqual([
    "Ticker",
    "Quantity",
    "Cost basis",
    "Market value",
    "Weight",
    "Unrealized P&L",
    "Realized P&L",
  ]);
  const demoC = byFirstCell(p, "DEMO-C")!;
  expect(demoC.slice(1, 3)).toEqual(["2", "100"]);
  expect(Number(demoC[4])).toBe(1); // weight as a decimal
  const total = byFirstCell(p, "Total")!;
  expect(total[1]).toBe("");
  expect(Number(total[2])).toBe(100);

  const returns = saved.getByRole("region", { name: "Your return" });
  await expect(returns.locator('[data-metric-value="irr:portfolio"]')).toHaveAttribute("data-status", "ok");
  const r = await download(page, returns.getByRole("button", { name: /Export CSV/ }));
  expect(r.name).toBe("sextant-portfolio-returns-Brokerage.csv");
  const ret = r.rows.map((row) => row.slice(1));
  expect(ret.map((row) => row[0])).toEqual([
    "Metric",
    "Time-weighted return",
    "Time-weighted return per year",
    "Money-weighted return (IRR)",
  ]);
  for (const row of ret.slice(1)) expect(row[1]).toMatch(/^-?\d/);
});
