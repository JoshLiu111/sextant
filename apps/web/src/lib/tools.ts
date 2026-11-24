// The tool registry: the nav, the home page cards and the dashboard cards read
// from here, including the group each tool sits in. Display strings live in
// src/i18n (messages.tools[slug] and messages.toolGroups[group]). The footer
// attribution follows the results on the page (components/PageSources.tsx), not the tool.
export type ToolSlug =
  | "options"
  | "risk"
  | "portfolio"
  | "company"
  | "valuation"
  | "macro"
  | "screener"
  | "ai-analyst";

/** The groups, in display order. The nav shows a one-tool group as a direct link. */
export const TOOL_GROUPS = ["markets", "companies", "portfolio-risk", "ai-analyst"] as const;
export type ToolGroup = (typeof TOOL_GROUPS)[number];

export type Tool = {
  slug: ToolSlug;
  href: `/${string}`;
  status: "live" | "coming-soon";
  group: ToolGroup;
};

// In display order within each group.
export const TOOLS: readonly Tool[] = [
  { slug: "macro", href: "/macro", status: "live", group: "markets" },
  { slug: "screener", href: "/screener", status: "live", group: "markets" },
  { slug: "company", href: "/company", status: "live", group: "companies" },
  { slug: "valuation", href: "/valuation", status: "live", group: "companies" },
  { slug: "portfolio", href: "/portfolio", status: "live", group: "portfolio-risk" },
  { slug: "risk", href: "/risk", status: "live", group: "portfolio-risk" },
  { slug: "options", href: "/options", status: "live", group: "portfolio-risk" },
  { slug: "ai-analyst", href: "/ai-analyst", status: "live", group: "ai-analyst" },
];

/** Every group with its tools, both in display order. */
export const TOOLS_BY_GROUP: readonly { group: ToolGroup; tools: readonly Tool[] }[] = TOOL_GROUPS.map(
  (group) => ({ group, tools: TOOLS.filter((tool) => tool.group === group) }),
);

export function getTool(slug: ToolSlug): Tool {
  const tool = TOOLS.find((t) => t.slug === slug);
  if (!tool) throw new Error(`Unknown tool: ${slug}`);
  return tool;
}
