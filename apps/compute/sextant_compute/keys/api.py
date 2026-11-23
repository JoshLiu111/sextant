"""Settings: a signed-in user's own data-provider keys (bring your own key).

Endpoints (all ``CurrentUser``: 401 when signed out), under ``/api/compute/keys``:

- ``GET ""``: the user's saved keys, ``[{provider, hint, created_at, updated_at}]``.
- ``PUT /{provider}`` with ``{key}``: checks the key with the provider, then
  saves it encrypted (replacing any earlier key). A rejected key answers 422
  ``invalid_key`` (field ``key``) and stores nothing; a provider outage answers
  503 ``source_unavailable`` and stores nothing.
- ``DELETE /{provider}``: removes the key and everything cached with it for
  this user (204, also when there was none).

The plaintext key is never returned: responses carry only ``hint``, its last
four characters. ``get_request_context`` (data/service.py) decrypts the keys
into ``ctx.keys`` on every request, so a replaced or deleted key takes effect
on the next request.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, BeforeValidator

from sextant_compute.auth import CurrentUser
from sextant_compute.auth.deps import get_db
from sextant_compute.data import user_cache
from sextant_compute.data.tiingo import TiingoAdapter
from sextant_compute.db import Database
from sextant_compute.errors import ApiError, check
from sextant_compute.keys import store
from sextant_compute.keys.cipher import KeyCipher, KeysNotConfigured

router = APIRouter(tags=["keys"])

Db = Annotated[Database, Depends(get_db)]
Provider = Literal["tiingo"]
PROVIDER_NAMES: dict[str, str] = {"tiingo": "Tiingo"}
MAX_KEY_LENGTH = 200
HINT_LENGTH = 4

_tiingo: TiingoAdapter | None = None


def get_tiingo() -> TiingoAdapter:
    """FastAPI dependency. Tests swap it with ``app.dependency_overrides``."""
    global _tiingo
    if _tiingo is None:
        _tiingo = TiingoAdapter.from_env()
    return _tiingo


def _strip(value: object) -> object:
    return value.strip() if isinstance(value, str) else value


class KeyIn(BaseModel):
    key: Annotated[
        str,
        BeforeValidator(_strip),
        check(lambda v: v != "", "Paste your API key."),
        check(lambda v: len(v) <= MAX_KEY_LENGTH, f"Use at most {MAX_KEY_LENGTH} characters."),
        check(
            lambda v: v.isascii() and v.isprintable() and not any(c.isspace() for c in v),
            "An API key has no spaces or special characters. Check that you copied only the key.",
        ),
    ]


class SavedKey(BaseModel):
    provider: Provider
    hint: str
    """The last four characters of the key; the rest is never shown again."""
    created_at: datetime
    updated_at: datetime


def _cipher() -> KeyCipher:
    try:
        return KeyCipher.from_env()
    except KeysNotConfigured:
        raise ApiError(503, "keys_not_configured", "Saving your own key is not available on this server yet.") from None


@router.get("")
def list_keys(user: CurrentUser, db: Db) -> list[SavedKey]:
    with db.connection() as conn:
        rows = store.list_for(conn, user.id)
    return [SavedKey.model_validate(row) for row in rows if row["provider"] in PROVIDER_NAMES]


@router.put("/{provider}")
def save_key(
    provider: Provider, body: KeyIn, user: CurrentUser, db: Db, tiingo: Annotated[TiingoAdapter, Depends(get_tiingo)]
) -> SavedKey:
    cipher = _cipher()
    if not tiingo.verify_key(body.key):  # SourceUnavailable -> 503 source_unavailable
        message = f"This key is invalid: {PROVIDER_NAMES[provider]} rejected it. Check that you copied the whole key."
        raise ApiError(422, "invalid_key", message, fields={"key": message})
    sealed = cipher.seal(user.id, provider, body.key)
    with db.connection() as conn:
        row = store.upsert(conn, user.id, provider, sealed, body.key[-HINT_LENGTH:])
    return SavedKey.model_validate(row)


@router.delete("/{provider}", status_code=status.HTTP_204_NO_CONTENT)
def delete_key(provider: Provider, user: CurrentUser, db: Db) -> Response:
    with db.connection() as conn:
        store.delete(conn, user.id, provider)
        # Without the key the user may no longer see that provider's data.
        user_cache.delete_for(conn, user.id, provider)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
