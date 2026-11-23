import { expect, test, type Page } from "@playwright/test";

// AI Explain on every tool besides the single-option tab of Options. The model is e2e/fake-anthropic.mjs: for
// these tools it names the tool, counts the metrics computed and says when the
// result is demo data. The e2e daily quota is 3; each test signs in with its own email.

function uniqueEmail(label: string) {
  return `${label}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.test`;
}

async function signInOn(page: Page, path: string) {
  await page.goto(path);
  await page.getByRole("banner").getByRole("link", { name: "Sign in with Google" }).click();
  await page.getByLabel("Email").fill(uniqueEmail("ai-tools"));
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page).toHaveURL(new RegExp(`${path}$`));
  return page.getByRole("main").getByRole("region", { name: "AI Explain" });
}

for (const { path, tool } of [
  { path: "/risk", tool: "risk" },
  { path: "/portfolio", tool: "portfolio" },
]) {
  test(`${path}: demo-data results are explained as demo data`, async ({ page }) => {
    const ai = await signInOn(page, path);

    await ai.first().getByRole("button", { name: "AI Explain" }).click();

    const explanation = ai.first().getByTestId("ai-explanation");
    await expect(explanation).toContainText(`This ${tool} result has`);
    await expect(explanation).toContainText("This result uses synthetic demo data, not real market data.");
  });
}

for (const tab of ["Strategy builder", "American (binomial)"]) {
  test(`options, ${tab}: the tab's result gets its own explanation`, async ({ page }) => {
    await signInOn(page, "/options");
    const main = page.getByRole("main");
    // The tabs are server-rendered, so a click before hydration is lost and the
    // single-option tab stays open: retry until the tab is really selected.
    const tabButton = main.getByRole("tab", { name: tab });
    await expect(async () => {
      await tabButton.click();
      await expect(tabButton).toHaveAttribute("aria-selected", "true", { timeout: 1000 });
    }).toPass();
    const ai = main.getByRole("tabpanel", { name: tab }).getByRole("region", { name: "AI Explain" });

    await ai.getByRole("button", { name: "AI Explain" }).click();

    await expect(ai.getByTestId("ai-explanation")).toContainText("This options result has");
    await expect(ai.getByTestId("ai-quota")).toHaveText("2 of 3 AI calls left today");
  });
}

for (const { path, tools } of [
  { path: "/company", tools: ["company", "company"] },
  { path: "/valuation", tools: ["valuation"] },
  { path: "/macro", tools: ["macro", "macro"] },
  { path: "/screener", tools: ["screener", "screener"] },
]) {
  test(`${path}: every result on the page has AI Explain, sharing one quota`, async ({ page }) => {
    const ai = await signInOn(page, path);
    // A cold screen over the recorded EDGAR frames can take a while.
    await expect(ai).toHaveCount(tools.length, { timeout: 30_000 });
    for (let i = 0; i < tools.length; i++) {
      await expect(ai.nth(i).getByTestId("ai-quota")).toHaveText("3 of 3 AI calls left today");
    }

    await ai.first().getByRole("button", { name: "AI Explain" }).click();

    const explanation = ai.first().getByTestId("ai-explanation");
    await expect(explanation).toContainText(`This ${tools[0]} result has`);
    await expect(explanation).not.toContainText("demo data");
    for (let i = 0; i < tools.length; i++) {
      await expect(ai.nth(i).getByTestId("ai-quota")).toHaveText("2 of 3 AI calls left today");
    }
  });
}
