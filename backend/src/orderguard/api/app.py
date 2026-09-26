"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from orderguard.api.routers import simulations
from orderguard.api.settings import get_app_settings


def create_app() -> FastAPI:
    settings = get_app_settings()
    app = FastAPI(
        title="OrderGuard API",
        description=(
            "Real-time delivery failure prediction and intervention system "
            "(synthetic marketplace simulation — no real company data)."
        ),
        version="0.1.0",
        # False by default (see AppSettings.debug) so unhandled exceptions
        # never return a traceback to the client in production.
        debug=settings.debug,
    )
    app.add_middleware(
        CORSMiddleware,
        # Never "*" -- driven by ORDERGUARD_ALLOWED_ORIGINS so the deployed
        # frontend's real origin (e.g. a Vercel URL) can be added in
        # production without a code change, while localhost:3000 keeps
        # working by default in development.
        allow_origins=settings.allowed_origins_list,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(simulations.router)

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
