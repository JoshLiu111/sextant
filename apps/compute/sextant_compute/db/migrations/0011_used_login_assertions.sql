-- Login assertions are single-use (see docs/adr/0001). Compute records each
-- assertion's jti when it opens a session and refuses a jti it has seen.
-- Rows are only needed until the assertion would have expired anyway.
-- Not user-owned: no user_id.

CREATE TABLE used_login_assertions (
    jti        text PRIMARY KEY,
    expires_at timestamptz NOT NULL
);

CREATE INDEX used_login_assertions_expires_at_idx ON used_login_assertions (expires_at);
