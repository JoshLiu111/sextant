"use client";

import { useState, type ReactNode } from "react";
import { getMessages } from "@/i18n";
import { TOOL_GROUPS } from "@/lib/tools";
import { FEATURE_BOARDS } from "./featureBoardData";

const HUES = 8; // --color-chart-1 to -8, the tint palette

/**
 * Nine tints for a 3 x 3 board: the eight chart hues in random order, the ninth a
 * hue that neither of its neighbours (cells 5 and 7) wears.
 */
function dealTints(random: () => number = Math.random): number[] {
  const hues = Array.from({ length: HUES }, (_, i) => i + 1);
  for (let i = hues.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1));
    [hues[i], hues[j]] = [hues[j], hues[i]];
  }
  const free = hues.filter((h) => h !== hues[5] && h !== hues[7]);
  return [...hues, free[Math.floor(random() * free.length)]];
}

// The first board's tints come from a fixed seed so the server and the first client
// render agree; every board after it is dealt fresh as it slides in.
function seeded(seed: number) {
  return () => ((seed = (seed * 16807) % 2147483647) - 1) / 2147483646;
}
const FIRST_TINTS = dealTints(seeded(20261124));

/**
 * The hero's boards: one tool group at a time, its nine features as a 3 x 3 grid
 * of links, each cell on its own pale tint. The orange line under the open group
 * fills over a few seconds and, when it ends, the next group opens: the open board
 * slides out to the left as the next slides in from the right. Whatever holds the
 * line (hover, focus, the Pause button, reduced motion, which never starts it)
 * holds the boards. With scripting off the first board stands, every link working.
 */
export function FeatureBoards({ backdrop }: { backdrop?: ReactNode }) {
  const t = getMessages();
  const copy = t.home.boards;
  const [board, setBoard] = useState({ open: 0, tints: FIRST_TINTS });
  // The board on its way out, kept until its slide ends.
  const [leaving, setLeaving] = useState<typeof board | null>(null);
  const [paused, setPaused] = useState(false);
  const group = TOOL_GROUPS[board.open];

  const go = (next: number) => {
    if (next === board.open) return;
    setLeaving(board);
    setBoard({ open: next, tints: dealTints() });
  };

  const grid = (b: typeof board, out: boolean) => {
    const g = TOOL_GROUPS[b.open];
    return (
      <ul
        key={`${g}-${out ? "out" : "in"}`}
        className={`board-grid ${out ? "board-leave" : leaving ? "board-enter" : ""}`}
        aria-hidden={out || undefined}
        inert={out || undefined}
        onAnimationEnd={out ? (e) => e.target === e.currentTarget && setLeaving(null) : undefined}
      >
        {FEATURE_BOARDS[g].map((feature, i) => (
          <li key={feature.href} className="min-w-0">
            {/* A full navigation, as the "Try this" links: the tool reads its URL inputs on load. */}
            <a href={feature.href} data-tool={feature.tool} data-tint={b.tints[i]} className="board-cell">
              <span aria-hidden className="tool-rule" />
              <span className="board-tool">{t.tools[feature.tool].name}</span>
              <span className="board-label">{feature.label}</span>
            </a>
          </li>
        ))}
      </ul>
    );
  };

  return (
    <section aria-label={copy.label} className="boards" data-paused={paused || undefined}>
      <div className="flex items-end justify-between gap-4 border-b border-rule">
        <div className="flex flex-wrap gap-x-5">
          {TOOL_GROUPS.map((g, i) => (
            <button
              key={g}
              type="button"
              aria-pressed={i === board.open}
              aria-label={copy.show(t.toolGroups[g])}
              onClick={() => go(i)}
              className="board-tab"
            >
              {t.toolGroups[g]}
              {i === board.open && (
                <span
                  aria-hidden
                  className="board-progress"
                  key={g}
                  onAnimationEnd={() => go((board.open + 1) % TOOL_GROUPS.length)}
                />
              )}
            </button>
          ))}
        </div>
        <button type="button" aria-pressed={paused} onClick={() => setPaused((p) => !p)} className="board-pause">
          {paused ? copy.play : copy.pause}
        </button>
      </div>

      <div className="relative mt-4">
        {backdrop && (
          <div aria-hidden className="board-backdrop">
            {backdrop}
          </div>
        )}
        <div className="board-stage" data-group={group}>
          {leaving && grid(leaving, true)}
          {grid(board, false)}
        </div>
      </div>
    </section>
  );
}
