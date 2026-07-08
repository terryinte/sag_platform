from __future__ import annotations

import os

from pydantic import BaseModel, Field


class Settings(BaseModel):
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    log_level: str = Field(default="info")
    dataforseo_login: str = Field(default_factory=lambda: os.getenv("DATAFORSEO_LOGIN", ""))
    dataforseo_password: str = Field(default_factory=lambda: os.getenv("DATAFORSEO_PASSWORD", ""))
    openrouter_api_key: str = Field(default_factory=lambda: os.getenv("OPENROUTER_API_KEY", ""))
    qianfan_access_key: str = Field(default_factory=lambda: os.getenv("QIANFAN_ACCESS_KEY", ""))
    qianfan_secret_key: str = Field(default_factory=lambda: os.getenv("QIANFAN_SECRET_KEY", ""))


settings = Settings()
