import { expect, type Locator } from "@playwright/test";

// Shared by the Risk & Performance specs: the results sit in tabs (issue #70).

/** Opens a Risk results tab ("Overview", "Rolling & distribution", "Model checks", "Technical analysis"). */
export async function openRiskTab(main: Locator, name: string) {
  const tab = main.getByRole("tab", { name });
  // Server-rendered: a click before hydration is lost, so retry until it lands.
  await expect(async () => {
    await tab.click();
    await expect(tab).toHaveAttribute("aria-selected", "true", { timeout: 1000 });
  }).toPass();
}
