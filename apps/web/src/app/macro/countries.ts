// Economies the cross-country comparison offers. Must match COUNTRIES in
// apps/compute/sextant_compute/macro/world.py (World Bank ISO3 codes; EMU is the
// euro area aggregate). Names live in en.ts under macro.countries.names.
export const COUNTRIES = [
  "USA", "DEU", "JPN", "GBR", "FRA", "ITA", "CAN", "ESP", "EMU",
  "CHN", "IND", "KOR", "AUS", "BRA", "MEX", "ARG", "ZAF",
] as const; // prettier-ignore
export type CountryCode = (typeof COUNTRIES)[number];

export const DEFAULT_COUNTRIES: CountryCode[] = ["USA", "DEU", "JPN", "GBR"];
export const MAX_COUNTRIES = 6;

function isCountry(code: string): code is CountryCode {
  return (COUNTRIES as readonly string[]).includes(code);
}

/** `?countries=USA,DEU` -> known codes in the given order, deduplicated, at most 6; defaults if none. */
export function parseCountries(param: string | string[] | undefined): CountryCode[] {
  const raw = Array.isArray(param) ? param.join(",") : (param ?? "");
  const codes = [...new Set(raw.split(",").map((c) => c.trim().toUpperCase()))].filter(isCountry);
  return codes.length > 0 ? codes.slice(0, MAX_COUNTRIES) : DEFAULT_COUNTRIES;
}
