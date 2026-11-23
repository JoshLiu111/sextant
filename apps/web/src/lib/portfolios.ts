// Browser client for saved portfolios (`/api/compute/portfolios`). The session
// cookie goes along automatically (same origin). Mirrors
// apps/compute/sextant_compute/portfolio/saved.py.

import { send as sendJson, type Outcome } from "./computeClient";

export type SavedHolding = { ticker: string; quantity: number; cost_price: number; currency: string };

export type PortfolioSummary = { id: string; name: string; created_at: string; updated_at: string };

export type SavedPortfolio = PortfolioSummary & { holdings: SavedHolding[] };

/** What create and update send. Numbers are null when the input is empty or not a number, so the API reports the field. */
export type PortfolioBody = {
  name: string;
  holdings: { ticker: string; quantity: number | null; cost_price: number | null; currency: string }[];
};

export type PortfolioOutcome<T> = Outcome<T>;

/** `suffix` follows `/portfolios`: "" for the collection, `/<id>` for one portfolio. */
function send<T>(method: string, suffix: "" | `/${string}`, body?: unknown): Promise<PortfolioOutcome<T>> {
  return sendJson<T>(method, `/portfolios${suffix}`, body);
}

// Transactions imported from CSV (apps/compute/sextant_compute/portfolio/imports.py).

export const IMPORT_FIELDS = ["date", "ticker", "side", "quantity", "price", "fees", "currency"] as const;
export type ImportField = (typeof IMPORT_FIELDS)[number];
export const REQUIRED_IMPORT_FIELDS: readonly ImportField[] = ["date", "ticker", "side", "quantity", "price"];

export type ColumnMapping = Record<ImportField, string | null>;

export type ImportedTransaction = {
  line: number;
  date: string;
  ticker: string;
  side: "buy" | "sell";
  quantity: number;
  price: number;
  fees: number;
  currency: string;
};

export type ImportRowError = { line: number; field: ImportField | null; message: string };

export type ImportPreview = {
  columns: string[];
  sample: { line: number; cells: string[] }[];
  row_count: number;
  mapping: ColumnMapping;
  missing_fields: ImportField[];
  transactions: ImportedTransaction[];
  errors: ImportRowError[];
  holdings_after: SavedHolding[] | null;
};

export type ImportResult = { import_id: string; imported: number; errors: ImportRowError[]; portfolio: SavedPortfolio };

/** `mapping` omitted: the API guesses it from the header row. */
export type ImportBody = { csv: string; mapping?: ColumnMapping };

export const portfoliosApi = {
  previewImport: (id: string, body: ImportBody) => send<ImportPreview>("POST", `/${id}/transactions/preview`, body),
  importTransactions: (id: string, body: ImportBody) => send<ImportResult>("POST", `/${id}/transactions`, body),
  list: () => send<PortfolioSummary[]>("GET", ""),
  get: (id: string) => send<SavedPortfolio>("GET", `/${id}`),
  create: (body: PortfolioBody) => send<SavedPortfolio>("POST", "", body),
  update: (id: string, body: PortfolioBody) => send<SavedPortfolio>("PUT", `/${id}`, body),
  remove: (id: string) => send<void>("DELETE", `/${id}`),
};
