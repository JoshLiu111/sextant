import { expect, type Locator, type Page } from "@playwright/test";

// Shared by the "How to use" specs (spec 02, issues #66–#68).

/** A metric's value on the page, by its `data-metric-value` id. */
export const metric = (page: Page, id: string) => page.getByRole("main").locator(`[data-metric-value="${id}"]`);

/** EDGAR and FRED come from the e2e fakes; a cold compute cache is slow. */
export const COLD = { timeout: 30_000 };

/** Opens a tool page and returns its "How to use" panel. */
export async function openTool(page: Page, url: string) {
  await page.goto(url);
  const panel = page.getByRole("main").getByRole("region", { name: "How to use" });
  await expect(panel).toBeVisible();
  return panel;
}

/** The panel's steps; visible only while the panel is open. */
export const steps = (panel: Locator) => panel.getByRole("list", { name: "Getting started" });

/**
 * Waits until a visitor's panel can react to a click. The panel is
 * server-rendered, so a toggle before hydration is not remembered; its
 * visitor-only extras line comes from the panel's own client check, so once
 * it's in the page the panel is live. Every tool has extras today.
 */
export async function untilPanelIsLive(panel: Locator) {
  await expect(panel.getByTestId("signed-in-extras")).toBeAttached();
}

export function uniqueEmail(label: string) {
  return `${label}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.test`;
}
