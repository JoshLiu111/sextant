# Accounts: web runs Google sign-in, compute owns users, sessions and the database

**Status:** accepted (ticket #5)

The Next.js app runs the Google OIDC flow (authorization code + PKCE, state, nonce) and verifies the ID token. It then signs a 60-second HS256 **login assertion** with `SESSION_SECRET` and posts it to the compute service. Compute verifies it, upserts the user by Google `sub`, and returns an opaque session token. Web stores that token in an httpOnly, SameSite=Lax cookie `sextant_session`. The FastAPI compute service is the only code that talks to Postgres: it owns `users`, the DB-backed `sessions`, and every user-owned table that comes later (portfolios, encrypted keys, per-user cache, AI usage). The spec already puts data access and the DataService `ctx.user_id` in compute, and one database owner means one migration tool and one place to enforce isolation.

**Who the user is.** Compute resolves the user from the session token, sent as either the cookie (browser calls to `/api/compute/*` are same-origin) or `Authorization: Bearer` (server-side calls from web). Route handlers use the `CurrentUser` / `OptionalUser` FastAPI dependencies. Sessions are rows, not JWTs, so sign-out and account deletion take effect immediately.

**Migrations.** Plain SQL files in `apps/compute/sextant_compute/db/migrations/NNNN_name.sql`, applied in order by a small runner (`sextant_compute.db.migrate`). The runner records each file in `schema_migrations` and serialises with an advisory lock. By default it runs on the compute service's first database connection, so Neon preview branches migrate themselves (`DB_AUTO_MIGRATE=0` turns this off; `uv run python -m sextant_compute.db` runs it by hand). There is no ORM: queries are psycopg 3 SQL.

**Cascade convention.** Every user-owned table has `user_id uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE`. A table owned through a parent (e.g. holdings through portfolios) references the parent with `ON DELETE CASCADE`. Account deletion is a single `DELETE FROM users`. `tests/test_user_owned_cascade.py` inspects the live schema and fails if any foreign key into user-owned data is not cascading, if any `user_id` column lacks the FK, or if a user-owned table has no row factory in the cascade test.

## Considered options

- **Auth.js / NextAuth in web, with web also owning the DB.** Rejected: we would end up with two DB clients and two migration tools, and compute would have to decrypt Auth.js's JWE cookies to learn who the user is.
- **Stateless JWT session cookie verified by both services.** Rejected: sign-out and deletion could not revoke the token before it expired, and compute needs a DB lookup anyway to confirm the user still exists.
- **Alembic.** Rejected for now: there is no ORM, and plain SQL files plus a 30-line runner are easier to read. We can switch if migrations ever need branching or downgrades.

## Consequences

- `SESSION_SECRET` must be set to the same value for both services.
- Google does not accept wildcard redirect URIs, so each preview host that should support sign-in must be registered with the Google OAuth client, or sign-in tested on a stable branch alias.
- e2e tests use a fake OIDC provider (`apps/web/e2e/fake-oidc.mjs`) selected by `OIDC_ISSUER`. Production leaves it unset, so the issuer is Google.
