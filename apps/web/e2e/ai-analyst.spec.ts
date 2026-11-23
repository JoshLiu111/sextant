import { expect, test, type Page } from "@playwright/test";

// AI Analyst. The model is e2e/fake-anthropic.mjs: asked a question with tools, it
// prices the default option with options_price, then answers citing the call price
// it got back. A question containing "misquote" makes it cite a wrong number
// (12.00 instead of 10.45). The e2e daily quota is 3 (shared with AI Explain).

function uniqueEmail(label: string) {
  return `${label}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.test`;
}

async function signInOnAnalyst(page: Page) {
  await page.goto("/ai-analyst");
  await page
    .getByRole("banner")
    .getByRole("link", { name: "Sign in with Google" })
    .click();
  await page.getByLabel("Email").fill(uniqueEmail("analyst"));
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page).toHaveURL(/\/ai-analyst$/);
  return page.getByRole("main");
}

async function ask(main: ReturnType<Page["getByRole"]>, question: string) {
  await main.getByRole("textbox", { name: "Your question" }).fill(question);
  await main.getByRole("button", { name: "Ask" }).click();
  return main.getByRole("region", { name: "Answer" });
}

test("visitors are told to sign in to use AI Analyst", async ({ page }) => {
  await page.goto("/ai-analyst");
  const main = page.getByRole("main");

  await expect(
    main.getByRole("heading", { level: 1, name: "AI Analyst" }),
  ).toBeVisible();
  await expect(main).toContainText("Sign in to use AI Analyst");
  await expect(
    main.getByRole("link", { name: "Sign in with Google" }),
  ).toHaveAttribute("href", "/auth/signin?returnTo=%2Fai-analyst");
  await expect(main.getByRole("button", { name: "Ask" })).toHaveCount(0);
});

test("a question is answered through a tool call, with the number traced to its calculation", async ({
  page,
}) => {
  const main = await signInOnAnalyst(page);
  await expect(main.getByTestId("ai-quota")).toHaveText(
    "3 of 3 AI calls left today",
  );

  const answer = await ask(
    main,
    "What is an at-the-money one-year call worth?",
  );

  await expect(answer.getByTestId("analyst-answer")).toContainText(
    "worth 10.45 per share",
  );
  const cited = answer.getByTestId("citation");
  await expect(cited).toHaveText("10.45");
  await expect(cited).toHaveAttribute("data-matches", "true");
  await expect(answer.getByTestId("analyst-mismatch-notice")).toHaveCount(0);
  await expect(main.getByTestId("ai-quota")).toHaveText(
    "2 of 3 AI calls left today",
  );

  // The trace: which tool was called with which parameters.
  const call = answer.getByTestId("analyst-call");
  await expect(call).toHaveCount(1);
  await expect(call).toContainText("options_price");
  await expect(call.getByTestId("analyst-call-input")).toContainText(
    '"volatility": 0.2',
  );

  // The cited number opens its calculation's raw result.
  const raw = call.getByTestId("analyst-raw-result");
  await expect(raw).not.toBeVisible();
  await cited.click();
  await expect(raw).toBeVisible();
  await expect(raw).toContainText('"call_price"');
  await expect(raw).toContainText("10.450");
});

test("a number that doesn't match its calculation is flagged in red", async ({
  page,
}) => {
  const main = await signInOnAnalyst(page);

  const answer = await ask(main, "Please misquote the call price.");

  const cited = answer.getByTestId("citation");
  await expect(cited).toHaveText("12.00");
  await expect(cited).toHaveAttribute("data-matches", "false");
  await expect(cited).toHaveClass(/text-red-700/);
  await expect(cited).toHaveAccessibleDescription(/does not match.*10\.45/i);
  await expect(answer.getByTestId("analyst-mismatch-notice")).toHaveText(
    "1 number in this answer does not match the calculation it cites. It is highlighted in red.",
  );
});
