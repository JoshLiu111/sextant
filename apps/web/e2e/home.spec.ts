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

// Where each card's "Open demo" link should land.
const TOOL_PATHS: Record<string, string> = {
  "Options Calculator": "/options",
  "Risk & Performance": "/risk",
  "My Portfolio": "/portfolio",
  "Company Health Check": "/company",
  "Valuation Calculator": "/valuation",
  "Macro Dashboard": "/macro",
  "Screener & Calendar": "/screener",
  "AI Analyst": "/ai-analyst",
};

// Tools that are built; every other tool page still says "Coming soon".
const LIVE_TOOLS = new Set([
  "Options Calculator",
  "Risk & Performance",
  "My Portfolio",
  "Company Health Check",
  "Valuation Calculator",
  "Macro Dashboard",
  "Screener & Calendar",
  "AI Analyst",
]);

test("the hero says what Sextant is, and Try a tool jumps to the tool cards", async ({ page }) => {
  await page.goto("/");

  const hero = page.getByRole("region", { name: "Free, transparent finance tools" });
  await expect(hero.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(hero.getByTestId("value-proposition")).not.toBeEmpty();

  await hero.getByRole("link", { name: "Try a tool" }).click();
  await expect(page).toHaveURL(/#tools$/);
  await expect(page.getByRole("heading", { level: 2, name: "Pick a question" })).toBeInViewport();
});

test("the hero's Sign in with Google starts Google sign-in", async ({ page }) => {
  await page.goto("/");

  const hero = page.getByRole("region", { name: "Free, transparent finance tools" });
  await hero.getByRole("link", { name: "Sign in with Google" }).click();

  // The fake OIDC provider stands in for Google's consent screen.
  await expect(page.getByRole("button", { name: "Continue" })).toBeVisible();
});

test("landing page shows all eight tools, each with its question, highlights and a demo link", async ({ page }) => {
  await page.goto("/");

  const cards = page.getByTestId("tool-card");
  await expect(cards).toHaveCount(TOOLS.length);
  for (const name of TOOLS) {
    const card = page.getByRole("article", { name, exact: true });
    await expect(card).toHaveCount(1);
    await expect(card.getByTestId("tool-question")).toHaveText(/\?$/);
    const highlights = await card.getByRole("listitem").count();
    expect(highlights).toBeGreaterThanOrEqual(2);
    expect(highlights).toBeLessThanOrEqual(3);
    await expect(card.getByRole("link", { name: /^Open demo/ })).toHaveAttribute("href", TOOL_PATHS[name]);
  }
});

test("a card's Open demo button opens that tool", async ({ page }) => {
  await page.goto("/");

  await page
    .getByRole("article", { name: "Risk & Performance", exact: true })
    .getByRole("link", { name: /^Open demo/ })
    .click();
  await expect(page).toHaveURL(/\/risk$/);
  await expect(page.getByRole("heading", { level: 1, name: "Risk & Performance" })).toBeVisible();
});

test("the Free account unlocks section lists what signing in adds", async ({ page }) => {
  await page.goto("/");

  const unlocks = page.getByRole("region", { name: "Free account unlocks" });
  await expect(unlocks).toContainText("your own Tiingo or FMP key");
  await expect(unlocks).toContainText("Saved portfolios");
  await expect(unlocks).toContainText("import");
  await expect(unlocks).toContainText("AI Explain");
  await expect(unlocks).toContainText("AI Analyst");
});

test("footer shows the investment disclaimer and an attribution slot", async ({ page }) => {
  await page.goto("/");

  const footer = page.getByRole("contentinfo");
  await expect(footer).toContainText("Not investment advice");
  await expect(footer).toContainText(
    "Sextant uses cookieless, anonymous page-view analytics (Vercel Web Analytics).",
  );
  await expect(footer.getByTestId("attribution-slot")).toBeAttached();
});

test("pages send no analytics outside Vercel", async ({ page }) => {
  const analyticsRequests: string[] = [];
  page.on("request", (request) => {
    const url = request.url();
    if (url.includes("/_vercel/insights") || url.includes("va.vercel-scripts.com")) analyticsRequests.push(url);
  });

  await page.goto("/");
  await expect(page.getByTestId("compute-status")).toHaveText(/Compute service: online/);
  await page.getByRole("link", { name: "Options Calculator" }).first().click();
  await expect(page).toHaveURL(/\/options/);
  await page.waitForLoadState("networkidle");

  expect(analyticsRequests).toEqual([]);
  expect(await page.locator('script[src*="insights"], script[src*="va.vercel-scripts.com"]').count()).toBe(0);
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

    // One column: every tool card starts at the same left edge.
    const lefts = await page
      .getByTestId("tool-card")
      .evaluateAll((cards) => cards.map((card) => Math.round(card.getBoundingClientRect().left)));
    expect(lefts).toHaveLength(TOOLS.length);
    expect(new Set(lefts).size).toBe(1);

    await page.getByRole("button", { name: "Menu" }).click();
    await page
      .getByRole("navigation", { name: "Tools" })
      .getByRole("link", { name: "Macro Dashboard", exact: true })
      .click();
    await expect(page.getByRole("heading", { level: 1, name: "Macro Dashboard" })).toBeVisible();
  });
});
