// The "How to use" panel's content shape (spec 02). Each tool's copy lives in
// src/i18n under `tools[slug].howTo`, checked with `satisfies HowToUse`; the
// panel is `<HowToUsePanel tool={slug} />` at the top of the tool's page.

/**
 * - `steps`: 3–5 short steps, the same for visitors and signed-in users.
 * - `examples`: 1–2 "Try this" links. `params` are the tool's own URL inputs
 *   (the shareable-link format in lib/urlInputs.ts), so a click fills in the form
 *   and shows a result.
 * - `signedInExtras`: what signing in adds on this tool, shown only to visitors.
 *   Empty when the tool has nothing extra for signed-in users.
 */
export type HowToUse = {
  steps: readonly string[];
  // `| undefined` only so that examples with different params type-check side by side.
  examples: readonly { label: string; params: Readonly<Record<string, string | undefined>> }[];
  signedInExtras: readonly string[];
};
