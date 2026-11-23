"""FastAPI application factory for the Sextant compute service.

Every public route lives under ``API_PREFIX`` because Vercel forwards the
original request path (``/api/compute/...``) to this service unchanged.
Add each tool as its own ``APIRouter`` and include it in ``create_app``.
"""

from fastapi import APIRouter, FastAPI

from sextant_compute import SERVICE_NAME, __version__
from sextant_compute.errors import install_error_handlers
from sextant_compute.options.api import router as options_router

API_PREFIX = "/api/compute"

health_router = APIRouter(tags=["health"])


@health_router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME, "version": __version__}


def create_app() -> FastAPI:
    app = FastAPI(
        title="Sextant compute service",
        version=__version__,
        docs_url=f"{API_PREFIX}/docs",
        openapi_url=f"{API_PREFIX}/openapi.json",
    )
    install_error_handlers(app)
    app.include_router(health_router, prefix=API_PREFIX)
    app.include_router(options_router, prefix=f"{API_PREFIX}/options")
    return app
