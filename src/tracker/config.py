"""Settings, read from environment variables (or a .env file), plus the coverage universe."""

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://tracker:tracker@localhost:5432/tracker"

    # SEC asks every client for a descriptive User-Agent with contact details.
    sec_user_agent: str = "FundamentalsTracker research contact@example.com"

    # Any OpenAI-compatible /chat/completions endpoint that supports tool calling.
    llm_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    llm_api_key: str = ""
    llm_model: str = "gemini-3.7-flash"

    # /ask runs on the same worker threads as every other endpoint. A time budget per question and
    # a cap on questions in flight keep slow LLM calls from tying them all up.
    ask_timeout_seconds: float = 90
    ask_concurrency: int = 8

    universe_file: Path = ROOT / "config" / "universe.yaml"
    snapshot_dir: Path = ROOT / "data" / "snapshot"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def load_tickers() -> list[str]:
    """The coverage universe. Adding a company means adding a line to universe.yaml."""
    data = yaml.safe_load(get_settings().universe_file.read_text())
    return [t.upper() for t in data["tickers"]]
