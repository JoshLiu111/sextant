import { expect, test, type Page } from "@playwright/test";

// Settings: a signed-in user's own Tiingo key. Tiingo is the fake in
// e2e/fake-tiingo.mjs: keys starting with "good" are valid, "outage…" makes it
// answer 503, anything else is rejected.

function uniqueEmail(label: string) {
  return `${label}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.test`;
}

async function signInOnSettings(page: Page, email: string) {
  await page.goto("/settings");
  await page.getByRole("main").getByRole("link", { name: "Sign in with Google" }).click();
  await page.getByLabel("Email").fill(email);
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page).toHaveURL(/\/settings$/);
  const section = page.getByRole("main").getByRole("region", { name: "Your Tiingo key" });
  await expect(section.getByLabel("Tiingo API key")).toBeVisible();
  return section;
}

test("anonymous visitors see a prompt to sign in to add their own key", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("banner").getByRole("link", { name: "Settings" }).click();
  await expect(page).toHaveURL(/\/settings$/);

  const prompt = page.getByRole("main").getByTestId("key-sign-in-prompt");
  await expect(prompt).toContainText("Sign in to add your own key");
  await expect(prompt.getByRole("link", { name: "Sign in with Google" })).toHaveAttribute(
    "href",
    "/auth/signin?returnTo=%2Fsettings",
  );
  await expect(page.getByLabel("Tiingo API key")).toHaveCount(0);
});

test("a signed-in user saves, replaces and deletes a Tiingo key", async ({ page }) => {
  const section = await signInOnSettings(page, uniqueEmail("keys"));
  const keyInput = section.getByLabel("Tiingo API key");
  const status = section.getByTestId("key-status");
  await expect(status).toHaveText("No key saved. Market data tools use demo data.");

  // Rejected by Tiingo: a clear error, nothing stored.
  await keyInput.fill("wrong-key-1234");
  await section.getByRole("button", { name: "Save key" }).click();
  await expect(section.getByTestId("field-error-key")).toContainText("key is invalid");
  await expect(status).toHaveText("No key saved. Market data tools use demo data.");

  // Tiingo down: a different message, nothing stored.
  await keyInput.fill("outage-key-0000");
  await section.getByRole("button", { name: "Save key" }).click();
  await expect(section.getByRole("alert")).toContainText("temporarily unavailable");
  await expect(status).toHaveText("No key saved. Market data tools use demo data.");

  const firstKey = "good0000000000000000000000000000000abcd";
  await keyInput.fill(firstKey);
  await section.getByRole("button", { name: "Save key" }).click();
  await expect(section.getByRole("status")).toHaveText("Key saved.");
  await expect(status).toContainText("ending in abcd");
  await expect(keyInput).toHaveValue("");

  // After a reload the key is still saved and only its hint reaches the browser.
  await page.reload();
  await expect(status).toContainText("ending in abcd");
  expect(await page.content()).not.toContain(firstKey);

  await keyInput.fill("good1111111111111111111111111111111wxyz");
  await section.getByRole("button", { name: "Replace key" }).click();
  await expect(section.getByRole("status")).toHaveText("Key saved.");
  await expect(status).toContainText("ending in wxyz");

  await section.getByRole("button", { name: "Delete key" }).click();
  await section.getByRole("button", { name: "Yes, delete my key" }).click();
  await expect(status).toHaveText("No key saved. Market data tools use demo data.");
  await page.reload();
  await expect(status).toHaveText("No key saved. Market data tools use demo data.");
});
