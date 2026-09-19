from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_env: str = "development"
    database_url: str = "sqlite:///./claims.db"
    redis_url: str = ""
    app_password: str = ""
    session_secret: str = ""
    app_url: str = "http://localhost:8000"
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    source_allowed_hosts: str = ""
    monitor_interval_seconds: int = 900
    worker_enabled: bool = True

    def validate_production(self):
        if self.app_env == "production":
            if len(self.app_password) < 16 or len(self.session_secret) < 32:
                raise ValueError(
                    "Production requires APP_PASSWORD (16+ characters) and SESSION_SECRET (32+ characters)."
                )
            if not self.database_url.startswith(("postgresql://", "postgres://", "postgresql+psycopg://")):
                raise ValueError("Production requires PostgreSQL DATABASE_URL.")
            if not self.app_url.startswith("https://"):
                raise ValueError("Production APP_URL must use HTTPS.")


settings = Settings()
