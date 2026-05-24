from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    OPENCLAW_URL: str = "http://188.136.214.220:18789"
    OPENCLAW_TOKEN: str = ""
    AI_PROVIDER: str = "openclaw"
    PRIMARY_MODEL: str = "ollama/qwen3-coder:30b"
    FALLBACK_MODELS: str = "ollama/qwen3-coder:latest,ollama/gemma3:12b,ollama/qwen3:14b,openai/gpt-4o-mini"
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "5tgb%TGB"
    OTP_MOCK_CODE: str = "123456"
    JWT_SECRET: str = "changeme"
    JWT_ALGORITHM: str = "HS256"
    DATABASE_URL: str = "sqlite:///./budgetmate.db"
    CORS_ORIGINS: str = "http://localhost:3000"

    @property
    def fallback_models_list(self) -> List[str]:
        return [m.strip() for m in self.FALLBACK_MODELS.split(",") if m.strip()]

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
