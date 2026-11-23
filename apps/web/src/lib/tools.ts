// The tool registry: the home page cards and the nav read from here. Display
// strings live in src/i18n (messages.tools[slug]). The footer attribution
// follows the results on the page (components/PageSources.tsx), not the tool.
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
};

export const TOOLS: readonly Tool[] = [
  { slug: "options", href: "/options", status: "live" },
  { slug: "risk", href: "/risk", status: "live" },
  { slug: "portfolio", href: "/portfolio", status: "live" },
  { slug: "company", href: "/company", status: "live" },
  { slug: "valuation", href: "/valuation", status: "live" },
  { slug: "macro", href: "/macro", status: "live" },
  { slug: "screener", href: "/screener", status: "live" },
  { slug: "ai-analyst", href: "/ai-analyst", status: "live" },
];

export function getTool(slug: ToolSlug): Tool {
  const tool = TOOLS.find((t) => t.slug === slug);
  if (!tool) throw new Error(`Unknown tool: ${slug}`);
  return tool;
}
