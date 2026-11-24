"use client";

import { useEffect, useRef, useState } from "react";
import { REFERENCE } from "@/lib/chartColors";

export type FrontierPoint = { x: number; y: number };
export type MarkedPortfolio = { id: string; label: string; point: FrontierPoint; color: string };

const MARGIN = { top: 16, right: 24, bottom: 40, left: 56 };

/**
 * Risk/return scatter: the frontier as a line from the minimum-variance end, and
 * labelled dots for marked portfolios (max Sharpe, min variance, current).
 * Each dot is `[data-frontier-point=<id>]` with its exact values in a `<title>`.
 */
export function FrontierChart({
  label,
  frontier,
  frontierLabel,
  marked,
  xLabel,
  yLabel,
  format,
  height = 300,
}: {
  label: string;
  frontier: FrontierPoint[];
  frontierLabel: string;
  marked: MarkedPortfolio[];
  xLabel: string;
  yLabel: string;
  format: (value: number) => string;
  height?: number;
}) {
  const wrapper = useRef<HTMLDivElement>(null);
  const [measured, setMeasured] = useState<number | null>(null);

  useEffect(() => {
    const el = wrapper.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => setMeasured(Math.floor(entry.contentRect.width)));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const all = [...frontier, ...marked.map((m) => m.point)];
  if (measured === null || all.length === 0) return <div ref={wrapper} className="w-full" style={{ height }} />;
  const width = Math.max(measured, 200);
  // Volatility axis from 0, so distances read as risk.
  const x0 = 0;
  const x1 = Math.max(...all.map((p) => p.x)) * 1.08 || 0.01;
  const [y0, y1] = pad(Math.min(...all.map((p) => p.y)), Math.max(...all.map((p) => p.y)));
  const innerW = width - MARGIN.left - MARGIN.right;
  const innerH = height - MARGIN.top - MARGIN.bottom;
  const sx = (x: number) => MARGIN.left + ((x - x0) / (x1 - x0)) * innerW;
  const sy = (y: number) => MARGIN.top + (1 - (y - y0) / (y1 - y0)) * innerH;
  const path = frontier.map((p, i) => `${i ? "L" : "M"}${sx(p.x).toFixed(2)},${sy(p.y).toFixed(2)}`).join("");

  return (
    <div ref={wrapper} className="w-full">
      <svg role="img" aria-label={label} width={width} height={height} viewBox={`0 0 ${width} ${height}`} className="block">
        <g className="text-muted" fontSize={12} fill="currentColor">
          {ticks(y0, y1).map((t) => (
            <g key={`y${t}`}>
              <line x1={MARGIN.left} x2={width - MARGIN.right} y1={sy(t)} y2={sy(t)} className="stroke-rule" />
              <text x={MARGIN.left - 6} y={sy(t)} textAnchor="end" dominantBaseline="middle">
                {format(t)}
              </text>
            </g>
          ))}
          {ticks(x0, x1, Math.max(2, Math.floor(innerW / 90))).map((t) => (
            <text key={`x${t}`} x={sx(t)} y={height - MARGIN.bottom + 16} textAnchor="middle">
              {format(t)}
            </text>
          ))}
          <text x={MARGIN.left + innerW / 2} y={height - 4} textAnchor="middle">
            {xLabel}
          </text>
          <text transform={`translate(12 ${MARGIN.top + innerH / 2}) rotate(-90)`} textAnchor="middle">
            {yLabel}
          </text>
        </g>
        <path d={path} fill="none" style={{ stroke: REFERENCE }} strokeWidth={2} />
        {marked.map((m, i) => {
          const flip = sx(m.point.x) > MARGIN.left + innerW * 0.7;
          return (
            <g key={m.id} data-frontier-point={m.id}>
              <circle cx={sx(m.point.x)} cy={sy(m.point.y)} r={6} style={{ fill: m.color }} className="stroke-paper-hi" strokeWidth={1.5}>
                <title>{`${m.label}: ${yLabel} ${format(m.point.y)}, ${xLabel} ${format(m.point.x)}`}</title>
              </circle>
              <text
                x={sx(m.point.x) + (flip ? -10 : 10)}
                y={sy(m.point.y) + (i - 1) * 4 + 4}
                textAnchor={flip ? "end" : "start"}
                fontSize={12}
                className="fill-ink-2"
              >
                {m.label}
              </text>
            </g>
          );
        })}
      </svg>
      <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-ink-2">
        <li className="flex items-center gap-2">
          <svg aria-hidden width={20} height={6}>
            <line x1={0} x2={20} y1={3} y2={3} style={{ stroke: REFERENCE }} strokeWidth={2} />
          </svg>
          {frontierLabel}
        </li>
        {marked.map((m) => (
          <li key={m.id} className="flex items-center gap-2">
            <span aria-hidden className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: m.color }} />
            {m.label}
          </li>
        ))}
      </ul>
    </div>
  );
}

function pad(lo: number, hi: number): [number, number] {
  if (lo === hi) return [lo - 0.01, hi + 0.01];
  const p = (hi - lo) * 0.08;
  return [lo - p, hi + p];
}

function ticks(lo: number, hi: number, count = 5): number[] {
  const raw = (hi - lo) / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw;
  const out: number[] = [];
  for (let t = Math.ceil(lo / step) * step; t <= hi + step * 1e-9; t += step) out.push(Number(t.toPrecision(12)));
  return out;
}
