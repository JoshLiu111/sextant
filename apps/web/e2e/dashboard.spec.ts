import { expect, test, type Page } from "@playwright/test";

// The signed-in user's dashboard (/dashboard) and the routing between it and the
// landing page (/). Sign-in runs against the fake OIDC provider in
// e2e/fake-oidc.mjs; each test signs in with its own email.

test("a visitor opening /dashboard ends on the landing page", async ({ page }) => {
  await page.goto("/dashboard");

  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("region", { name: "Free, transparent finance tools" })).toBeVisible();
});

function uniqueEmail(label: string) {
  return `${label}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.test`;
}

/** Signs in from the landing page's hero, which returns to `/`. */
async function signInFromLanding(page: Page, email: string, name = "") {
  await page.goto("/");
  await page
    .getByRole("region", { name: "Free, transparent finance tools" })
    .getByRole("link", { name: "Sign in with Google" })
    .click();
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Name").fill(name);
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
}

test("signing in from the landing page ends on the dashboard", async ({ page }) => {
  await signInFromLanding(page, uniqueEmail("landing"), "Ada Lovelace");

  await expect(page.getByRole("heading", { level: 1 })).toContainText("Ada Lovelace");
});

test("a signed-in user opening / ends on the dashboard", async ({ page }) => {
  await signInFromLanding(page, uniqueEmail("root"));

  await page.goto("/risk");
  await page.goto("/");
  await expect(page).toHaveURL(/\/dashboard$/);
});

test("signing in from a tool page returns to that tool page", async ({ page }) => {
  await page.goto("/valuation");
  await page.getByRole("banner").getByRole("link", { name: "Sign in with Google" }).click();
  await page.getByLabel("Email").fill(uniqueEmail("tool"));
  await page.getByRole("button", { name: "Continue" }).click();

  await expect(page).toHaveURL(/\/valuation$/);
  await expect(page.getByRole("banner").getByTestId("signed-in-user")).toBeVisible();
});

test("with an invalid session cookie, / shows the landing page and nothing loops", async ({ page, context, baseURL }) => {
  await context.addCookies([{ name: "sextant_session", value: "not-a-real-session", url: baseURL! }]);

  await page.goto("/");
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("region", { name: "Free, transparent finance tools" })).toBeVisible();

  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("region", { name: "Free, transparent finance tools" })).toBeVisible();
});

// The tool nav is unchanged by signing in: three group menus and the AI Analyst link.
async function expectToolNav(page: Page) {
  const nav = page.getByRole("navigation", { name: "Tools" });
  await expect(nav.getByRole("button")).toHaveCount(3);
  for (const group of ["Markets", "Companies", "Portfolio & Risk"]) {
    await expect(nav.getByRole("button", { name: group, exact: true })).toBeVisible();
  }
  await expect(nav.getByRole("link")).toHaveText(["AI Analyst"]);
}

test("a signed-in user gets a Dashboard nav link, and the logo points to the dashboard", async ({ page }) => {
  await signInFromLanding(page, uniqueEmail("nav"));
  await page.goto("/risk");

  const banner = page.getByRole("banner");
  await expect(banner.getByRole("link", { name: "Sextant", exact: true })).toHaveAttribute("href", "/dashboard");
  await banner.getByRole("link", { name: "Dashboard", exact: true }).click();
  await expect(page).toHaveURL(/\/dashboard$/);

  await expectToolNav(page);
});

test("a visitor gets no Dashboard link, and the logo points to the landing page", async ({ page }) => {
  await page.goto("/risk");

  const banner = page.getByRole("banner");
  await expect(banner.getByRole("link", { name: "Sign in with Google" })).toBeVisible();
  await expect(banner.getByRole("link", { name: "Sextant", exact: true })).toHaveAttribute("href", "/");
  await expect(banner.getByRole("link", { name: "Dashboard", exact: true })).toHaveCount(0);
  await expectToolNav(page);
});

test("dashboard groups the tool cards under the nav's four groups", async ({ page }) => {
  await signInFromLanding(page, uniqueEmail("groups"));

  const tools = page.getByRole("main").getByRole("region", { name: "Your tools" });
  const groups: Record<string, string[]> = {
    Markets: ["Macro Dashboard", "Screener & Calendar"],
    Companies: ["Company Health Check", "Valuation Calculator"],
    "Portfolio & Risk": ["My Portfolio", "Risk & Performance", "Options Calculator"],
    "AI Analyst": ["AI Analyst"],
  };
  for (const [group, names] of Object.entries(groups)) {
    const section = tools.getByRole("region", { name: group, exact: true });
    await expect(section.getByRole("article")).toHaveCount(names.length);
    for (const name of names) await expect(section.getByRole("article", { name, exact: true })).toHaveCount(1);
  }
});

test("dashboard tool cards open the tool, with no demo wording", async ({ page }) => {
  await signInFromLanding(page, uniqueEmail("cards"));

  const card = page.getByRole("main").getByRole("article", { name: "Risk & Performance", exact: true });
  await expect(card.getByRole("link", { name: /demo/i })).toHaveCount(0);
  await card.getByRole("link", { name: "Open: Risk & Performance" }).click();
  await expect(page).toHaveURL(/\/risk$/);
});

