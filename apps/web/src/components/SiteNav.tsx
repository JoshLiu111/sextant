"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { getMessages } from "@/i18n";
import { TOOLS_BY_GROUP, type ToolGroup } from "@/lib/tools";

/**
 * The top bar. Tools come in the registry's groups (lib/tools.ts): a group with
 * several tools is a disclosure menu, a one-tool group is a direct link. One menu
 * is open at a time; Escape, a click outside or following a link closes it.
 * `account` and `logo` are server-rendered from the signed-in state (see AccountMenu and NavLogo).
 */
export function SiteNav({ account, logo }: { account?: ReactNode; logo: ReactNode }) {
  const t = getMessages();
  const [open, setOpen] = useState(false);
  const [openGroup, setOpenGroup] = useState<ToolGroup | null>(null);
  const navRef = useRef<HTMLElement>(null);
  const buttons = useRef<Partial<Record<ToolGroup, HTMLButtonElement | null>>>({});

  useEffect(() => {
    if (!openGroup) return;
    function onPointerDown(event: PointerEvent) {
      if (!navRef.current?.contains(event.target as Node)) setOpenGroup(null);
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key !== "Escape" || !openGroup) return;
      setOpenGroup(null);
      buttons.current[openGroup]?.focus();
    }
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [openGroup]);

  function closeAll() {
    setOpenGroup(null);
    setOpen(false);
  }

  return (
    <header className="border-b border-black/10 dark:border-white/15">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-2 px-4 py-3">
        {logo}
        <div className="ml-auto md:order-last">{account}</div>
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
          ref={navRef}
          aria-label={t.site.toolsNavLabel}
          className={`${open ? "block" : "hidden"} w-full md:block md:w-auto`}
        >
          <ul className="flex flex-col gap-1 py-2 md:flex-row md:flex-wrap md:gap-4 md:py-0">
            {TOOLS_BY_GROUP.map(({ group, tools }) => {
              if (tools.length === 1) {
                const [tool] = tools;
                return (
                  <li key={group}>
                    <Link href={tool.href} className="block py-1 text-sm hover:underline" onClick={closeAll}>
                      {t.tools[tool.slug].name}
                    </Link>
                  </li>
                );
              }
              const expanded = openGroup === group;
              const menuId = `nav-group-${group}`;
              return (
                <li key={group} className="md:relative">
                  <button
                    type="button"
                    ref={(el) => {
                      buttons.current[group] = el;
                    }}
                    className="block py-1 text-sm hover:underline"
                    aria-expanded={expanded}
                    aria-controls={menuId}
                    onClick={() => setOpenGroup(expanded ? null : group)}
                  >
                    {t.toolGroups[group]}
                    <span aria-hidden> ▾</span>
                  </button>
                  <ul
                    id={menuId}
                    className={`${expanded ? "flex" : "hidden"} flex-col gap-1 pb-1 pl-4 md:absolute md:left-0 md:top-full md:z-10 md:mt-1 md:min-w-max md:rounded md:border md:border-black/10 md:bg-background md:p-2 md:dark:border-white/15`}
                  >
                    {tools.map((tool) => (
                      <li key={tool.slug}>
                        <Link href={tool.href} className="block py-1 text-sm hover:underline" onClick={closeAll}>
                          {t.tools[tool.slug].name}
                        </Link>
                      </li>
                    ))}
                  </ul>
                </li>
              );
            })}
          </ul>
        </nav>
      </div>
    </header>
  );
}
