import { expect, test } from "@playwright/test";

// Time-weighted and money-weighted (IRR) returns of a saved portfolio. Sign-in
// uses the fake OIDC provider (e2e/fake-oidc.mjs).

function uniqueEmail(label: string) {
  return `${label}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.test`;
}

test("a user sees the portfolio's time-weighted and money-weighted returns, and an import changes the IRR", async ({
  page,
}) => {
  await page.goto("/portfolio");
  await page.getByRole("banner").getByRole("link", { name: "Sign in with Google" }).click();
  await page.getByLabel("Email").fill(uniqueEmail("returns"));
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page).toHaveURL(/\/portfolio$/);
  const saved = page.getByRole("main").getByRole("region", { name: "Your portfolios" });
  await saved.getByLabel("Portfolio name").fill("Brokerage");
  await saved.getByLabel("Ticker 1").fill("DEMO-C");
  await saved.getByLabel("Quantity 1").fill("1");
  await saved.getByLabel("Cost price 1").fill("50");
  await saved.getByRole("button", { name: "Save portfolio" }).click();
  await expect(saved.getByRole("status").first()).toContainText("Saved");

  const returns = saved.getByRole("region", { name: "Your return" });
  const irr = returns.locator('[data-metric-value="irr:portfolio"]');
  for (const id of ["twr", "twr_annualized", "irr"]) {
    await expect(returns.locator(`[data-metric-value="${id}:portfolio"]`)).toHaveAttribute("data-status", "ok");
  }
  await expect(irr).toContainText("%");
  await expect(returns.getByText("Which one to use")).toBeVisible();
  await expect(returns.getByTestId("explainer")).toHaveCount(3);
  const before = await irr.textContent();

  // A large buy in the middle of the range weights the IRR towards the later period.
  const importer = saved.getByRole("region", { name: "Import transactions" });
  await importer.getByLabel("CSV file").setInputFiles({
    name: "trades.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("Date,Ticker,Side,Quantity,Price\n2023-06-01,DEMO-C,Buy,100,1\n"),
  });
  await importer.getByRole("button", { name: "Import 1 transaction" }).click();
  await expect(importer.getByRole("status")).toContainText("Imported 1 transaction.");

  await expect(irr).toHaveAttribute("data-status", "ok");
  await expect(irr).not.toHaveText(before ?? "");
});
