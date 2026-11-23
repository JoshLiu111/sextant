// CSV export of a result table (story 9). Pages describe the table they show as a
// `CsvTable`; `ExportCsvButton` turns it into a file. Values are the underlying
// numbers from the envelope, never the formatted strings on screen.

import type { MetricResult } from "./envelope";

/**
 * One cell. A `MetricResult` exports its value only when its status is ok, so a
 * missing_data or error metric is an empty cell. null/undefined are empty too.
 */
export type CsvValue = string | number | null | undefined | MetricResult;

export type CsvTable = {
  /** Header row: the column labels as shown. */
  columns: string[];
  rows: CsvValue[][];
};

/** Leading column added to every row of a table built from synthetic data. */
export const DEMO_COLUMN = "Data";
export const DEMO_VALUE = "Synthetic demo data";

function cellText(value: CsvValue): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "object") return value.status === "ok" && value.value !== null ? String(value.value) : "";
  if (typeof value === "number") return Number.isFinite(value) ? String(value) : "";
  return value;
}

function quote(text: string): string {
  return /[",\r\n]/.test(text) || /^\s|\s$/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

/** RFC 4180 text (CRLF rows). With `demo`, every row starts with a "Synthetic demo data" column. */
export function toCsv(table: CsvTable, { demo = false }: { demo?: boolean } = {}): string {
  const header = demo ? [DEMO_COLUMN, ...table.columns] : table.columns;
  const rows = table.rows.map((r) => (demo ? [DEMO_VALUE, ...r.map(cellText)] : r.map(cellText)));
  return [header, ...rows].map((r) => r.map(quote).join(",")).join("\r\n") + "\r\n";
}

/** "sextant-<tool>-<table>-<input>.csv", with anything unsafe in a file name replaced. */
export function csvFilename(tool: string, table: string, input?: string): string {
  const slug = (s: string) =>
    s
      .trim()
      .replace(/[^A-Za-z0-9.-]+/g, "_")
      .replace(/^_+|_+$/g, "");
  const kebab = (s: string) => slug(s.toLowerCase().replace(/\s+/g, "-"));
  return ["sextant", kebab(tool), kebab(table), input ? slug(input) : ""].filter(Boolean).join("-") + ".csv";
}
