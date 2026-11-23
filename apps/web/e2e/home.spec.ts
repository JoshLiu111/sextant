import { expect, test } from "@playwright/test";

const TOOLS = [
  "Options Calculator",
  "Risk & Performance",
  "My Portfolio",
  "Company Health Check",
  "Valuation Calculator",
  "Macro Dashboard",
  "Screener & Calendar",
  "AI Analyst",
];

// Tools that are built; every other tool page still says "Coming soon".
const LIVE_TOOLS = new Set(["Options Calculator", "Risk & Performance", "Company Health Check", "Macro Dashboard"]);

test("home page lists all eight tools with a description", async ({ page }) => {
  await page.goto("/");

  const cards = page.getByTestId("tool-card");
  await expect(cards).toHaveCount(TOOLS.length);
  for (const name of TOOLS) {
    const card = cards.filter({ has: page.getByRole("heading", { name, exact: true }) });
    await expect(card).toHaveCount(1);
    await expect(card.getByTestId("tool-description")).not.toBeEmpty();
  }
});

test("footer shows the investment disclaimer and an attribution slot", async ({ page }) => {
  await page.goto("/");

  const footer = page.getByRole("contentinfo");
  await expect(footer).toContainText("Not investment advice");
  await expect(footer.getByTestId("attribution-slot")).toBeAttached();
});

test("home page shows the compute service is online", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByTestId("compute-status")).toHaveText(/Compute service: online/);
});

test("nav reaches every tool from any page, and unbuilt tools say coming soon", async ({ page }) => {
  await page.goto("/");
  const nav = page.getByRole("navigation", { name: "Tools" });

  for (const name of TOOLS) {
    await nav.getByRole("link", { name, exact: true }).click();
    await expect(page.getByRole("heading", { level: 1, name })).toBeVisible();
    const comingSoon = page.getByRole("main").getByText("Coming soon", { exact: true });
    if (LIVE_TOOLS.has(name)) await expect(comingSoon).toHaveCount(0);
    else await expect(comingSoon).toBeVisible();
    await expect(page.getByRole("contentinfo")).toContainText("Not investment advice");
  }
});

test.describe("mobile width", () => {
  test.use({ viewport: { width: 375, height: 740 } });

  test("home page has no horizontal scroll and the nav still reaches tools", async ({ page }) => {
    await page.goto("/");

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(0);

    await page.getByRole("button", { name: "Menu" }).click();
    await page
      .getByRole("navigation", { name: "Tools" })
      .getByRole("link", { name: "Macro Dashboard", exact: true })
      .click();
    await expect(page.getByRole("heading", { level: 1, name: "Macro Dashboard" })).toBeVisible();
  });
});
