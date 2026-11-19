from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_app_secret: str = ""
    whatsapp_verify_token: str = ""
    graph_api_version: str = "v24.0"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5-5"

    database_url: str = "sqlite:///./data/bot.db"

    dry_run: bool = True
    alert_template_name: str = "intake_alert"
    alert_template_lang: str = "en"
    session_timeout_hours: int = 24

    projects_file: Path = ROOT / "config" / "projects.json"
    reasons_file: Path = ROOT / "config" / "reasons.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()
