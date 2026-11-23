"""FastAPI application factory for the Sextant compute service.

Every public route lives under ``API_PREFIX`` because Vercel forwards the
original request path (``/api/compute/...``) to this service unchanged.
Add each tool as its own ``APIRouter`` and include it in ``create_app``.
"""

from fastapi import APIRouter, FastAPI

from sextant_compute import SERVICE_NAME, __version__

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
    app.include_router(health_router, prefix=API_PREFIX)
    return app
