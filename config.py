"""Configuração segura da aplicação."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

DEFAULT_BASE_URL = "https://api.safetyculture.io"


@dataclass(frozen=True)
class Settings:
    api_token: str | None
    base_url: str = DEFAULT_BASE_URL


def get_settings(token: str | None = None, base_url: str | None = None) -> Settings:
    """Obtém o token da sessão ou do ambiente, sem o expor."""
    resolved_token = (token or os.getenv("SAFETYCULTURE_API_TOKEN") or "").strip() or None
    resolved_base = (base_url or os.getenv("SAFETYCULTURE_API_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
    return Settings(api_token=resolved_token, base_url=resolved_base)

