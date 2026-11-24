import { expect, test, type Page } from "@playwright/test";
import { COLD, openTool, steps, uniqueEmail } from "./how-to-use-helpers";

// The "How to use" panel's content on Macro Dashboard, Screener & Calendar and
// AI Analyst (issue #68; the panel itself is covered in how-to-use.spec.ts).
// Values come from the recorded fixtures behind the fakes (see macro-search,
// macro-world, shareable-links and ai-analyst specs).

async function signIn(page: Page, url: string) {
  await page.goto(url);
  await page.getByRole("banner").getByRole("link", { name: "Sign in with Google" }).click();
  await page.getByLabel("Email").fill(uniqueEmail("how-to-68"));
  await page.getByRole("button", { name: "Continue" }).click();
}

const TOOLS = [
  { url: "/macro", name: "Macro Dashboard", extra: "AI explanation" },
  { url: "/screener", name: "Screener & Calendar", extra: "your own Tiingo or FMP key" },
  { url: "/ai-analyst", name: "AI Analyst", extra: "ask questions in plain English" },
] as const;

for (const tool of TOOLS) {
  test.describe(tool.name, () => {
    test("shows the panel open, with steps and an example link", async ({ page }) => {
      const panel = await openTool(page, tool.url);
      await expect(steps(panel)).toBeVisible();
      const count = await steps(panel).getByRole("listitem").count();
      expect(count).toBeGreaterThanOrEqual(3);
      expect(count).toBeLessThanOrEqual(5);
      await expect(panel.getByRole("link", { name: /^Try this:/ }).first()).toBeVisible();
    });

    test("a visitor sees what signing in adds here, with a sign-in link back to this tool", async ({ page }) => {
      const panel = await openTool(page, tool.url);
      const extras = panel.getByTestId("signed-in-extras");
      await expect(extras).toContainText("Signed-in users can also");
      await expect(extras).toContainText(tool.extra);
      await expect(extras.getByRole("link", { name: "Sign in with Google" })).toHaveAttribute(
        "href",
        `/auth/signin?returnTo=${encodeURIComponent(tool.url)}`,
      );
    });

    test("a signed-in user sees no such line", async ({ page }) => {
      await signIn(page, tool.url);
      await expect(page).toHaveURL(new RegExp(`${tool.url}$`));
      // Reload so the panel's session check is one we can wait for: a signed-in quota answers 200.
      const quota = page.waitForResponse((r) => r.url().includes("/ai/quota") && r.status() === 200);
      await page.reload();
      await quota;
      const panel = page.getByRole("main").getByRole("region", { name: "How to use" });
      await expect(steps(panel)).toBeVisible();
      await expect(panel.getByText("Signed-in users can also")).toHaveCount(0);
    });
  });
}

test.describe("example links fill in the inputs and show a result", () => {
  test("Macro Dashboard: payrolls since 2020", async ({ page }) => {
    const panel = await openTool(page, "/macro");
    await panel.getByRole("link", { name: "Try this: Track US payrolls since 2020" }).click();
    const main = page.getByRole("main");
    await expect(main.getByLabel("History from")).toHaveValue("2020-01-01");
    await expect(main.locator('[data-metric-value="latest:PAYEMS"]')).toContainText("157,995", COLD);
  });

  test("Macro Dashboard: the US, China and India side by side", async ({ page }) => {
    const panel = await openTool(page, "/macro");
    await panel.getByRole("link", { name: "Try this: Compare the US, China and India" }).click();
    const section = page.getByRole("main").getByTestId("countries");
    await expect(section.locator('[data-metric-value="latest:gdp_growth:CHN"]')).toContainText("4.96%", COLD);
    await expect(section.locator('[data-metric-value="latest:gdp_growth:IND"]')).toContainText("7.57%");
    await expect(section.locator('[data-metric-value="latest:gdp_growth:DEU"]')).toHaveCount(0);
  });

  test("Screener & Calendar: low-debt growth companies", async ({ page }) => {
    const panel = await openTool(page, "/screener");
    await panel.getByRole("link", { name: "Try this: Find growing companies with little debt" }).click();
    const main = page.getByRole("main");
    const criteria = main.getByRole("group", { name: "Criteria" });
    await expect(criteria.getByLabel("Metric for criterion 2")).toHaveValue("debt_ratio");
    await expect(criteria.getByLabel("Value for criterion 2")).toHaveValue("30");
    await expect(main.getByTestId("screen-summary")).toBeVisible(COLD);
    await expect
      .poll(() =>
        main
          .getByRole("table", { name: "Screen results" })
          .locator("[data-ticker]")
          .evaluateAll((rows) => rows.map((r) => r.getAttribute("data-ticker"))),
      )
      .toEqual(["AMD", "NVDA"]);
  });

  test("Screener & Calendar: JPMorgan's dividends", async ({ page }) => {
    const panel = await openTool(page, "/screener");
    await panel.getByRole("link", { name: "Try this: See JPMorgan's dividend history" }).click();
    const main = page.getByRole("main");
    await expect(main.getByLabel("Dividend ticker")).toHaveValue("JPM");
    await expect(main.getByTestId("dividends-heading")).toHaveText("JPMORGAN CHASE & CO (JPM)", COLD);
    await expect(main.locator('[data-period="FY2025"]')).toHaveText("5.80");
  });

  test("AI Analyst: a signed-in user gets the question filled in, and asking it answers", async ({ page }) => {
    await signIn(page, "/ai-analyst");
    await expect(page).toHaveURL(/\/ai-analyst$/);
    const panel = page.getByRole("main").getByRole("region", { name: "How to use" });
    await panel.getByRole("link", { name: "Try this: Ask what an at-the-money call is worth" }).click();
    const main = page.getByRole("main");
    const question = main.getByRole("textbox", { name: "Your question" });
    await expect(question).toHaveValue("What is an at-the-money one-year call worth?");
    // Asking spends one of the day's AI calls, so it stays a deliberate click.
    await expect(main.getByRole("region", { name: "Answer" })).toHaveCount(0);
    await main.getByRole("button", { name: "Ask" }).click();
    await expect(main.getByRole("region", { name: "Answer" }).getByTestId("analyst-answer")).toContainText(
      "worth 10.45 per share",
    );
  });

  test("AI Analyst: a visitor who follows an example signs in and comes back to the same question", async ({ page }) => {
    const panel = await openTool(page, "/ai-analyst");
    await panel.getByRole("link", { name: "Try this: Ask what an at-the-money call is worth" }).click();
    const main = page.getByRole("main");
    await expect(main).toContainText("Sign in to use AI Analyst");
    await main.getByTestId("analyst-sign-in").getByRole("link", { name: "Sign in with Google" }).click();
    await page.getByLabel("Email").fill(uniqueEmail("how-to-68-analyst"));
    await page.getByRole("button", { name: "Continue" }).click();
    await expect(page.getByRole("main").getByRole("textbox", { name: "Your question" })).toHaveValue(
      "What is an at-the-money one-year call worth?",
    );
  });
});
