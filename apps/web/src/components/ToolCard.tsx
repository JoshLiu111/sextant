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
      data-tool={tool.slug}
      className="card flex h-full flex-col p-4 md:p-5"
    >
      <span aria-hidden className="tool-rule mb-4" />
      <h4 id={headingId} className="font-display text-xl leading-tight text-ink">
        {copy.name}
      </h4>
      <p data-testid="tool-question" className="mt-2 text-sm font-medium text-ink">
        {copy.question}
      </p>
      <ul className="mt-3 flex list-disc flex-col gap-1 pl-5 text-sm text-ink-2 marker:text-muted">
        {copy.highlights.map((highlight) => (
          <li key={highlight}>{highlight}</li>
        ))}
      </ul>
      {personal && <div className="mt-3 text-sm">{personal}</div>}
      {tool.status === "coming-soon" && (
        <span className="mt-3 self-start text-xs font-medium text-muted">
          {t.comingSoon.badge}
        </span>
      )}
      <Link
        href={tool.href}
        aria-label={`${label}: ${copy.name}`}
        className="mt-auto self-start pt-4"
      >
        <span className="btn btn-sm">
          {label}
        </span>
      </Link>
    </article>
  );
}
