import { expect, test, type Page } from "@playwright/test";

// AI Explain on the Options Calculator. The model is e2e/fake-anthropic.mjs, which
// answers from the result the compute service sent it; the e2e daily quota is 3
// (AI_DAILY_QUOTA in playwright.config.ts). Each test signs in with its own email.

function uniqueEmail(label: string) {
  return `${label}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.test`;
}

async function signInOnOptions(page: Page) {
  await page.goto("/options");
  await page.getByRole("banner").getByRole("link", { name: "Sign in with Google" }).click();
  await page.getByLabel("Email").fill(uniqueEmail("ai"));
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page).toHaveURL(/\/options$/);
  return page.getByRole("main").getByRole("region", { name: "AI Explain" });
}

test("visitors are told to sign in to use AI Explain", async ({ page }) => {
  await page.goto("/options");
  const ai = page.getByRole("main").getByRole("region", { name: "AI Explain" });

  await expect(ai).toContainText("Sign in to use AI Explain");
  await expect(ai.getByRole("link", { name: "Sign in with Google" })).toHaveAttribute(
    "href",
    "/auth/signin?returnTo=%2Foptions",
  );
  await expect(ai.getByRole("button", { name: "AI Explain" })).toHaveCount(0);
});

test("a signed-in user gets a plain-English explanation and sees the quota go down", async ({ page }) => {
  const ai = await signInOnOptions(page);
  await expect(ai.getByTestId("ai-quota")).toHaveText("3 of 3 AI calls left today");

  await ai.getByRole("button", { name: "AI Explain" }).click();

  // The fake model quotes the call price the compute service calculated (10.45).
  await expect(ai.getByTestId("ai-explanation")).toContainText("the call is worth about 10.45");
  await expect(ai.getByTestId("ai-advice-notice")).toHaveText(
    "This is only a reading of the calculation, not investment advice or a recommendation to buy or sell anything.",
  );
  await expect(ai.getByTestId("ai-quota")).toHaveText("2 of 3 AI calls left today");
});

test("cited numbers are checked against the result, and uncited ones are marked as unchecked", async ({ page }) => {
  const ai = await signInOnOptions(page);
  await ai.getByRole("button", { name: "AI Explain" }).click();

  const explanation = ai.getByTestId("ai-explanation");
  const cited = explanation.getByTestId("citation");
  await expect(cited).toHaveText("10.45");
  await expect(cited).toHaveAttribute("data-matches", "true");
  await expect(cited).toHaveAccessibleDescription(/^From calculation calc_/);
  await expect(ai.getByTestId("mismatch-notice")).toHaveCount(0);
  // The strike (100) is an input, not a metric: the fake model writes it uncited.
  const uncited = explanation.getByTestId("uncited-number");
  await expect(uncited).toHaveText("100");
  await expect(uncited).toHaveAccessibleDescription(/not checked/i);
  await expect(ai.getByTestId("uncited-notice")).toBeVisible();
});

test("a cited number that doesn't match the result is flagged in red", async ({ page }) => {
  const ai = await signInOnOptions(page);
  const callPrice = page.getByRole("main").locator('[data-metric-value="call_price"]');
  // The default result first, so the form has hydrated and won't reset the new spot.
  await expect(callPrice).toContainText("10.45");
  // With a spot of 99 the fake model miscites the call price as 12.00.
  await page.getByRole("main").getByRole("spinbutton", { name: "Spot price" }).fill("99");
  // The S = 99 price itself: "Calculating…" would also pass a not-10.45 check.
  await expect(callPrice).toContainText(/^9\.82/);
  await ai.getByRole("button", { name: "AI Explain" }).click();

  const cited = ai.getByTestId("ai-explanation").getByTestId("citation");
  await expect(cited).toHaveText("12.00");
  await expect(cited).toHaveAttribute("data-matches", "false");
  await expect(cited).toHaveClass(/text-red-700/);
  await expect(cited).toHaveAccessibleDescription(/does not match.*9\.\d\d/i);
  await expect(ai.getByTestId("mismatch-notice")).toHaveText(
    "1 number in this answer does not match the calculation it cites. It is highlighted in red.",
  );
});

test("the explanation follows the result on screen", async ({ page }) => {
  const ai = await signInOnOptions(page);
  const main = page.getByRole("main");
  await ai.getByRole("button", { name: "AI Explain" }).click();
  await expect(ai.getByTestId("ai-explanation")).toBeVisible();

  await main.getByRole("spinbutton", { name: "Spot price" }).fill("120");
  await expect(main.locator('[data-metric-value="call_price"]')).toContainText(/^26\.1/);

  await expect(ai.getByTestId("ai-explanation")).toHaveCount(0);
  await ai.getByRole("button", { name: "AI Explain" }).click();
  // S = 120, otherwise the defaults: BS call 26.17.
  await expect(ai.getByTestId("ai-explanation")).toContainText("the call is worth about 26.17");
});

test.describe("in New York", () => {
  test.use({ timezoneId: "America/New_York" });

  test("calls over the daily quota are refused, with the reset time in the visitor's time zone", async ({ page }) => {
    const ai = await signInOnOptions(page);
    const button = ai.getByRole("button", { name: "AI Explain" });
    for (const left of [2, 1, 0]) {
      await button.click();
      await expect(ai.getByTestId("ai-quota")).toHaveText(`${left} of 3 AI calls left today`);
    }

    await expect(button).toBeDisabled();
    // The quota resets at 00:00 UTC: 7 PM in New York in winter, 8 PM in summer.
    await expect(ai.getByTestId("ai-quota-used-up")).toHaveText(
      /^You have used all of today's AI calls\. Your quota resets at (7:00 PM EST|8:00 PM EDT)\.$/,
    );
  });
});
