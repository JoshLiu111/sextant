-- Valuation Calculator (P2): signed-in users' named sets of DCF/WACC assumptions per ticker.
--
-- User-owned per docs/adr/0001: user_id cascades from users, so deleting an
-- account removes the user's saved assumptions. One set per (user, ticker, name);
-- saving under an existing name replaces it. ``assumptions`` is the JSON of
-- valuation.api.ValuationAssumptions (rates as decimals, null = derive).

CREATE TABLE valuation_assumptions (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    ticker      text NOT NULL CHECK (length(ticker) BETWEEN 1 AND 20),
    name        text NOT NULL CHECK (length(name) BETWEEN 1 AND 100),
    assumptions jsonb NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, ticker, name)
);
