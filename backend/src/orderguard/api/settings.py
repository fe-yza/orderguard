"""App-wide configuration sourced from environment variables, never
hardcoded -- CORS origins, debug mode, and the simulation-endpoint rate
limit. Kept separate from `persistence/database.py`'s DatabaseSettings
since these are unrelated concerns that happen to share the ORDERGUARD_
env prefix.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ORDERGUARD_")

    # Comma-separated list of allowed frontend origins for CORS. Defaults
    # to the local Next.js dev server; production sets this via env var to
    # the deployed frontend's real origin(s) (e.g. a Vercel URL). Never
    # "*" -- the API is not meant to be called from arbitrary origins.
    allowed_origins: str = "http://localhost:3000"

    # Governs FastAPI's `debug` flag, which controls whether unhandled
    # exceptions return a traceback in the response. Always False in
    # production; only ever set True for local debugging.
    debug: bool = False

    # POST /simulations runs three full simulation passes and is the only
    # endpoint expensive enough to need protecting from abuse (see
    # `api/rate_limit.py`). These defaults comfortably cover normal
    # interactive use -- the guided tour's one bootstrap run, a recruiter
    # clicking "Run experiment" repeatedly -- while still bounding a
    # scripted burst from one client.
    rate_limit_max_requests: int = 20
    rate_limit_window_seconds: float = 60.0

    @property
    def allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_app_settings() -> AppSettings:
    return AppSettings()
