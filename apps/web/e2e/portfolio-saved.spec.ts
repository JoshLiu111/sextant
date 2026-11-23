import { expect, test, type Locator, type Page } from "@playwright/test";

// Saved portfolios for signed-in users. Sign-in uses the fake OIDC provider
// (e2e/fake-oidc.mjs); each test signs in with its own email.

function uniqueEmail(label: string) {
  return `${label}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.test`;
}

async function signInOnPortfolio(page: Page, email: string) {
  await page.goto("/portfolio");
  await page.getByRole("banner").getByRole("link", { name: "Sign in with Google" }).click();
  await page.getByLabel("Email").fill(email);
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page).toHaveURL(/\/portfolio$/);
  const saved = page.getByRole("main").getByRole("region", { name: "Your portfolios" });
  await expect(saved.getByLabel("Portfolio name")).toBeVisible();
  return saved;
}

type Holding = { ticker: string; quantity: string; cost: string; currency?: string };

async function fillHoldings(saved: Locator, holdings: Holding[]) {
  for (const [i, h] of holdings.entries()) {
    const n = i + 1;
    if ((await saved.getByLabel(`Ticker ${n}`).count()) === 0) {
      await saved.getByRole("button", { name: "Add holding" }).click();
    }
    await saved.getByLabel(`Ticker ${n}`).fill(h.ticker);
    await saved.getByLabel(`Quantity ${n}`).fill(h.quantity);
    await saved.getByLabel(`Cost price ${n}`).fill(h.cost);
    if (h.currency) await saved.getByLabel(`Currency ${n}`).fill(h.currency);
  }
}

async function createPortfolio(saved: Locator, name: string, holdings: Holding[]) {
  await saved.getByRole("button", { name: "New portfolio" }).click();
  await saved.getByLabel("Portfolio name").fill(name);
  await fillHoldings(saved, holdings);
  await saved.getByRole("button", { name: "Save portfolio" }).click();
  await expect(saved.getByRole("status")).toContainText("Saved");
  await expect(saved.getByLabel("Saved portfolio")).toHaveValue(/.+/);
}

const metric = (scope: Locator, id: string) => scope.locator(`[data-metric-value="${id}"]`);

test("anonymous visitors see a prompt to sign in to save, and the demo still works", async ({ page }) => {
  await page.goto("/portfolio");
  const main = page.getByRole("main");

  const prompt = main.getByTestId("save-prompt");
  await expect(prompt).toContainText("Sign in to save");
  await expect(prompt.getByRole("link", { name: "Sign in with Google" })).toHaveAttribute(
    "href",
    "/auth/signin?returnTo=%2Fportfolio",
  );
  await expect(main.getByRole("region", { name: "Your portfolios" })).toHaveCount(0);
  await expect(metric(main, "annualized_volatility:portfolio")).toHaveAttribute("data-status", "ok");
});

