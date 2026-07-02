"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.core.config import get_settings
from app.dao.item_dao import get_item_dao
from app.routers import health, items


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Application startup/shutdown hooks."""
    settings = get_settings()
    # Convenience for local dev / integration tests: create the table if missing.
    # In production, provision the table via infrastructure-as-code instead.
    if settings.auto_create_table and settings.environment != "production":
        get_item_dao().ensure_table()
    yield


def create_app() -> FastAPI:
    """Application factory: build and configure the FastAPI instance."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        debug=settings.debug,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(items.router)

    @app.get("/", tags=["root"])
    def root() -> dict[str, str]:
        """Root endpoint with a friendly pointer to the docs."""
        return {"message": f"{settings.app_name} is running", "docs": "/docs"}

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
