from pathlib import Path
from pydantic import field_validator
from pydantic_settings import BaseSettings
from typing import List

BACKEND_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BACKEND_DIR / ".env"


class Settings(BaseSettings):
    OPENCLAW_URL: str = "http://188.136.214.220:18789"
    OPENCLAW_TOKEN: str = ""
    AI_PROVIDER: str = "openclaw"
    PRIMARY_MODEL: str = "ollama/gemma4:26b"
    FALLBACK_MODELS: str = "ollama/qwen3-coder:30b,ollama/qwen3-coder:latest,ollama/gemma3:12b,ollama/qwen3:14b,openai/gpt-4o-mini"
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "5tgb%TGB"
    OTP_MOCK_CODE: str = "123456"
    JWT_SECRET: str = "changeme"
    JWT_ALGORITHM: str = "HS256"
    DATABASE_URL: str = f"sqlite:///{(BACKEND_DIR / 'budgetmate.db').as_posix()}"
    CORS_ORIGINS: str = "http://localhost:3000"
    STARTER_FREE_TOKENS: int = 20000
    OPENAI_API_KEY: str = ""

    @field_validator("DATABASE_URL")
    @classmethod
    def normalize_sqlite_url(cls, value: str) -> str:
        prefix = "sqlite:///"
        if not value.startswith(prefix):
            return value

        db_path = value[len(prefix):]
        if db_path in (":memory:", ""):
            return value

        path = Path(db_path)
        if not path.is_absolute():
            path = BACKEND_DIR / path
        return f"{prefix}{path.resolve().as_posix()}"

    @property
    def fallback_models_list(self) -> List[str]:
        return [m.strip() for m in self.FALLBACK_MODELS.split(",") if m.strip()]

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    model_config = {"env_file": str(ENV_FILE), "extra": "ignore"}


settings = Settings()
