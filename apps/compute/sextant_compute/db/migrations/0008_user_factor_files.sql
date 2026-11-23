-- Factor files a user uploaded for factor regressions on My data (ADR 0003):
-- Sextant ships no real factor data, so a user brings their own (e.g. a
-- Kenneth R. French Data Library CSV). Shown only to that user; never in the
-- shared cache.
--
-- User-owned per docs/adr/0001: user_id cascades from users, so deleting an
-- account removes the user's factor files.
--
-- One file per ``kind``: ``three_factor`` (Mkt-RF, SMB, HML, RF) and
-- ``momentum`` (MOM). ``factors`` is the parsed table in decimals:
-- {"dates": ["2024-01-31", ...], "order": ["Mkt-RF", ...],
--  "columns": {"Mkt-RF": [0.0123, null, ...], ...}}.
-- Monthly dates are month ends.

CREATE TABLE user_factor_files (
    user_id     uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    kind        text NOT NULL CHECK (kind IN ('three_factor', 'momentum')),
    filename    text NOT NULL,
    frequency   text NOT NULL CHECK (frequency IN ('daily', 'monthly')),
    factors     jsonb NOT NULL,
    uploaded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, kind)
);
