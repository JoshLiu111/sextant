-- The per-user data cache: responses fetched with a user's own provider key
-- (Tiingo, later FMP). Provider terms allow showing that data only to the key
-- holder, so it never goes to the shared cache (see data/service.py).
--
-- User-owned per docs/adr/0001: user_id cascades from users, so deleting an
-- account removes the user's cached data. Deleting a provider key removes the
-- user's rows for that ``source`` (keys/api.py).
--
-- ``cache_key`` is DataService's whole-request key and already contains
-- ``user:<user_id>``; ``value`` is the JSON-encoded response.

CREATE TABLE user_data_cache (
    cache_key  text PRIMARY KEY,
    user_id    uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    source     text NOT NULL,
    value      jsonb NOT NULL,
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX user_data_cache_user_source ON user_data_cache (user_id, source);
