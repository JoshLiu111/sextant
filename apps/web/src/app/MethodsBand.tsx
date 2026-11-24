"use client";

import { useState } from "react";
import type { ToolSlug } from "@/lib/tools";

export type MethodRun = { tool: ToolSlug; name: string; methods: readonly string[] };

/**
 * The methods every tool computes, drifting past in two rows that run in
 * opposite directions, like a tape. One button holds them still; under reduced
 * motion they sit still and wrap. The second copy of each row exists only to
 * close the loop, so it is hidden from assistive technology.
 */
export function MethodsBand({
  heading,
  rows,
  pauseLabel,
  playLabel,
}: {
  heading: string;
  rows: MethodRun[][];
  pauseLabel: string;
  playLabel: string;
}) {
  const [paused, setPaused] = useState(false);
  // One flat run of items per row: each tool's name, then its methods.
  const run = (row: MethodRun[], copy: boolean) =>
    row.flatMap((group) => [
      <li key={`${group.tool}${copy ? "-copy" : ""}`} data-tool={group.tool} className="tape-tool">
        <span className="tape-tag">{group.name}</span>
      </li>,
      ...group.methods.map((m) => (
        <li key={`${group.tool}-${m}${copy ? "-copy" : ""}`} className="tape-method">
          {m}
        </li>
      )),
    ]);

  return (
    <section aria-labelledby="methods-heading" className="tape-band" data-paused={paused || undefined}>
      <div className="mx-auto flex max-w-7xl items-end justify-between gap-6 px-4 md:px-6">
        <h2 id="methods-heading" className="text-ink">
          {heading}
        </h2>
        <button type="button" className="deck-toggle tape-toggle" onClick={() => setPaused((p) => !p)}>
          {paused ? (
            <svg aria-hidden viewBox="0 0 12 12" width="12" height="12">
              <path d="M3 1.5 L10.5 6 L3 10.5 Z" fill="currentColor" />
            </svg>
          ) : (
            <svg aria-hidden viewBox="0 0 12 12" width="12" height="12">
              <rect x="2" y="1.5" width="2.5" height="9" fill="currentColor" />
              <rect x="7.5" y="1.5" width="2.5" height="9" fill="currentColor" />
            </svg>
          )}
          <span>{paused ? playLabel : pauseLabel}</span>
        </button>
      </div>
      <div className="mx-auto mt-10 flex max-w-7xl flex-col gap-5 md:px-6">
        {rows.map((row, i) => (
          <div key={i} className="tape" data-reverse={i % 2 === 1 || undefined}>
            <div className="tape-track">
              <ul className="tape-list">{run(row, false)}</ul>
              <ul aria-hidden className="tape-list tape-copy">
                {run(row, true)}
              </ul>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
