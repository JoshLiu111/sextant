import type { AttributionId } from "./attributions";

// The tool registry: the home page cards, the nav and the footer attribution
// all read from here. Display strings live in src/i18n (messages.tools[slug]).
export type ToolSlug =
  | "options"
  | "risk"
  | "portfolio"
  | "company"
  | "valuation"
  | "macro"
  | "screener"
  | "ai-analyst";

export type Tool = {
  slug: ToolSlug;
  href: `/${string}`;
  status: "live" | "coming-soon";
  /** Data sources the page actually uses; rendered in the footer attribution slot. */
  attributions: readonly AttributionId[];
};

export const TOOLS: readonly Tool[] = [
  { slug: "options", href: "/options", status: "live", attributions: [] },
  { slug: "risk", href: "/risk", status: "live", attributions: ["demo"] },
  { slug: "portfolio", href: "/portfolio", status: "coming-soon", attributions: [] },
  { slug: "company", href: "/company", status: "coming-soon", attributions: [] },
  { slug: "valuation", href: "/valuation", status: "coming-soon", attributions: [] },
  { slug: "macro", href: "/macro", status: "coming-soon", attributions: [] },
  { slug: "screener", href: "/screener", status: "coming-soon", attributions: [] },
  { slug: "ai-analyst", href: "/ai-analyst", status: "coming-soon", attributions: [] },
];

export function getTool(slug: ToolSlug): Tool {
  const tool = TOOLS.find((t) => t.slug === slug);
  if (!tool) throw new Error(`Unknown tool: ${slug}`);
  return tool;
}

/** The tool whose route contains `pathname` (e.g. "/macro" or "/macro/anything"). */
export function toolForPath(pathname: string): Tool | undefined {
  return TOOLS.find((t) => pathname === t.href || pathname.startsWith(`${t.href}/`));
}
