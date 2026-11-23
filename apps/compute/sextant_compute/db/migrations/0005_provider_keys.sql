-- Settings: each signed-in user's own data-provider API keys (bring your own key).
--
-- User-owned per docs/adr/0001: user_id cascades from users, so deleting an
-- account removes the user's keys. One key per (user, provider).
--
-- The key is stored encrypted (AES-256-GCM, see sextant_compute/keys/cipher.py)
-- with a secret from the PROVIDER_KEY_SECRET environment variable; the database
-- never sees the plaintext. ``hint`` is the last four characters, the only part
-- of the key ever shown again.

CREATE TABLE provider_keys (
    user_id    uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    provider   text NOT NULL CHECK (provider ~ '^[a-z][a-z0-9_]*$'),
    nonce      bytea NOT NULL,
    ciphertext bytea NOT NULL,
    hint       text NOT NULL CHECK (length(hint) <= 4),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, provider)
);
