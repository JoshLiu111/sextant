import { expect, test } from "@playwright/test";
import { COLD, metric, openTool, steps, uniqueEmail } from "./how-to-use-helpers";

// "How to use" content for My Portfolio, Company Health Check and the Valuation
// Calculator (spec 02, issue #67): steps, example links that fill in the inputs
// and show a result, and for visitors what signing in adds on that tool.

test.describe("My Portfolio", () => {
  test("shows the panel with steps and example links", async ({ page }) => {
    const panel = await openTool(page, "/portfolio");
    expect(await steps(panel).getByRole("listitem").count()).toBeGreaterThanOrEqual(3);
    await expect(panel.getByRole("link", { name: /^Try this:/ }).first()).toBeVisible();
  });

  test("example: a 60/40 portfolio", async ({ page }) => {
    const panel = await openTool(page, "/portfolio");
    await panel.getByRole("link", { name: "Try this: Load a 60/40 portfolio" }).click();
    const demo = page.getByRole("main").getByRole("region", { name: "Demo portfolio" });
    await expect(demo.getByLabel("Ticker 1")).toHaveValue("DEMO-C");
    await expect(demo.getByLabel("Weight 1 (%)")).toHaveValue("60");
    await expect(demo.getByLabel("Ticker 2")).toHaveValue("DEMO-E");
    await expect(demo.getByLabel("Ticker 3")).toHaveCount(0);
    await expect(metric(page, "max_drawdown:portfolio")).toHaveAttribute("data-status", "ok");
  });

  test("example: a portfolio through a 45% crash", async ({ page }) => {
    const panel = await openTool(page, "/portfolio");
    await panel.getByRole("link", { name: "Try this: Hold one stock through a 45% crash" }).click();
    const demo = page.getByRole("main").getByRole("region", { name: "Demo portfolio" });
    await expect(demo.getByLabel("Ticker 1")).toHaveValue("DEMO-D");
    await expect(demo.getByLabel("Weight 1 (%)")).toHaveValue("100");
    // DEMO-D's injected crash: exactly 45% from 2022-02-28 to the 2022-04-11 bottom.
    await expect(metric(page, "max_drawdown:portfolio")).toContainText("45.00%");
  });

  test("a visitor sees what signing in adds", async ({ page }) => {
    const panel = await openTool(page, "/portfolio");
    const extras = panel.getByTestId("signed-in-extras");
    await expect(extras).toContainText("Signed-in users can also");
    await expect(extras).toContainText("your own Tiingo or FMP key");
    await expect(extras).toContainText("save portfolios");
    await expect(extras).toContainText("import your trades from a CSV file");
    await expect(extras).toContainText("AI explanation");
    await expect(extras.getByRole("link", { name: "Sign in with Google" })).toHaveAttribute(
      "href",
      "/auth/signin?returnTo=%2Fportfolio",
    );
  });
});

test.describe("Company Health Check", () => {
  test("shows the panel with steps and example links", async ({ page }) => {
    const panel = await openTool(page, "/company");
    expect(await steps(panel).getByRole("listitem").count()).toBeGreaterThanOrEqual(3);
    await expect(panel.getByRole("link", { name: /^Try this:/ }).first()).toBeVisible();
  });

  test("example: Apple's P/E at a $250 share price", async ({ page }) => {
    const panel = await openTool(page, "/company");
    await panel.getByRole("link", { name: "Try this: Check Apple's P/E at a $250 share price" }).click();
    const ratios = page.getByRole("main").getByTestId("ratios");
    await expect(ratios.getByLabel("Compare company 1", { exact: true })).toHaveValue("AAPL");
    await expect(ratios.getByLabel("Share price 1", { exact: true })).toHaveValue("250");
    await expect(metric(page, "price_to_earnings:AAPL:2026-09-26")).toHaveText("27.84", COLD);
  });

  test("example: Microsoft next to Apple", async ({ page }) => {
    const panel = await openTool(page, "/company");
    await panel.getByRole("link", { name: "Try this: Compare Microsoft with Apple" }).click();
    const main = page.getByRole("main");
    const ratios = main.getByTestId("ratios");
    await expect(ratios.getByLabel("Compare company 1", { exact: true })).toHaveValue("MSFT");
    await expect(ratios.getByLabel("Compare company 2", { exact: true })).toHaveValue("AAPL");
    await expect(metric(page, "current_ratio:AAPL:2026-09-26")).toHaveText("1.02", COLD);
    await expect(ratios.locator('[data-metric-value^="current_ratio:MSFT:"][data-status="ok"]').first()).toBeVisible();
    // The statements below follow the same link.
    await expect(main.getByLabel("Ticker")).toHaveValue("MSFT");
    await expect(main.getByTestId("results").getByRole("heading", { name: /MICROSOFT/i })).toBeVisible(COLD);
  });

  test("a visitor sees what signing in adds", async ({ page }) => {
    const panel = await openTool(page, "/company");
    const extras = panel.getByTestId("signed-in-extras");
    await expect(extras).toContainText("Signed-in users can also");
    await expect(extras).toContainText("AI explanation");
    await expect(extras.getByRole("link", { name: "Sign in with Google" })).toHaveAttribute(
      "href",
      "/auth/signin?returnTo=%2Fcompany",
    );
  });
});

