"""Accounts and sessions: who the current user is.

Route handlers that need the user take a dependency:

    from sextant_compute.auth import CurrentUser, OptionalUser

    @router.get("/things")
    def list_things(user: CurrentUser): ...      # 401 when signed out

    @router.get("/maybe")
    def maybe(user: OptionalUser): ...           # None when signed out

The session token arrives either as the ``sextant_session`` cookie (browser
calls to /api/compute/... are same-origin) or as ``Authorization: Bearer``
(server-side calls from apps/web, which forward the cookie value).
"""

from sextant_compute.auth.deps import CurrentUser, OptionalUser, User

__all__ = ["CurrentUser", "OptionalUser", "User"]