test("a signed-in user creates, switches between, renames, edits and deletes portfolios", async ({ page }) => {
  const saved = await signInOnPortfolio(page, uniqueEmail("crud"));
  await expect(saved.getByText("You have no saved portfolios yet.")).toBeVisible();

  await createPortfolio(saved, "Steady", [
    { ticker: "DEMO-A", quantity: "10", cost: "100" },
    { ticker: "DEMO-E", quantity: "20", cost: "50" },
  ]);
  await expect(metric(saved, "market_value:portfolio")).toHaveAttribute("data-status", "ok");
  await expect(metric(saved, "cost_basis:portfolio")).toContainText("2,000.00");
  for (const id of ["annualized_volatility", "max_drawdown", "var", "sharpe", "beta"]) {
    await expect(metric(saved, `${id}:portfolio`)).toHaveAttribute("data-status", "ok");
  }
  await expect(saved.getByRole("img", { name: /cumulative return/i })).toBeVisible();
  await expect(saved.getByTestId("demo-badge")).toBeVisible();
  const steadyVol = await metric(saved, "annualized_volatility:portfolio").textContent();

  await createPortfolio(saved, "Speculative", [{ ticker: "DEMO-F", quantity: "5", cost: "30" }]);
  const switcher = saved.getByLabel("Saved portfolio");
  await expect(switcher.locator("option")).toHaveText(["Steady", "Speculative"]);
  await expect(metric(saved, "annualized_volatility:portfolio")).toHaveAttribute("data-status", "ok");
  await expect(metric(saved, "annualized_volatility:portfolio")).not.toHaveText(steadyVol ?? "");

  // Switch back: the editor and results follow the selection.
  await switcher.selectOption({ label: "Steady" });
  await expect(saved.getByLabel("Portfolio name")).toHaveValue("Steady");
  await expect(saved.getByLabel("Ticker 2")).toHaveValue("DEMO-E");
  await expect(metric(saved, "annualized_volatility:portfolio")).toHaveText(steadyVol ?? "");

  // Rename and edit a holding.
  await saved.getByLabel("Portfolio name").fill("Steady income");
  await saved.getByLabel("Quantity 1").fill("30");
  await saved.getByRole("button", { name: "Save portfolio" }).click();
  await expect(saved.getByRole("status")).toContainText("Saved");
  await expect(switcher.locator("option")).toHaveText(["Steady income", "Speculative"]);
  await expect(metric(saved, "cost_basis:portfolio")).toContainText("4,000.00");

  // Invalid input is shown on its field and nothing is saved.
  await saved.getByLabel("Quantity 2").fill("0");
  await saved.getByRole("button", { name: "Save portfolio" }).click();
  await expect(saved.getByTestId("field-error-holdings.1.quantity")).toContainText("greater than 0");
  await page.reload();
  await expect(saved.getByLabel("Quantity 2")).toHaveValue("20");

  // Delete asks for confirmation first.
  await saved.getByRole("button", { name: "Delete portfolio" }).click();
  await saved.getByRole("button", { name: "Cancel" }).click();
  await expect(switcher.locator("option")).toHaveCount(2);
  await saved.getByRole("button", { name: "Delete portfolio" }).click();
  await saved.getByRole("button", { name: "Yes, delete this portfolio" }).click();
  await expect(switcher.locator("option")).toHaveText(["Speculative"]);
  await expect(saved.getByLabel("Portfolio name")).toHaveValue("Speculative");
});

test("saved portfolios persist across sessions and devices", async ({ page, browser }) => {
  const email = uniqueEmail("persist");
  const saved = await signInOnPortfolio(page, email);
  await createPortfolio(saved, "Long term", [{ ticker: "DEMO-C", quantity: "3", cost: "120" }]);

  // A second device: a fresh browser context with no cookies, signing in as the same person.
  const other = await browser.newContext();
  try {
    const otherSaved = await signInOnPortfolio(await other.newPage(), email);
    await expect(otherSaved.getByLabel("Saved portfolio").locator("option")).toHaveText(["Long term"]);
    await expect(otherSaved.getByLabel("Ticker 1")).toHaveValue("DEMO-C");
  } finally {
    await other.close();
  }

  // Signing out and back in on the first device keeps it too.
  await page.getByRole("banner").getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("banner").getByRole("link", { name: "Sign in with Google" })).toBeVisible();
  await page.goto("/portfolio");
  await expect(page.getByRole("main").getByTestId("save-prompt")).toBeVisible();
  const again = await signInOnPortfolio(page, email);
  await expect(again.getByLabel("Saved portfolio").locator("option")).toHaveText(["Long term"]);
});

test("saved portfolios are never encoded in the URL; only demo-mode inputs are", async ({ page }) => {
  const saved = await signInOnPortfolio(page, uniqueEmail("url"));
  await createPortfolio(saved, "Private", [{ ticker: "DEMO-F", quantity: "5", cost: "30" }]);
  await expect(metric(saved, "market_value:portfolio")).toHaveAttribute("data-status", "ok");
  await expect(page).toHaveURL(/\/portfolio$/);

  const demo = page.getByRole("main").getByRole("region", { name: "Demo portfolio" });
  await demo.getByRole("button", { name: "Calculate" }).click();
  await expect(page).toHaveURL(/[?&]holdings=DEMO-A:40,DEMO-B:30,DEMO-E:30(&|$)/);
  expect(page.url()).not.toContain("DEMO-F");
  expect(page.url()).not.toContain("Private");
});
