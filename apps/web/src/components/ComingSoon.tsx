import Link from "next/link";
import { getMessages } from "@/i18n";
import type { ToolSlug } from "@/lib/tools";

/** Placeholder page body for a tool that is not built yet. */
export function ComingSoon({ slug }: { slug: ToolSlug }) {
  const t = getMessages();
  const tool = t.tools[slug];
  return (
    <main className="mx-auto w-full max-w-6xl px-4 py-10">
      <h1 className="text-3xl">{tool.name}</h1>
      <p className="mt-2 text-ink-2">{tool.description}</p>
      <p className="mt-6 inline-block rounded-card bg-paper-2 px-2 py-1 text-sm font-medium text-ink">
        {t.comingSoon.badge}
      </p>
      <p className="mt-3">{t.comingSoon.body}</p>
      <Link href="/" className="link mt-6 inline-block">
        {t.comingSoon.back}
      </Link>
    </main>
  );
}