test.describe("status strip", () => {
  // The quota resets at midnight UTC; the dashboard shows it in the user's own time zone.
  test.use({ timezoneId: "America/New_York" });

  test("a fresh user sees no key with a Settings link, the full AI quota and 0 portfolios", async ({ page }) => {
    await signInFromLanding(page, uniqueEmail("fresh"), "Grace Hopper");
    const main = page.getByRole("main");
    await expect(main.getByRole("heading", { level: 1 })).toHaveText("Welcome, Grace Hopper");

    const quota = main.getByRole("region", { name: "AI quota" });
    await expect(quota).toContainText("3 of 3 AI calls left today");
    await expect(quota).toContainText(/Resets at (7:00 PM EST|8:00 PM EDT)/);

    const portfolios = main.getByRole("region", { name: "Saved portfolios" });
    await expect(portfolios).toContainText("0 saved portfolios");
    await expect(portfolios.getByRole("link", { name: "Open My Portfolio" })).toHaveAttribute("href", "/portfolio");

    const key = main.getByRole("region", { name: "Data key" });
    await expect(key).toContainText("No key connected");
    await key.getByRole("link", { name: "Add a key in Settings" }).click();
    await expect(page).toHaveURL(/\/settings$/);
  });

  test("after saving a key and a portfolio, the strip and the My Portfolio card show them", async ({ page }) => {
    await signInFromLanding(page, uniqueEmail("saved"));

    // Save a Tiingo key through Settings (the fake accepts keys starting with "good").
    await page.goto("/settings");
    const tiingo = page.getByRole("main").getByRole("region", { name: "Your Tiingo key" });
    await tiingo.getByLabel("Tiingo API key").fill("good0000000000000000000000000000000abcd");
    await tiingo.getByRole("button", { name: "Save key" }).click();
    await expect(tiingo.getByRole("status")).toHaveText("Key saved.");

    // Save a portfolio through My Portfolio.
    await page.goto("/portfolio");
    const saved = page.getByRole("main").getByRole("region", { name: "Your portfolios" });
    await saved.getByRole("button", { name: "New portfolio" }).click();
    await saved.getByLabel("Portfolio name").fill("Core");
    await saved.getByLabel("Ticker 1").fill("AAPL");
    await saved.getByLabel("Quantity 1").fill("10");
    await saved.getByLabel("Cost price 1").fill("150");
    await saved.getByRole("button", { name: "Save portfolio" }).click();
    await expect(saved.getByRole("status")).toContainText("Saved");

    await page.goto("/dashboard");
    const main = page.getByRole("main");
    const key = main.getByRole("region", { name: "Data key" });
    await expect(key).toContainText("Tiingo connected");
    await expect(key).not.toContainText("No key connected");
    await expect(main.getByRole("region", { name: "Saved portfolios" })).toContainText("1 saved portfolio");
    await expect(main.getByRole("article", { name: "My Portfolio", exact: true })).toContainText("1 saved portfolio");
  });

  test("the AI remaining count matches the quota endpoint", async ({ page }) => {
    await signInFromLanding(page, uniqueEmail("quota"));
    // Spend one call with AI Explain on the Options Calculator.
    await page.goto("/options");
    const ai = page.getByRole("main").getByRole("region", { name: "AI Explain" });
    await ai.getByRole("button", { name: "AI Explain" }).click();
    await expect(ai.getByTestId("ai-quota")).toHaveText("2 of 3 AI calls left today");
    await page.goto("/dashboard");

    const res = await page.request.get("/api/compute/ai/quota");
    expect(res.ok()).toBe(true);
    const quota = (await res.json()) as { limit: number; remaining: number };

    await expect(page.getByRole("main").getByRole("region", { name: "AI quota" })).toContainText(
      `${quota.remaining} of ${quota.limit} AI calls left today`,
    );
  });

  test("a status item that fails to load shows unavailable, and the rest still renders", async ({ page }) => {
    await signInFromLanding(page, uniqueEmail("failing"), "Katherine Johnson");
    await page.route("**/api/compute/portfolios", (route) =>
      route.fulfill({ status: 503, contentType: "application/json", body: "{}" }),
    );
    await page.reload();

    const main = page.getByRole("main");
    await expect(main.getByRole("region", { name: "Saved portfolios" })).toContainText(/unavailable/i);
    await expect(main.getByRole("heading", { level: 1 })).toHaveText("Welcome, Katherine Johnson");
    await expect(main.getByRole("region", { name: "Data key" })).toContainText("No key connected");
    await expect(main.getByRole("region", { name: "AI quota" })).toContainText("3 of 3 AI calls left today");
    await expect(main.getByTestId("tool-card")).toHaveCount(8);
  });

  test("status items whose requests never reach the server show unavailable, each on its own", async ({ page }) => {
    await signInFromLanding(page, uniqueEmail("offline"), "Dorothy Vaughan");
    await page.route("**/api/compute/keys", (route) => route.abort());
    await page.route("**/api/compute/portfolios", (route) => route.abort());
    await page.reload();

    const main = page.getByRole("main");
    await expect(main.getByRole("region", { name: "Data key" })).toContainText(/unavailable/i);
    await expect(main.getByRole("region", { name: "Saved portfolios" })).toContainText(/unavailable/i);
    await expect(main.getByRole("article", { name: "My Portfolio", exact: true })).toContainText(/unavailable/i);
    await expect(main.getByRole("region", { name: "AI quota" })).toContainText("3 of 3 AI calls left today");
  });

  test("a user with no name is greeted by email", async ({ page }) => {
    const email = uniqueEmail("noname");
    await signInFromLanding(page, email);

    await expect(page.getByRole("main").getByRole("heading", { level: 1 })).toHaveText(`Welcome, ${email}`);
  });
});
