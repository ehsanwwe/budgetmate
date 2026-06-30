from pathlib import Path
from urllib.parse import urlsplit
from pydantic import field_validator
from pydantic_settings import BaseSettings
from typing import List

BACKEND_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BACKEND_DIR / ".env"


class Settings(BaseSettings):
    AI_PROVIDER: str = ""
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "gpt-oss:20b"
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "5tgb%TGB"
    OTP_MOCK_CODE: str = "123456"
    JWT_SECRET: str = "changeme"
    JWT_ALGORITHM: str = "HS256"
    DATABASE_URL: str = f"sqlite:///{(BACKEND_DIR / 'budgetmate.db').as_posix()}"
    CORS_ORIGINS: str = "http://localhost:3000"
    STARTER_FREE_TOKENS: int = 20000
    APP_TIMEZONE: str = "Asia/Tehran"
    AGENT_DEBUG_TRACE: bool = False
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/auth/google/callback"
    GOOGLE_OAUTH_FRONTEND_SUCCESS_URL: str = "http://localhost:3000/fa"
    GOOGLE_OAUTH_FRONTEND_ERROR_URL: str = "http://localhost:3000/fa/login"
    GOOGLE_PEOPLE_PROFILE_ENRICHMENT_ENABLED: bool = False

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

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def normalize_cors_origins(cls, value: str) -> str:
        normalized: list[str] = []
        for raw_origin in str(value).split(","):
            origin = raw_origin.strip().rstrip("/")
            if not origin:
                continue
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.netloc
                or parsed.path
                or parsed.query
                or parsed.fragment
                or origin.startswith("http://https://")
                or origin.startswith("https://http://")
            ):
                raise ValueError(f"Invalid CORS origin: {origin}")
            canonical = f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"
            if canonical not in normalized:
                normalized.append(canonical)
        if not normalized:
            raise ValueError("CORS_ORIGINS must contain at least one valid origin")
        return ",".join(normalized)

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    model_config = {"env_file": str(ENV_FILE), "extra": "ignore"}


settings = Settings()