test.describe("Valuation Calculator", () => {
  test("shows the panel with steps and example links", async ({ page }) => {
    const panel = await openTool(page, "/valuation");
    expect(await steps(panel).getByRole("listitem").count()).toBeGreaterThanOrEqual(3);
    await expect(panel.getByRole("link", { name: /^Try this:/ }).first()).toBeVisible();
  });

  test("example: Microsoft at 8% growth", async ({ page }) => {
    const panel = await openTool(page, "/valuation");
    await panel.getByRole("link", { name: "Try this: Value Microsoft at 8% growth" }).click();
    const main = page.getByRole("main");
    await expect(main.getByLabel("Ticker")).toHaveValue("MSFT");
    await expect(main.getByLabel("Growth rate (%)")).toHaveValue("8");
    // MSFT with 8% growth, other assumptions default: $185.06 per share.
    await expect(metric(page, "intrinsic_value_per_share")).toContainText("$185.06", COLD);
  });

  test("example: Microsoft with a 12% cost of equity", async ({ page }) => {
    const panel = await openTool(page, "/valuation");
    await panel.getByRole("link", { name: "Try this: Override the cost of equity at 12%" }).click();
    const main = page.getByRole("main");
    await expect(main.getByLabel("Cost of equity (%)")).toHaveValue("12");
    await expect(metric(page, "cost_of_equity")).toContainText("12.00%", COLD);
    await expect(metric(page, "cost_of_equity")).toContainText("Your override");
    await expect(metric(page, "intrinsic_value_per_share")).toHaveAttribute("data-status", "ok");
  });

  test("a visitor sees what signing in adds", async ({ page }) => {
    const panel = await openTool(page, "/valuation");
    const extras = panel.getByTestId("signed-in-extras");
    await expect(extras).toContainText("Signed-in users can also");
    await expect(extras).toContainText("your own Tiingo or FMP key");
    await expect(extras).toContainText("save your assumptions");
    await expect(extras).toContainText("AI explanation");
    await expect(extras.getByRole("link", { name: "Sign in with Google" })).toHaveAttribute(
      "href",
      "/auth/signin?returnTo=%2Fvaluation",
    );
  });

  test("a signed-in user sees the same steps but no such line", async ({ page }) => {
    await page.goto("/valuation");
    await page.getByRole("banner").getByRole("link", { name: "Sign in with Google" }).click();
    await page.getByLabel("Email").fill(uniqueEmail("how-to-67"));
    await page.getByRole("button", { name: "Continue" }).click();
    await expect(page).toHaveURL(/\/valuation$/);

    const panel = page.getByRole("main").getByRole("region", { name: "How to use" });
    await expect(steps(panel)).toBeVisible();
    // The AI Explain button shows the session is known.
    await expect(page.getByRole("main").getByRole("button", { name: "AI Explain" }).first()).toBeVisible(COLD);
    await expect(panel.getByText("Signed-in users can also")).toHaveCount(0);
  });
});
