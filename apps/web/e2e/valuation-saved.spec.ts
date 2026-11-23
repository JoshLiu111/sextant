import { expect, test, type Page } from "@playwright/test";

// Valuation Calculator: margin of safety against a share price (typed in, or the
// latest close from the user's own Tiingo key on My data), and saved assumption sets.
// EDGAR is e2e/fake-edgar.mjs (MSFT FY2026, defaults give $163.73 per share);
// Tiingo is e2e/fake-tiingo.mjs (keys starting with "good"; MSFT's latest close is
// $402.00 on 2024-02-12).

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

async function openValuation(page: Page) {
  await page.goto("/valuation");
  const main = page.getByRole("main");
  // Wait for the first result so the page is hydrated and the key list has loaded.
  await expect(value(main, "intrinsic_value_per_share")).toContainText("$163.73");
  return main;
}

type Main = ReturnType<Page["getByRole"]>;
const value = (main: Main, id: string) => main.locator(`[data-metric-value="${id}"]`);

test("without a price the market comparison asks for one; a typed-in price gives the margin of safety", async ({
  page,
}) => {
  const main = await openValuation(page);
  const market = main.getByTestId("market-comparison");
  for (const id of ["share_price", "market_cap", "margin_of_safety"]) {
    await expect(value(market, id)).toHaveAttribute("data-status", "missing_data");
    await expect(value(market, id)).toContainText("Enter a share price");
  }

  // A fixed discount rate keeps the intrinsic value independent of the price (no WACC weights).
  await main.getByLabel("Discount rate (%)").fill("9");
  await expect(value(main, "intrinsic_value_per_share")).toContainText("$169.08");
  await main.getByLabel("Share price ($)").fill("100");

  await expect(value(market, "share_price")).toContainText("$100.00");
  await expect(value(market, "share_price")).toContainText("Your price");
  // 7,427M shares x $100; margin of safety (169.08 - 100) / 169.08.
  await expect(value(market, "market_cap")).toContainText("$742.70B");
  await expect(value(market, "margin_of_safety")).toContainText("40.86%");
});

test("visitors see a sign-in prompt instead of the save control", async ({ page }) => {
  const main = await openValuation(page);
  const saved = main.getByTestId("saved-assumptions");

  await expect(saved.getByText("Sign in to save your assumptions")).toBeVisible();
  await expect(saved.getByRole("link", { name: "Sign in with Google" })).toBeVisible();
  await expect(saved.getByRole("button", { name: "Save assumptions" })).toHaveCount(0);
});

test("on My data the latest close from Tiingo fills the price", async ({ page }) => {
  await signIn(page, uniqueEmail("val-mydata"), { withKey: true });
  const main = await openValuation(page);
  const toggle = main.getByTestId("data-mode");

  await toggle.getByText("My data").click();

  const market = main.getByTestId("market-comparison");
  await expect(value(market, "share_price")).toContainText("$402.00");
  await expect(value(market, "share_price")).toContainText("Latest close from Tiingo, 2024-02-12");
  await expect(value(market, "margin_of_safety")).toHaveAttribute("data-status", "ok");
  await expect(main.getByText("Optional. Leave blank to use the latest close from Tiingo.")).toBeVisible();
});

test("a signed-in user saves, loads and deletes a named set of assumptions", async ({ page }) => {
  await signIn(page, uniqueEmail("val-saved"), { withKey: false });
  const main = await openValuation(page);
  const saved = main.getByTestId("saved-assumptions");
  await expect(saved.getByText("No saved assumptions for MSFT yet.")).toBeVisible();

  await main.getByLabel("Growth rate (%)").fill("8");
  await main.getByLabel("Cost of debt (%)").fill("4.5");
  await expect(value(main, "intrinsic_value_per_share")).toContainText("$190.93");
  await saved.getByLabel("Name").fill("Bullish");
  await saved.getByRole("button", { name: "Save assumptions" }).click();
  await expect(saved.getByRole("status")).toHaveText("Saved as Bullish.");
  await expect(saved.getByRole("list", { name: "Saved assumptions for MSFT" }).getByText("Bullish")).toBeVisible();

  // Back to the defaults, then load the set: every input comes back and the result recomputes.
  await page.reload();
  await expect(value(main, "intrinsic_value_per_share")).toContainText("$163.73");
  await saved.getByRole("button", { name: "Load Bullish" }).click();
  await expect(main.getByLabel("Growth rate (%)")).toHaveValue("8");
  await expect(main.getByLabel("Cost of debt (%)")).toHaveValue("4.5");
  await expect(main.getByLabel("Terminal growth (%)")).toHaveValue("2.5");
  await expect(main.getByLabel("Share price ($)")).toHaveValue("");
  await expect(value(main, "intrinsic_value_per_share")).toContainText("$190.93");

  await saved.getByRole("button", { name: "Delete Bullish" }).click();
  await expect(saved.getByRole("status")).toHaveText("Deleted Bullish.");
  await expect(saved.getByText("No saved assumptions for MSFT yet.")).toBeVisible();
});
