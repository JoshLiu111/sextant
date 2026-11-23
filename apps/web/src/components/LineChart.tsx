"use client";

import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";

export type ChartPoint = { x: number; y: number | null };

export type ChartSeries = {
  id: string;
  label: string;
  /** Sorted by x ascending. `y: null` leaves a gap in the line. */
  points: ChartPoint[];
  /** Any CSS color. */
  color: string;
  dashed?: boolean;
};

/** A labelled vertical reference line, e.g. the strike or a drawdown start. */
export type ChartMarker = { x: number; label: string };

type Props = {
  /** Accessible name of the chart (role="img"). */
  label: string;
  series: ChartSeries[];
  xLabel: string;
  formatX: (x: number) => string;
  formatY: (y: number) => string;
  markers?: ChartMarker[];
  height?: number;
};

const MARGIN = { top: 12, right: 16, bottom: 36, left: 56 };

/**
 * Responsive SVG line chart. Hovering (or focusing and using the arrow keys)
 * shows a tooltip with the exact value of every series at the nearest x.
 * For dates, pass x as epoch milliseconds and format it in `formatX`.
 */
export function LineChart({ label, series, xLabel, formatX, formatY, markers = [], height = 280 }: Props) {
  const wrapper = useRef<HTMLDivElement>(null);
  // Unknown until measured, so the SVG never renders wider than its container.
  const [measured, setMeasured] = useState<number | null>(null);
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  useEffect(() => {
    const el = wrapper.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => setMeasured(Math.floor(entry.contentRect.width)));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const xs = useMemo(
    () => [...new Set(series.flatMap((s) => s.points.map((p) => p.x)))].sort((a, b) => a - b),
    [series],
  );
  const ys = series.flatMap((s) => s.points.flatMap((p) => (p.y === null ? [] : [p.y])));
  if (measured === null || xs.length === 0 || ys.length === 0) {
    return <div ref={wrapper} className="w-full" style={{ height }} />;
  }
  const width = Math.max(measured, 200);

  const [x0, x1] = padDomain(xs[0], xs[xs.length - 1], 0);
  const [y0, y1] = padDomain(Math.min(...ys), Math.max(...ys), 0.05);
  const innerW = width - MARGIN.left - MARGIN.right;
  const innerH = height - MARGIN.top - MARGIN.bottom;
  const sx = (x: number) => MARGIN.left + ((x - x0) / (x1 - x0)) * innerW;
  const sy = (y: number) => MARGIN.top + (1 - (y - y0) / (y1 - y0)) * innerH;

  const hoverX = hoverIndex === null ? null : xs[Math.min(hoverIndex, xs.length - 1)];

  function onPointerMove(e: PointerEvent<SVGSVGElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * width;
    const x = x0 + ((px - MARGIN.left) / innerW) * (x1 - x0);
    setHoverIndex(nearestIndex(xs, x));
  }

  function onKeyDown(e: KeyboardEvent<SVGSVGElement>) {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    e.preventDefault();
    const step = e.key === "ArrowLeft" ? -1 : 1;
    setHoverIndex((i) => Math.min(Math.max((i ?? Math.floor(xs.length / 2)) + step, 0), xs.length - 1));
  }

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
        onPointerLeave={() => setHoverIndex(null)}
        onKeyDown={onKeyDown}
        onFocus={() => setHoverIndex((i) => i ?? Math.floor(xs.length / 2))}
        onBlur={() => setHoverIndex(null)}
      >
        <g className="text-black/40 dark:text-white/40" fontSize={11} fill="currentColor">
          {ticks(y0, y1).map((t) => (
            <g key={`y${t}`}>
              <line x1={MARGIN.left} x2={width - MARGIN.right} y1={sy(t)} y2={sy(t)} stroke="currentColor" strokeOpacity={0.25} />
              <text x={MARGIN.left - 6} y={sy(t)} textAnchor="end" dominantBaseline="middle">
                {formatY(t)}
              </text>
            </g>
          ))}
          {ticks(x0, x1, Math.max(2, Math.floor(innerW / 90))).map((t) => (
            <text key={`x${t}`} x={sx(t)} y={height - MARGIN.bottom + 16} textAnchor="middle">
              {formatX(t)}
            </text>
          ))}
          <text x={MARGIN.left + innerW / 2} y={height - 4} textAnchor="middle">
            {xLabel}
          </text>
        </g>
        {markers.map((m, i) => {
          // Stagger labels so nearby markers don't overlap; flip to the left near the right edge.
          const flip = sx(m.x) > MARGIN.left + innerW * 0.7;
          return (
            <g key={`m${m.label}${m.x}`} data-testid="chart-marker" className="text-black/50 dark:text-white/50">
              <line x1={sx(m.x)} x2={sx(m.x)} y1={MARGIN.top} y2={MARGIN.top + innerH} stroke="currentColor" strokeDasharray="2 3" />
              <text
                x={sx(m.x) + (flip ? -4 : 4)}
                y={MARGIN.top + 10 + i * 14}
                textAnchor={flip ? "end" : "start"}
                fontSize={11}
                fill="currentColor"
              >
                {m.label}
              </text>
            </g>
          );
        })}
        {series.map((s) => (
          <path
            key={s.id}
            d={linePath(s.points, sx, sy)}
            fill="none"
            stroke={s.color}
            strokeWidth={2}
            strokeDasharray={s.dashed ? "6 4" : undefined}
          />
        ))}
        {hoverX !== null && (
          <g>
            <line x1={sx(hoverX)} x2={sx(hoverX)} y1={MARGIN.top} y2={MARGIN.top + innerH} stroke="currentColor" strokeOpacity={0.4} />
            {series.map((s) => {
              const p = pointAt(s.points, hoverX);
              return p && p.y !== null ? <circle key={s.id} cx={sx(p.x)} cy={sy(p.y)} r={4} fill={s.color} /> : null;
            })}
          </g>
        )}
      </svg>
      {hoverX !== null && (
        <div
          data-testid="chart-tooltip"
          role="status"
          className="pointer-events-none absolute top-2 rounded-md border border-black/10 bg-white/95 px-3 py-2 text-xs shadow-sm dark:border-white/15 dark:bg-black/90"
          style={sx(hoverX) > width / 2 ? { right: width - sx(hoverX) + 8 } : { left: sx(hoverX) + 8 }}
        >
          <div className="font-medium">
            {xLabel}: <span className="font-mono tabular-nums">{formatX(hoverX)}</span>
          </div>
          {series.map((s) => {
            const p = pointAt(s.points, hoverX);
            return (
              <div key={s.id} className="flex items-center gap-2">
                <span aria-hidden className="inline-block h-2 w-2 rounded-full" style={{ background: s.color }} />
                {s.label}: <span className="font-mono tabular-nums">{p && p.y !== null ? formatY(p.y) : "–"}</span>
              </div>
            );
          })}
        </div>
      )}
      <ul className="mt-2 flex flex-wrap gap-4 text-xs">
        {series.map((s) => (
          <li key={s.id} className="flex items-center gap-2">
            <svg aria-hidden width={20} height={6}>
              <line x1={0} x2={20} y1={3} y2={3} stroke={s.color} strokeWidth={2} strokeDasharray={s.dashed ? "6 4" : undefined} />
            </svg>
            {s.label}
          </li>
        ))}
      </ul>
    </div>
  );
}

