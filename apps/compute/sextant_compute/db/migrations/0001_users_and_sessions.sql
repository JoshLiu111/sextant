-- Accounts and sessions.
--
-- Convention for every user-owned table (see docs/adr/0001):
--   user_id uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE
-- and child tables of a user-owned table reference their parent with
-- ON DELETE CASCADE too. Deleting a users row then removes everything.
-- tests/test_user_owned_cascade.py enforces this for every table.

CREATE TABLE users (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    google_sub    text NOT NULL UNIQUE,
    email         text NOT NULL,
    name          text,
    created_at    timestamptz NOT NULL DEFAULT now(),
    last_login_at timestamptz NOT NULL DEFAULT now()
);

-- Opaque session tokens live only in the browser cookie; we store a SHA-256.
CREATE TABLE sessions (
    token_hash bytea PRIMARY KEY,
    user_id    uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL
);

CREATE INDEX sessions_user_id_idx ON sessions (user_id);
