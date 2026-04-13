from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── Facebook / Meta ──────────────────────────────────────────────────────
    page_access_token: str
    verify_token: str
    app_secret: str

    # ── GitHub Models API (OpenAI-compatible) ────────────────────────────────
    github_token: str
    github_models_endpoint: str = "https://models.inference.ai.azure.com"
    ai_model: str = "gpt-4o-mini"
    max_history_messages: int = 20

    # ── Google Sheets ─────────────────────────────────────────────────────────
    google_service_account_json: str   # Nội dung JSON trên 1 dòng
    google_sheet_id: str

    # ── App ───────────────────────────────────────────────────────────────────
    data_dir: str = "data"
    port: int = 8000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
