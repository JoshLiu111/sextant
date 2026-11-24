import { expect, test } from "@playwright/test";
import { metric, openTool, steps, uniqueEmail, untilPanelIsLive } from "./how-to-use-helpers";

// The "How to use" panel at the top of tool pages (spec 02, issue #66): steps,
// one-click example links, and for visitors the things signing in adds on that tool.
// Open or collapsed is remembered per tool in the browser.

test.describe("on the first visit", () => {
  for (const [url, tool] of [
    ["/options", "Options Calculator"],
    ["/risk", "Risk & Performance"],
  ]) {
    test(`${tool} shows the panel open, with steps and an example link`, async ({ page }) => {
      const panel = await openTool(page, url);
      await expect(steps(panel)).toBeVisible();
      expect(await steps(panel).getByRole("listitem").count()).toBeGreaterThanOrEqual(3);
      await expect(panel.getByRole("link", { name: /^Try this:/ }).first()).toBeVisible();
    });
  }
});

test.describe("without JavaScript", () => {
  test.use({ javaScriptEnabled: false });

  test("the panel is open, so the steps are still readable", async ({ page }) => {
    const panel = await openTool(page, "/risk");
    await expect(steps(panel)).toBeVisible();
  });
});

test("a collapsed panel stays collapsed after a reload, and only on that tool", async ({ page }) => {
  const risk = await openTool(page, "/risk");
  await untilPanelIsLive(risk);
  await risk.getByText("How to use", { exact: true }).click();
  await expect(steps(risk)).toBeHidden();

  // It renders open until the page reads the remembered state.
  await page.reload();
  await untilPanelIsLive(risk);
  await expect(steps(risk)).toBeHidden();

  const options = await openTool(page, "/options");
  await expect(steps(options)).toBeVisible();

  // Opening it again is remembered too.
  const reopened = await openTool(page, "/risk");
  await untilPanelIsLive(reopened);
  await reopened.getByText("How to use", { exact: true }).click();
  await expect(steps(reopened)).toBeVisible();
  await page.reload();
  await expect(steps(reopened)).toBeVisible();
});

test("the panel toggles from the keyboard", async ({ page }) => {
  const panel = await openTool(page, "/risk");
  await untilPanelIsLive(panel);
  const toggle = panel.getByText("How to use", { exact: true });
  await toggle.focus();
  await page.keyboard.press("Enter");
  await expect(steps(panel)).toBeHidden();
  await page.keyboard.press("Space");
  await expect(steps(panel)).toBeVisible();
});

test.describe("example links fill in the inputs and show a result", () => {
  test("Options Calculator: a call at 30% volatility", async ({ page }) => {
    const panel = await openTool(page, "/options");
    await panel.getByRole("link", { name: "Try this: Price a call at 30% volatility" }).click();
    await expect(page).toHaveURL(/[?&]volatility=30(&|$)/);
    await expect(page.getByRole("main").getByLabel("Volatility")).toHaveValue("30");
    // S = K = 100, T = 1, sigma = 30%, r = 5% -> call 14.23.
    await expect(metric(page, "call_price")).toContainText("14.23");
  });

  test("Options Calculator: an iron condor", async ({ page }) => {
    const panel = await openTool(page, "/options");
    await panel.getByRole("link", { name: "Try this: Build an iron condor" }).click();
    const main = page.getByRole("main");
    await expect(main.getByRole("tab", { name: "Strategy builder" })).toHaveAttribute("aria-selected", "true");
    await expect(main.getByTestId("strategy-leg")).toHaveCount(4);
    // 80/90/110/120 around S = 100 -> a credit of 4.4155.
    await expect(metric(page, "net_cost")).toContainText("-4.4155");
  });

  test("Risk & Performance: a sharp crash", async ({ page }) => {
    const panel = await openTool(page, "/risk");
    await panel.getByRole("link", { name: "Try this: Measure a 45% crash" }).click();
    await expect(page.getByRole("main").getByLabel("Tickers")).toHaveValue("DEMO-D");
    // DEMO-D's injected crash: exactly 45% from 2022-02-28 to the 2022-04-11 bottom.
    await expect(metric(page, "max_drawdown:DEMO-D")).toContainText("45.00%");
  });

  test("Risk & Performance: two stocks at 99% confidence", async ({ page }) => {
    const panel = await openTool(page, "/risk");
    await panel.getByRole("link", { name: "Try this: Compare two stocks at 99% VaR" }).click();
    const main = page.getByRole("main");
    await expect(main.getByLabel("Tickers")).toHaveValue("DEMO-A,DEMO-B");
    await expect(main.getByLabel("VaR confidence level (%)")).toHaveValue("99");
    await expect(metric(page, "var:DEMO-B")).toHaveAttribute("data-status", "ok");
  });
});

test.describe("the signed-in extras line", () => {
  test("a visitor on Risk & Performance sees what signing in adds, with a sign-in link", async ({ page }) => {
    const panel = await openTool(page, "/risk");
    const extras = panel.getByTestId("signed-in-extras");
    await expect(extras).toContainText("Signed-in users can also");
    await expect(extras).toContainText("your own Tiingo or FMP key");
    await expect(extras.getByRole("link", { name: "Sign in with Google" })).toHaveAttribute(
      "href",
      "/auth/signin?returnTo=%2Frisk",
    );
  });

  test("a visitor on the Options Calculator sees that signing in adds AI Explain", async ({ page }) => {
    const panel = await openTool(page, "/options");
    const extras = panel.getByTestId("signed-in-extras");
    await expect(extras).toContainText("Signed-in users can also");
    await expect(extras).toContainText("get a plain-English AI explanation of the result");
    await expect(extras.getByRole("link", { name: "Sign in with Google" })).toHaveAttribute(
      "href",
      "/auth/signin?returnTo=%2Foptions",
    );
  });

  test("a signed-in user on Risk & Performance sees no such line", async ({ page }) => {
    await page.goto("/risk");
    await page.getByRole("banner").getByRole("link", { name: "Sign in with Google" }).click();
    await page.getByLabel("Email").fill(uniqueEmail("how-to"));
    await page.getByRole("button", { name: "Continue" }).click();
    await expect(page).toHaveURL(/\/risk$/);

    const panel = page.getByRole("main").getByRole("region", { name: "How to use" });
    await expect(steps(panel)).toBeVisible();
    // The same steps as visitors get; the AI Explain button shows the session is known.
    await expect(page.getByRole("main").getByRole("button", { name: "AI Explain" }).first()).toBeVisible();
    await expect(panel.getByText("Signed-in users can also")).toHaveCount(0);
  });
});
