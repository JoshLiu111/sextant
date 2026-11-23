-- My Portfolio (P4): transactions imported from CSV into a saved portfolio.
--
-- User-owned per docs/adr/0001: portfolio_transactions cascades from portfolios,
-- which cascades from users, so deleting a portfolio or an account removes them.
-- The holdings stay the source of truth for what is held now; these rows are
-- the history an import applied to them.

CREATE TABLE portfolio_transactions (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    portfolio_id uuid NOT NULL REFERENCES portfolios (id) ON DELETE CASCADE,
    import_id    uuid NOT NULL,
    line         integer NOT NULL CHECK (line >= 1),
    trade_date   date NOT NULL,
    ticker       text NOT NULL CHECK (ticker <> ''),
    side         text NOT NULL CHECK (side IN ('buy', 'sell')),
    quantity     numeric NOT NULL CHECK (quantity > 0),
    price        numeric NOT NULL CHECK (price >= 0),
    fees         numeric NOT NULL DEFAULT 0 CHECK (fees >= 0),
    currency     text NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
    imported_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX portfolio_transactions_portfolio_idx ON portfolio_transactions (portfolio_id, trade_date, id);
