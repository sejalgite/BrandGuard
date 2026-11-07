"""
app/config.py
Production-ready configuration management for BrandGuard.

To generate a cryptographically secure 256-bit (32-byte) SECRET_KEY:
  - CLI: openssl rand -hex 32
  - Python: python -c "import secrets; print(secrets.token_urlsafe(32))"
"""
import os
import json
from typing import List, Optional, Union
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "BrandGuard API"

    # Database Configuration
    DATABASE_URL: str = "postgresql://brandguard_user:brandguard_secure_password@localhost:5435/brandguard"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    # JWT & Security
    DEFAULT_DEV_SECRET: str = "brandguard_development_secret_key_change_in_production_32bytes_min"
    SECRET_KEY: str = "brandguard_development_secret_key_change_in_production_32bytes_min"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    # CORS & Network Boundaries
    BACKEND_CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    ALLOWED_HOSTS: List[str] = ["localhost", "127.0.0.1", "testserver"]
    TRUSTED_PROXY_IPS: List[str] = ["127.0.0.1", "::1", "testclient"]

    # Storage Configuration (configurable path, preserving tenant isolation)
    STORAGE_PATH: str = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "storage",
        "documents"
    )

    # API Documentation Visibility (disabled by default in production)
    DOCS_ENABLED: Optional[bool] = None

    # Logging Format: 'text' (default) or 'json' (structured production logging)
    LOG_FORMAT: str = "text"

    # Optional AI Providers
    GEMINI_API_KEY: str = ""
    OLLAMA_BASE_URL: str = "http://localhost:11434"

    @field_validator("ENVIRONMENT")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        env = v.strip().lower()
        allowed = {"development", "staging", "production"}
        if env not in allowed:
            raise ValueError(f"ENVIRONMENT must be one of {allowed}, got '{v}'")
        return env

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return []
            if v.startswith("[") and v.endswith("]"):
                try:
                    return [str(item).strip().rstrip("/") for item in json.loads(v) if str(item).strip()]
                except Exception:
                    pass
            return [origin.strip().rstrip("/") for origin in v.split(",") if origin.strip()]
        elif isinstance(v, (list, tuple)):
            return [str(item).strip().rstrip("/") for item in v if str(item).strip()]
        return v

    @field_validator("ALLOWED_HOSTS", mode="before")
    @classmethod
    def assemble_allowed_hosts(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return ["*"]
            if v.startswith("[") and v.endswith("]"):
                try:
                    return [str(item).strip() for item in json.loads(v) if str(item).strip()]
                except Exception:
                    pass
            return [host.strip() for host in v.split(",") if host.strip()]
        elif isinstance(v, (list, tuple)):
            return [str(item).strip() for item in v if str(item).strip()]
        return v

    @field_validator("TRUSTED_PROXY_IPS", mode="before")
    @classmethod
    def assemble_trusted_proxies(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return []
            if v.startswith("[") and v.endswith("]"):
                try:
                    return [str(item).strip() for item in json.loads(v) if str(item).strip()]
                except Exception:
                    pass
            return [ip.strip() for ip in v.split(",") if ip.strip()]
        elif isinstance(v, (list, tuple)):
            return [str(item).strip() for item in v if str(item).strip()]
        return v

    @field_validator("LOG_FORMAT")
    @classmethod
    def validate_log_format(cls, v: str) -> str:
        fmt = v.strip().lower()
        if fmt not in {"text", "json"}:
            raise ValueError(f"LOG_FORMAT must be 'text' or 'json', got '{v}'")
        return fmt

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        env = self.ENVIRONMENT.lower()
        if env == "production":
            # 1. Require DEBUG=False in production
            if self.DEBUG:
                raise ValueError("DEBUG must be False in production environment.")

            # 2. Reject missing, weak, or default SECRET_KEY in production
            insecure_defaults = {
                self.DEFAULT_DEV_SECRET,
                "secret",
                "changeme",
                "password",
                "admin",
                "brandguard",
                "12345678",
                "supersecret",
            }
            if not self.SECRET_KEY or self.SECRET_KEY.strip() in insecure_defaults:
                raise ValueError(
                    "In production, SECRET_KEY must be set to a secure, cryptographically random string (cannot use default development key)."
                )
            if len(self.SECRET_KEY.encode("utf-8")) < 32:
                raise ValueError(
                    f"In production, SECRET_KEY must contain at least 32 bytes of entropy (got {len(self.SECRET_KEY.encode('utf-8'))} bytes)."
                )
            # Entropy heuristic: length is not proof of entropy; reject repetitive trivial strings
            if len(set(self.SECRET_KEY)) < 8:
                raise ValueError(
                    "In production, SECRET_KEY exhibits low character entropy (fewer than 8 unique characters). Use a cryptographically generated secret."
                )

        return self

    @property
    def IS_DOCS_ENABLED(self) -> bool:
        """Determines if interactive Swagger/ReDoc and OpenAPI schema are served."""
        if self.DOCS_ENABLED is not None:
            return self.DOCS_ENABLED
        return self.ENVIRONMENT.lower() != "production"

    @property
    def COOKIE_SECURE(self) -> bool:
        """
        Enforce Secure=True in production and staging.
        In development HTTP, Secure=False allows localhost cookies over plaintext HTTP.
        """
        return self.ENVIRONMENT.lower() in {"production", "staging"}

    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
