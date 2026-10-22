from __future__ import annotations

import os
from pathlib import Path

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
    openai_api_key: str = Field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    perplexity_api_key: str = Field(default_factory=lambda: os.getenv("PERPLEXITY_API_KEY", ""))
    gemini_api_key: str = Field(default_factory=lambda: os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", ""))
    anthropic_api_key: str = Field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    deepseek_api_key: str = Field(default_factory=lambda: os.getenv("DEEPSEEK_API_KEY", ""))
    kimi_api_key: str = Field(default_factory=lambda: os.getenv("KIMI_API_KEY", "") or os.getenv("MOONSHOT_API_KEY", ""))
    database_path: str = Field(
        default_factory=lambda: os.getenv(
            "SAG_DATABASE_PATH",
            str(Path(__file__).resolve().parents[4] / "data" / "sag-mvp.db"),
        )
    )


settings = Settings()
