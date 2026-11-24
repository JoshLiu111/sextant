"use client";

import { useState } from "react";
import { getMessages } from "@/i18n";

export type TapeItem = {
  key: string;
  label: string;
  /** The reading, formatted with its unit. */
  value: string;
  /** Latest minus previous reading, in the reading's own unit; null when the card has no history. */
  change: number | null;
  /** Where the card sits on /macro. */
  href: string;
};

const SIGNED = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2, signDisplay: "exceptZero" });

function Item({ item, copy }: { item: TapeItem; copy?: boolean }) {
  const t = getMessages().home.tape;
  const change = item.change === null ? null : SIGNED.format(item.change).replace("-", "−");
  const direction = item.change === null || item.change === 0 ? "flat" : item.change > 0 ? "up" : "down";
  return (
    <li className="tape-item">
      <a href={item.href} tabIndex={copy ? -1 : undefined} className="tape-link">
        <span className="tape-label">{item.label}</span>
        <span className="tape-value">{item.value}</span>
        {change !== null && (
          <span className="tape-change" data-direction={direction}>
            <span aria-hidden>{change}</span>
            <span className="sr-only">{t.changeLabel(change)}</span>
          </span>
        )}
      </a>
    </li>
  );
}

/**
 * The readings drift right to left in a loop (two copies, the second hidden from
 * assistive tech); hovering or focusing the band, or the Pause button, holds it.
 * Under reduced motion it stands still and scrolls by hand.
 */
export function TapeTrack({ items }: { items: TapeItem[] }) {
  const t = getMessages().home.tape;
  const [paused, setPaused] = useState(false);
  return (
    <section aria-label={t.label} className="tape" data-paused={paused || undefined}>
      <div className="mx-auto flex max-w-7xl items-stretch px-4 md:px-6">
        <button
          type="button"
          onClick={() => setPaused((p) => !p)}
          aria-pressed={paused}
          aria-label={paused ? t.play : t.pause}
          className="tape-toggle"
        >
          <svg aria-hidden viewBox="0 0 12 12" width="12" height="12">
            {paused ? <path d="M3 1.5v9l7-4.5z" fill="currentColor" /> : <path d="M2.5 1.5h2.5v9H2.5zM7 1.5h2.5v9H7z" fill="currentColor" />}
          </svg>
        </button>
        <div className="tape-window">
          <div className="tape-run" style={{ ["--tape-items" as string]: items.length }}>
            <ul className="tape-list">
              {items.map((item) => (
                <Item key={item.key} item={item} />
              ))}
            </ul>
            <ul className="tape-list tape-copy" aria-hidden>
              {items.map((item) => (
                <Item key={item.key} item={item} copy />
              ))}
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
}
