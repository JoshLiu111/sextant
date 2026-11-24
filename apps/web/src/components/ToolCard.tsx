import Link from "next/link";
import type { ReactNode } from "react";
import { getMessages, type Messages } from "@/i18n";
import type { Tool } from "@/lib/tools";

/**
 * One tool as a card: the question it answers, its highlights and a link that
 * opens it. Shared by the landing page (`action="openDemo"`) and the dashboard
 * (`action="open"`); `personal` is an optional slot for the signed-in user's
 * own info about this tool.
 */
export function ToolCard({
  tool,
  action,
  personal,
}: {
  tool: Tool;
  action: keyof Messages["common"]["toolCard"];
  personal?: ReactNode;
}) {
  const t = getMessages();
  const label = t.common.toolCard[action];
  const copy = t.tools[tool.slug];
  const headingId = `tool-card-${tool.slug}`;
  return (
    <article
      aria-labelledby={headingId}
      data-testid="tool-card"
      className="flex h-full flex-col rounded-lg border border-black/10 p-4 dark:border-white/15"
    >
      <h4 id={headingId} className="font-semibold">
        {copy.name}
      </h4>
      <p data-testid="tool-question" className="mt-1 text-sm font-medium">
        {copy.question}
      </p>
      <ul className="mt-3 flex list-disc flex-col gap-1 pl-5 text-sm text-black/70 dark:text-white/70">
        {copy.highlights.map((highlight) => (
          <li key={highlight}>{highlight}</li>
        ))}
      </ul>
      {personal && <div className="mt-3 text-sm">{personal}</div>}
      {tool.status === "coming-soon" && (
        <span className="mt-3 self-start rounded bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-900">
          {t.comingSoon.badge}
        </span>
      )}
      <Link
        href={tool.href}
        aria-label={`${label}: ${copy.name}`}
        className="mt-auto self-start pt-4"
      >
        <span className="inline-block rounded border border-black/15 px-3 py-1 text-sm font-medium hover:border-black/40 dark:border-white/20 dark:hover:border-white/50">
          {label}
        </span>
      </Link>
    </article>
  );
}
