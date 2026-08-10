"""
Centralized configuration. All secrets come from environment variables —
never hardcoded, never committed. See .env.example for the full list.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://billing:billing@localhost:5432/billing"

    # Stripe (test mode only — see README)
    stripe_secret_key: str = "sk_test_placeholder"
    stripe_webhook_secret: str = "whsec_placeholder"
    stripe_price_id_pro: str = "price_placeholder"
    stripe_success_url: str = "http://localhost:8000/billing/success"
    stripe_cancel_url: str = "http://localhost:8000/billing/cancel"

    # App
    environment: str = "development"


settings = Settings()
