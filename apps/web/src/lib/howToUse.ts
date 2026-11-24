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

/** The tool's URL with these inputs, `,` and `:` left readable as in shared links. */
export function exampleHref(path: string, params: Readonly<Record<string, string | undefined>>): string {
  const defined = Object.entries(params).filter((entry): entry is [string, string] => entry[1] !== undefined);
  const query = new URLSearchParams(defined).toString().replace(/%2C/gi, ",").replace(/%3A/gi, ":");
  return query ? `${path}?${query}` : path;
}
