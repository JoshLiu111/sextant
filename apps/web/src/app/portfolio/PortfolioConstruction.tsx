"use client";

import { EfficientFrontier } from "./EfficientFrontier";
import { RebalancingBacktest } from "./RebalancingBacktest";

/**
 * Portfolio construction views for the demo portfolio (stories 55, 56). They take
 * the demo form's request body, so editing the holdings above re-runs both.
 */
export function PortfolioConstruction({ portfolio }: { portfolio: Record<string, unknown> }) {
  return (
    <div className="mt-4 space-y-12">
      <RebalancingBacktest portfolio={portfolio} />
      <EfficientFrontier portfolio={portfolio} />
    </div>
  );
}
