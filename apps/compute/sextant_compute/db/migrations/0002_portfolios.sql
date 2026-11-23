-- My Portfolio (P4): saved portfolios of manually entered holdings.
--
-- User-owned per docs/adr/0001: portfolios.user_id cascades from users, and
-- portfolio_holdings cascades from portfolios, so deleting an account removes both.

CREATE TABLE portfolios (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    name       text NOT NULL CHECK (length(name) BETWEEN 1 AND 100),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX portfolios_user_id_idx ON portfolios (user_id, created_at);

-- One row per holding; position keeps the order the user entered them in.
CREATE TABLE portfolio_holdings (
    portfolio_id uuid NOT NULL REFERENCES portfolios (id) ON DELETE CASCADE,
    position     integer NOT NULL CHECK (position >= 0),
    ticker       text NOT NULL,
    quantity     numeric NOT NULL CHECK (quantity > 0),
    cost_price   numeric NOT NULL CHECK (cost_price >= 0),
    currency     text NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
    PRIMARY KEY (portfolio_id, position),
    UNIQUE (portfolio_id, ticker)
);
