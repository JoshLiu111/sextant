"use client";

import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";

/** One bar: `x` is the bin center, `width` the bin width, `count` the observations in it. */
export type HistogramBin = { x: number; count: number };

type Props = {
  /** Accessible name of the chart (role="img"). */
  label: string;
  bins: HistogramBin[];
  binWidth: number;
  xLabel: string;
  formatX: (x: number) => string;
  /** Tooltip line for a bar's count, e.g. "12 daily returns". */
  formatCount: (count: number) => string;
  color?: string;
  height?: number;
};

const MARGIN = { top: 12, right: 16, bottom: 36, left: 44 };

/**
 * Responsive SVG histogram. Hovering (or focusing and using the arrow keys)
 * shows the bin's range and count.
 */
export function Histogram({ label, bins, binWidth, xLabel, formatX, formatCount, color = "#2563eb", height = 240 }: Props) {
  const wrapper = useRef<HTMLDivElement>(null);
  const [measured, setMeasured] = useState<number | null>(null);
  const [hover, setHover] = useState<number | null>(null);

  useEffect(() => {
    const el = wrapper.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => setMeasured(Math.floor(entry.contentRect.width)));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  if (measured === null || bins.length === 0) {
    return <div ref={wrapper} className="w-full" style={{ height }} />;
  }
  const width = Math.max(measured, 200);
  const innerW = width - MARGIN.left - MARGIN.right;
  const innerH = height - MARGIN.top - MARGIN.bottom;
  const x0 = bins[0].x - binWidth / 2;
  const x1 = bins[bins.length - 1].x + binWidth / 2;
  const maxCount = Math.max(...bins.map((b) => b.count), 1);
  const sx = (x: number) => MARGIN.left + ((x - x0) / (x1 - x0 || 1)) * innerW;
  const sy = (c: number) => MARGIN.top + (1 - c / maxCount) * innerH;
  const barW = Math.max(innerW / bins.length - 1, 1);

  function onPointerMove(e: PointerEvent<SVGSVGElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * width;
    const i = Math.floor(((px - MARGIN.left) / innerW) * bins.length);
    setHover(Math.min(Math.max(i, 0), bins.length - 1));
  }

  function onKeyDown(e: KeyboardEvent<SVGSVGElement>) {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    e.preventDefault();
    const step = e.key === "ArrowLeft" ? -1 : 1;
    setHover((i) => Math.min(Math.max((i ?? Math.floor(bins.length / 2)) + step, 0), bins.length - 1));
  }

  const xTicks = [x0, (x0 + x1) / 2, x1];
  const hovered = hover === null ? null : bins[hover];

  return (
    <div ref={wrapper} className="relative w-full">
      <svg
        role="img"
        aria-label={label}
        tabIndex={0}
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        className="block touch-none select-none outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
        onPointerMove={onPointerMove}
        onPointerDown={onPointerMove}
        onPointerLeave={() => setHover(null)}
        onKeyDown={onKeyDown}
        onFocus={() => setHover((i) => i ?? Math.floor(bins.length / 2))}
        onBlur={() => setHover(null)}
      >
        <g className="text-black/40 dark:text-white/40" fontSize={11} fill="currentColor">
          {[0, Math.round(maxCount / 2), maxCount].map((c) => (
            <g key={`y${c}`}>
              <line x1={MARGIN.left} x2={width - MARGIN.right} y1={sy(c)} y2={sy(c)} stroke="currentColor" strokeOpacity={0.25} />
              <text x={MARGIN.left - 6} y={sy(c)} textAnchor="end" dominantBaseline="middle">
                {c}
              </text>
            </g>
          ))}
          {xTicks.map((t, i) => (
            <text key={`x${i}`} x={sx(t)} y={height - MARGIN.bottom + 16} textAnchor={i === 0 ? "start" : i === 2 ? "end" : "middle"}>
              {formatX(t)}
            </text>
          ))}
          <text x={MARGIN.left + innerW / 2} y={height - 4} textAnchor="middle">
            {xLabel}
          </text>
        </g>
        {bins.map((b, i) => (
          <rect
            key={b.x}
            data-testid="histogram-bar"
            x={sx(b.x - binWidth / 2) + 0.5}
            width={barW}
            y={sy(b.count)}
            height={MARGIN.top + innerH - sy(b.count)}
            fill={color}
            fillOpacity={hover === i ? 0.9 : 0.6}
          />
        ))}
      </svg>
      {hovered && (
        <div
          data-testid="chart-tooltip"
          role="status"
          className="pointer-events-none absolute top-2 rounded-md border border-black/10 bg-white/95 px-3 py-2 text-xs shadow-sm dark:border-white/15 dark:bg-black/90"
          style={sx(hovered.x) > width / 2 ? { right: width - sx(hovered.x) + 8 } : { left: sx(hovered.x) + 8 }}
        >
          <div className="font-medium">
            {xLabel}:{" "}
            <span className="font-mono tabular-nums">
              {formatX(hovered.x - binWidth / 2)} – {formatX(hovered.x + binWidth / 2)}
            </span>
          </div>
          <div className="font-mono tabular-nums">{formatCount(hovered.count)}</div>
        </div>
      )}
    </div>
  );
}
