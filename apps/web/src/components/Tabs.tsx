"use client";

import { useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { useUrlInputs, type UrlCodec } from "@/lib/urlInputs";

/** Each tab's own query params, used to pick the tab for a link without `?tab=`. */
export type TabParams<Id extends string> = Partial<Record<Id, readonly string[]>>;

/**
 * The open tab of a tool page, kept in the query string (`?tab=strategy`) so a
 * shared link opens the same tab. Writing the tab keeps every other param, so a
 * tool's own inputs and its tab share the URL. Uses `useSearchParams` (via
 * `useUrlInputs`), so render the caller inside `<Suspense>`.
 *
 * Which tab opens: an explicit `?tab=` wins (an unknown one opens the first
 * tab). Without one, as in links shared before the page had tabs, the first
 * tab (in `ids` order) whose own params (`inferFrom`) are in the URL opens, so
 * `/screener?filings_ticker=AAPL` opens Filings. Otherwise the first tab opens.
 *
 * `ids` and `inferFrom` should be module-level constants
 * (`const TABS = ["overview", "checks"] as const`).
 */
export function useUrlTab<const Id extends string>(
  ids: readonly [Id, ...Id[]],
  { param = "tab", inferFrom }: { param?: string; inferFrom?: TabParams<Id> } = {},
): [Id, (id: Id) => void] {
  const codec = useMemo<UrlCodec<{ tab: Id }>>(
    () => ({
      keys: [param],
      read: (params) => {
        const raw = params.get(param);
        if (raw !== null) return { tab: ids.find((id) => id === raw) ?? ids[0] };
        const inferred = ids.find((id) => inferFrom?.[id]?.some((key) => params.has(key)));
        return { tab: inferred ?? ids[0] };
      },
      write: ({ tab }) => ({ [param]: tab }),
    }),
    [ids, param, inferFrom],
  );
  const { initial, share } = useUrlInputs(codec);
  const [tab, setTabState] = useState<Id>(initial.tab);
  const setTab = (id: Id) => {
    setTabState(id);
    share({ tab: id });
  };
  return [tab, setTab];
}

/** Where each key moves the selection, given the open tab's index and the tab count. */
const KEY_MOVES: Record<string, (index: number, count: number) => number> = {
  ArrowRight: (index, count) => (index + 1) % count,
  ArrowLeft: (index, count) => (index - 1 + count) % count,
  Home: () => 0,
  End: (_, count) => count - 1,
};

/**
 * An accessible tablist with one panel: the open tab's. Only the open panel is
 * mounted, so only it fetches. Arrow keys, Home and End move between tabs (and
 * open them); only the open tab is in the Tab order. Spacing is the caller's
 * (`className`).
 *
 * Element ids are `${idPrefix}-tab-${id}` and `${idPrefix}-panel-${id}`.
 * Pair with `useUrlTab` for URL-backed state:
 *
 *   const [tab, setTab] = useUrlTab(TABS);
 *   <Tabs idPrefix="risk" label="Risk results" tabs={TABS} labels={t.tabs} active={tab} onChange={setTab}>
 *     {tab === "overview" && <Overview />}
 *   </Tabs>
 */
export function Tabs<Id extends string>({
  idPrefix,
  label,
  tabs,
  labels,
  active,
  onChange,
  children,
  className,
}: {
  idPrefix: string;
  /** The tablist's accessible name. */
  label: string;
  /** The tab ids, in display order. */
  tabs: readonly Id[];
  /** Each tab's visible label (extra keys, such as an i18n `label`, are ignored). */
  labels: Readonly<Record<Id, string>>;
  active: Id;
  onChange: (id: Id) => void;
  /** The open tab's content. */
  children: ReactNode;
  className?: string;
}) {
  const buttons = useRef(new Map<Id, HTMLButtonElement>());

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    const move = KEY_MOVES[e.key];
    if (!move) return;
    e.preventDefault();
    const id = tabs[move(tabs.indexOf(active), tabs.length)];
    onChange(id);
    buttons.current.get(id)?.focus();
  }

  return (
    <div className={className}>
      <div
        role="tablist"
        aria-label={label}
        onKeyDown={onKeyDown}
        className="flex flex-wrap gap-1 border-b border-black/10 dark:border-white/15"
      >
        {tabs.map((id) => (
          <button
            key={id}
            ref={(el) => {
              if (el) buttons.current.set(id, el);
              else buttons.current.delete(id);
            }}
            id={`${idPrefix}-tab-${id}`}
            role="tab"
            type="button"
            aria-selected={active === id}
            aria-controls={`${idPrefix}-panel-${id}`}
            tabIndex={active === id ? 0 : -1}
            onClick={() => onChange(id)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium ${
              active === id
                ? "border-black dark:border-white"
                : "border-transparent text-black/60 hover:text-black dark:text-white/60 dark:hover:text-white"
            }`}
          >
            {labels[id]}
          </button>
        ))}
      </div>
      <div id={`${idPrefix}-panel-${active}`} role="tabpanel" aria-labelledby={`${idPrefix}-tab-${active}`}>
        {children}
      </div>
    </div>
  );
}