function padDomain(lo: number, hi: number, fraction: number): [number, number] {
  if (lo === hi) return [lo - 1, hi + 1];
  const pad = (hi - lo) * fraction;
  return [lo - pad, hi + pad];
}

function ticks(lo: number, hi: number, count = 5): number[] {
  const raw = (hi - lo) / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw;
  const out: number[] = [];
  for (let t = Math.ceil(lo / step) * step; t <= hi + step * 1e-9; t += step) out.push(Number(t.toPrecision(12)));
  return out;
}

function nearestIndex(sorted: number[], x: number): number {
  let lo = 0;
  let hi = sorted.length - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (sorted[mid] < x) lo = mid;
    else hi = mid;
  }
  return Math.abs(sorted[lo] - x) <= Math.abs(sorted[hi] - x) ? lo : hi;
}

function pointAt(points: ChartPoint[], x: number): ChartPoint | undefined {
  if (points.length === 0) return undefined;
  return points[nearestIndex(points.map((p) => p.x), x)];
}

function linePath(points: ChartPoint[], sx: (x: number) => number, sy: (y: number) => number): string {
  let d = "";
  let pen = false;
  for (const p of points) {
    if (p.y === null) {
      pen = false;
      continue;
    }
    d += `${pen ? "L" : "M"}${sx(p.x).toFixed(2)},${sy(p.y).toFixed(2)}`;
    pen = true;
  }
  return d;
}
