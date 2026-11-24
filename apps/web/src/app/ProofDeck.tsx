"use client";

import Link from "next/link";
import { useEffect, useRef, useState, useSyncExternalStore, type CSSProperties, type ReactNode } from "react";

const REDUCED = "(prefers-reduced-motion: reduce)";
const subscribeReduced = (onChange: () => void) => {
  const query = window.matchMedia(REDUCED);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
};
const noSubscription = () => () => {};
import type { ToolSlug } from "@/lib/tools";

export type DeckFrame = {
  id: string;
  tool: ToolSlug;
  href: string;
  /** The tool's full name, for the caption and the buttons' accessible names. */
  name: string;
  /** The button's visible label. */
  short: string;
  caption: string;
  /** Accessible name of the frame's button, and the caption's link text. */
  showLabel: string;
  openLabel: string;
  /** The guides' readouts: where the numbers came from, and how they were made. */
  source: string;
  note: string;
  /** Width over height of the capture. */
  ratio: number;
  picture: ReactNode;
  /** Drawn over the capture, positioned in % of it. */
  overlay?: ReactNode;
};

/**
 * The hero's deck of proofs: one screen from each tool on a printed sheet,
 * turning over every few seconds. Each sheet arrives with its own orange guides
 * naming the source and the method. The deck holds still while it is hovered,
 * focused, off screen, paused, or when the visitor prefers reduced motion; the
 * buttons beneath pick a sheet directly. Without scripting the first sheet shows.
 */
export function ProofDeck({
  frames,
  label,
  pauseLabel,
  playLabel,
  interval = 6500,
  className = "",
}: {
  frames: DeckFrame[];
  label: string;
  pauseLabel: string;
  playLabel: string;
  interval?: number;
  className?: string;
}) {
  const [active, setActive] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [held, setHeld] = useState(false);
  const [onScreen, setOnScreen] = useState(true);
  const root = useRef<HTMLElement>(null);
  // On the server (and without scripting) the deck is still and only the first sheet shows.
  const reduced = useSyncExternalStore(subscribeReduced, () => window.matchMedia(REDUCED).matches, () => false);
  const ready = useSyncExternalStore(noSubscription, () => true, () => false);

  useEffect(() => {
    const el = root.current;
    if (!el) return;
    let inView = true;
    const update = () => setOnScreen(inView && !document.hidden);
    const observer = new IntersectionObserver(([entry]) => {
      inView = entry.isIntersecting;
      update();
    });
    observer.observe(el);
    document.addEventListener("visibilitychange", update);
    return () => {
      observer.disconnect();
      document.removeEventListener("visibilitychange", update);
    };
  }, []);

  const running = playing && !held && onScreen && !reduced;
  const current = frames[active];
  const advance = () => setActive((i) => (i + 1) % frames.length);

  return (
    <figure
      ref={root}
      aria-roledescription="carousel"
      aria-label={label}
      data-js={ready || undefined}
      className={`deck min-w-0 ${className}`}
      onPointerEnter={() => setHeld(true)}
      onPointerLeave={() => setHeld(false)}
      onFocus={() => setHeld(true)}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setHeld(false);
      }}
    >
      <div className="crop relative">
        <div className="sheet deck-sheet">
          <div className="deck-stage">
            {frames.map((frame, i) => (
              <div
                key={frame.id}
                className="deck-frame"
                data-active={i === active || undefined}
                aria-hidden={i !== active}
                inert={i !== active}
              >
                <div
                  data-slot={frame.id}
                  data-kind="product"
                  className="deck-fit"
                  style={{ "--ratio": frame.ratio } as CSSProperties}
                >
                  {frame.picture}
                  {i === active && frame.overlay}
                </div>
              </div>
            ))}
          </div>
        </div>
        {/* The guides redraw with every sheet: keyed on it, so the draw-in replays. */}
        <div key={current.id} aria-hidden className="pointer-events-none absolute inset-0">
          <span className="guide guide-x" style={{ top: "-1.25rem" }} />
          <span className="guide-label" style={{ top: "-2.75rem", left: 0 }}>
            {current.source}
          </span>
          <span className="guide guide-y" style={{ left: "-1.25rem" }} />
          <span className="guide-label" style={{ bottom: "-2rem", right: 0 }}>
            {current.note}
          </span>
        </div>
      </div>

      <div className="mt-12 flex items-start gap-3">
        <div role="group" aria-label={label} className="grid min-w-0 grow grid-cols-4 gap-x-3 gap-y-1 sm:grid-cols-7">
          {frames.map((frame, i) => (
            <button
              key={frame.id}
              type="button"
              data-tool={frame.tool}
              aria-label={frame.showLabel}
              aria-current={i === active || undefined}
              className="deck-tab"
              onClick={() => setActive(i)}
            >
              <span aria-hidden className="deck-track">
                {i === active && (
                  <span
                    key={`${frame.id}-${running}`}
                    className="deck-fill"
                    data-running={running || undefined}
                    style={{ animationDuration: `${interval}ms` }}
                    onAnimationEnd={() => {
                      if (running) advance();
                    }}
                  />
                )}
              </span>
              {frame.short}
            </button>
          ))}
        </div>
        <button
          type="button"
          className="deck-toggle"
          onClick={() => setPlaying((p) => !p)}
          hidden={reduced}
        >
          {playing ? (
            <svg aria-hidden viewBox="0 0 12 12" width="12" height="12">
              <rect x="2" y="1.5" width="2.5" height="9" fill="currentColor" />
              <rect x="7.5" y="1.5" width="2.5" height="9" fill="currentColor" />
            </svg>
          ) : (
            <svg aria-hidden viewBox="0 0 12 12" width="12" height="12">
              <path d="M3 1.5 L10.5 6 L3 10.5 Z" fill="currentColor" />
            </svg>
          )}
          <span>{playing ? pauseLabel : playLabel}</span>
        </button>
      </div>

      <figcaption aria-live={running ? "off" : "polite"} className="mt-3 text-sm text-ink-2">
        <span className="font-medium text-ink">{current.name}.</span> {current.caption}{" "}
        <Link href={current.href} className="link whitespace-nowrap">
          {current.openLabel}
        </Link>
      </figcaption>
    </figure>
  );
}
