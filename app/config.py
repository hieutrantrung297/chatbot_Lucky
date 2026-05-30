from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── Facebook / Meta ──────────────────────────────────────────────────────
    facebook_app_id: str = ""
    facebook_page_id: str = ""
    page_access_token: str
    verify_token: str
    app_secret: str

    # ── GitHub Models API (OpenAI-compatible) ────────────────────────────────
    github_token: str
    github_models_endpoint: str = "https://models.inference.ai.azure.com"
    ai_model: str = "gpt-4o-mini"
    max_history_messages: int = 20

    # ── OpenAI fallback (dùng khi GitHub Models bị rate limit) ───────────────
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # ── Google Sheets ─────────────────────────────────────────────────────────
    google_service_account_json: str   # Nội dung JSON trên 1 dòng
    google_sheet_id: str

    # ── Admin dashboard ───────────────────────────────────────────────────────
    admin_password: str = "lucky2024"

    # ── App ───────────────────────────────────────────────────────────────────
    server_url: str = ""
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
