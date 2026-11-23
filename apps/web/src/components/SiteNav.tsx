"use client";

import Link from "next/link";
import { useState } from "react";
import { getMessages } from "@/i18n";
import { TOOLS } from "@/lib/tools";

export function SiteNav() {
  const t = getMessages();
  const [open, setOpen] = useState(false);

  return (
    <header className="border-b border-black/10 dark:border-white/15">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-2 px-4 py-3">
        <Link href="/" className="text-lg font-semibold tracking-tight">
          {t.site.name}
        </Link>
        <button
          type="button"
          className="rounded border border-black/15 px-3 py-1 text-sm md:hidden dark:border-white/20"
          aria-expanded={open}
          aria-controls="tools-nav"
          onClick={() => setOpen((o) => !o)}
        >
          {t.site.menu}
        </button>
        <nav
          id="tools-nav"
          aria-label={t.site.toolsNavLabel}
          className={`${open ? "block" : "hidden"} w-full md:block md:w-auto`}
        >
          <ul className="flex flex-col gap-1 py-2 md:flex-row md:flex-wrap md:gap-4 md:py-0">
            {TOOLS.map((tool) => (
              <li key={tool.slug}>
                <Link
                  href={tool.href}
                  className="block py-1 text-sm hover:underline"
                  onClick={() => setOpen(false)}
                >
                  {t.tools[tool.slug].name}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      </div>
    </header>
  );
}
