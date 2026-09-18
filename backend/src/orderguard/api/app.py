"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from orderguard.api.routers import orders, simulations


def create_app() -> FastAPI:
    app = FastAPI(
        title="OrderGuard API",
        description=(
            "Real-time delivery failure prediction and intervention system "
            "(synthetic marketplace simulation — no real company data)."
        ),
        version="0.1.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(simulations.router)
    app.include_router(orders.router)

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
