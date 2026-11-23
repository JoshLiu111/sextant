import type { Messages } from "@/i18n";

export type Instrument = "call" | "put" | "underlying";
export type Position = "long" | "short";

/** A leg as the form keeps it: numbers as typed. */
export type LegForm = { instrument: Instrument; position: Position; quantity: string; strike: string };

export type PresetId = keyof Messages["options"]["strategy"]["presets"]["items"];

type PresetLeg = { instrument: Instrument; position: Position; strikeFactor: number };

/** Classic strategies with strikes as multiples of the spot (names and descriptions in en.ts). */
const PRESETS: Record<PresetId, readonly PresetLeg[]> = {
  bullCallSpread: [
    { instrument: "call", position: "long", strikeFactor: 0.95 },
    { instrument: "call", position: "short", strikeFactor: 1.05 },
  ],
  straddle: [
    { instrument: "call", position: "long", strikeFactor: 1 },
    { instrument: "put", position: "long", strikeFactor: 1 },
  ],
  strangle: [
    { instrument: "put", position: "long", strikeFactor: 0.9 },
    { instrument: "call", position: "long", strikeFactor: 1.1 },
  ],
  ironCondor: [
    { instrument: "put", position: "long", strikeFactor: 0.8 },
    { instrument: "put", position: "short", strikeFactor: 0.9 },
    { instrument: "call", position: "short", strikeFactor: 1.1 },
    { instrument: "call", position: "long", strikeFactor: 1.2 },
  ],
};

export const PRESET_IDS = Object.keys(PRESETS) as PresetId[];

/** The preset's legs, with strikes around ``spot`` rounded to cents. */
export function presetLegs(id: PresetId, spot: number): LegForm[] {
  return PRESETS[id].map((leg) => ({
    instrument: leg.instrument,
    position: leg.position,
    quantity: "1",
    strike: String(Math.round(spot * leg.strikeFactor * 100) / 100),
  }));
}

export const DEFAULT_PRESET: PresetId = "bullCallSpread";
