"""FastAPI application factory for the Sextant compute service.

Every public route lives under ``API_PREFIX`` because Vercel forwards the
original request path (``/api/compute/...``) to this service unchanged.
Add each tool as its own ``APIRouter`` and include it in ``create_app``.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

from sextant_compute import SERVICE_NAME, __version__
from sextant_compute.auth.api import router as auth_router
from sextant_compute.db import Database
from sextant_compute.errors import install_error_handlers
from sextant_compute.macro.api import router as macro_router
from sextant_compute.options.api import router as options_router
from sextant_compute.portfolio.api import router as portfolio_router
from sextant_compute.risk.api import router as risk_router

API_PREFIX = "/api/compute"

health_router = APIRouter(tags=["health"])


@health_router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME, "version": __version__}


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    app.state.db.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Sextant compute service",
        version=__version__,
        docs_url=f"{API_PREFIX}/docs",
        openapi_url=f"{API_PREFIX}/openapi.json",
        lifespan=_lifespan,
    )
    install_error_handlers(app)
    # Opened lazily on first use, so anonymous tools never need a database.
    app.state.db = Database.from_env()
    app.include_router(health_router, prefix=API_PREFIX)
    app.include_router(options_router, prefix=f"{API_PREFIX}/options")
    app.include_router(risk_router, prefix=f"{API_PREFIX}/risk")
    app.include_router(portfolio_router, prefix=f"{API_PREFIX}/portfolio")
    app.include_router(macro_router, prefix=f"{API_PREFIX}/macro")
    app.include_router(auth_router, prefix=API_PREFIX)
    return app
