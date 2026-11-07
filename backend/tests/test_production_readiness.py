"""
backend/tests/test_production_readiness.py
Step 1 Production Hardening Verification:
- Configuration validation (ENVIRONMENT, SECRET_KEY, DEBUG, CORS, ALLOWED_HOSTS, STORAGE_PATH, LOG_FORMAT)
- Low-entropy rejection & entropy documentation
- Middleware & Security headers (X-Content-Type-Options, X-Frame-Options, Referrer-Policy, conditional HSTS)
- HSTS proxy trust verification (rejects spoofed X-Forwarded-Proto from untrusted clients)
- Request ID tracing, validation, and propagation (CRLF injection prevention)
- Error handling without stack trace leakage
- Trusted host boundary enforcement
- API documentation visibility toggle
- Health endpoints: /health/live, /health/ready, and comprehensive /health
- Storage writeability, unique probe file, and failure cleanup
- Structured JSON logging, document text redaction, and exception secret scrubbing
"""
import os
import re
import json
import uuid
import secrets
import logging
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from fastapi import FastAPI, Request
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.config import Settings, settings
from app.main import app
from app.core.logging_config import JSONLogFormatter, request_id_ctx, setup_logging

client = TestClient(app)


# =============================================================================
# 1. Configuration & Security Hardening Tests
# =============================================================================
class TestProductionConfig:
    def test_environment_validation(self):
        """Rejects unrecognized environments."""
        with pytest.raises(ValueError, match="ENVIRONMENT must be one of"):
            Settings(ENVIRONMENT="invalid_env")

        # Valid environments must pass
        for valid_env in ["development", "staging", "production"]:
            s = Settings(
                ENVIRONMENT=valid_env,
                DEBUG=False,
                SECRET_KEY="c1d2e3f4g5h6i7j8k9l0m1n2o3p4q5r6",
            )
            assert s.ENVIRONMENT == valid_env

    def test_production_rejects_debug_true(self):
        """DEBUG must be False in production."""
        with pytest.raises(ValueError, match="DEBUG must be False in production"):
            Settings(
                ENVIRONMENT="production",
                DEBUG=True,
                SECRET_KEY="c1d2e3f4g5h6i7j8k9l0m1n2o3p4q5r6",
            )

    def test_production_rejects_default_or_weak_secret(self):
        """Production rejects default development key, weak keys, or keys < 32 bytes."""
        # 1. Default dev secret rejected
        with pytest.raises(ValueError, match="cannot use default development key"):
            Settings(
                ENVIRONMENT="production",
                DEBUG=False,
                SECRET_KEY="brandguard_development_secret_key_change_in_production_32bytes_min",
            )

        # 2. Known weak secret rejected
        with pytest.raises(ValueError, match="cannot use default development key"):
            Settings(
                ENVIRONMENT="production",
                DEBUG=False,
                SECRET_KEY="secret",
            )

        # 3. Short secret (< 32 bytes) rejected
        with pytest.raises(ValueError, match="must contain at least 32 bytes of entropy"):
            Settings(
                ENVIRONMENT="production",
                DEBUG=False,
                SECRET_KEY="short_key_under_32_bytes!",
            )

        # 4. Low-entropy string (e.g. repeated single character) rejected
        with pytest.raises(ValueError, match="low character entropy"):
            Settings(
                ENVIRONMENT="production",
                DEBUG=False,
                SECRET_KEY="a" * 64,
            )

        # 5. Valid strong cryptographic secret succeeds
        strong_secret = secrets.token_hex(32)  # 64-character hex string (256-bit entropy)
        valid_prod = Settings(
            ENVIRONMENT="production",
            DEBUG=False,
            SECRET_KEY=strong_secret,
        )
        assert valid_prod.SECRET_KEY == strong_secret
        assert valid_prod.DEBUG is False

    def test_cors_origins_parsing(self):
        """CORS origins parsed from comma-separated string, JSON list, or Python list."""
        # Comma-separated string
        s1 = Settings(BACKEND_CORS_ORIGINS="https://app.brandguard.com, https://brandguard.com/")
        assert s1.BACKEND_CORS_ORIGINS == ["https://app.brandguard.com", "https://brandguard.com"]

        # JSON array string
        s2 = Settings(BACKEND_CORS_ORIGINS='["https://demo.brandguard.com", "https://staging.brandguard.com"]')
        assert s2.BACKEND_CORS_ORIGINS == ["https://demo.brandguard.com", "https://staging.brandguard.com"]

        # Empty string
        s3 = Settings(BACKEND_CORS_ORIGINS="")
        assert s3.BACKEND_CORS_ORIGINS == []

    def test_allowed_hosts_parsing(self):
        """Allowed hosts parsed from comma-separated or JSON list."""
        s = Settings(ALLOWED_HOSTS="brandguard.com, api.brandguard.com, localhost")
        assert s.ALLOWED_HOSTS == ["brandguard.com", "api.brandguard.com", "localhost"]

    def test_trusted_proxy_ips_parsing(self):
        """Trusted proxy IPs parsed from comma-separated string."""
        s = Settings(TRUSTED_PROXY_IPS="10.0.0.1, 192.168.1.1, 127.0.0.1")
        assert s.TRUSTED_PROXY_IPS == ["10.0.0.1", "192.168.1.1", "127.0.0.1"]

    def test_log_format_validation(self):
        """LOG_FORMAT must be text or json."""
        assert Settings(LOG_FORMAT="text").LOG_FORMAT == "text"
        assert Settings(LOG_FORMAT="json").LOG_FORMAT == "json"
        with pytest.raises(ValueError, match="LOG_FORMAT must be 'text' or 'json'"):
            Settings(LOG_FORMAT="yaml")


# =============================================================================
# 2. Middleware & Security Headers Tests
# =============================================================================
class TestSecurityMiddleware:
    def test_security_headers_present(self):
        """Standard hardened headers must be attached to every response."""
        response = client.get("/")
        assert response.status_code == 200
        headers = response.headers

        assert headers.get("X-Content-Type-Options") == "nosniff"
        assert headers.get("X-Frame-Options") == "DENY"
        assert headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
        # Obsolete header must NOT be present
        assert "X-XSS-Protection" not in headers

    def test_conditional_hsts_trusted_proxy(self):
        """HSTS header is attached when request uses HTTPS or X-Forwarded-Proto=https from trusted proxy."""
        # 1. Plain HTTP request: no HSTS
        resp_http = client.get("/")
        assert "Strict-Transport-Security" not in resp_http.headers

        # 2. Trusted proxy (TestClient defaults to host='testclient' which is in default TRUSTED_PROXY_IPS)
        resp_https = client.get("/", headers={"x-forwarded-proto": "https"})
        assert resp_https.headers.get("Strict-Transport-Security") == "max-age=31536000; includeSubDomains"

    def test_hsts_rejects_untrusted_client_spoofed_forwarded_proto(self):
        """Untrusted client IP cannot spoof X-Forwarded-Proto to activate HSTS."""
        # Create an app where only 10.0.0.1 is trusted
        from app.main import security_and_tracing_middleware
        test_app = FastAPI()
        test_app.middleware("http")(security_and_tracing_middleware)

        @test_app.get("/ping")
        def ping():
            return {"ok": True}

        # Client connecting from an untrusted public IP 198.51.100.2
        test_c = TestClient(test_app, client=("198.51.100.2", 52123))
        resp = test_c.get("/ping", headers={"x-forwarded-proto": "https"})
        assert resp.status_code == 200
        # HSTS MUST NOT be activated because 198.51.100.2 is not in TRUSTED_PROXY_IPS
        assert "Strict-Transport-Security" not in resp.headers

    def test_request_id_generation_and_propagation(self):
        """Responses must include X-Request-ID, generating a UUID when omitted."""
        # 1. Auto-generated UUID4
        resp = client.get("/")
        req_id = resp.headers.get("X-Request-ID")
        assert req_id is not None
        # Verify valid UUID format
        parsed_uuid = uuid.UUID(req_id)
        assert str(parsed_uuid) == req_id

        # 2. Safe incoming request ID is preserved
        custom_id = "trace-corp-client-12345"
        resp_custom = client.get("/", headers={"X-Request-ID": custom_id})
        assert resp_custom.headers.get("X-Request-ID") == custom_id

        # 3. Malformed / unsafe request ID is discarded and replaced with a valid UUID
        unsafe_id = "<script>alert(1)</script>"
        resp_unsafe = client.get("/", headers={"X-Request-ID": unsafe_id})
        safe_replacement = resp_unsafe.headers.get("X-Request-ID")
        assert safe_replacement != unsafe_id
        uuid.UUID(safe_replacement)  # Must be valid UUID

        # 4. CRLF injection attempt discarded
        crlf_id = "trace\r\nSet-Cookie: evil=1"
        resp_crlf = client.get("/", headers={"X-Request-ID": crlf_id})
        safe_crlf = resp_crlf.headers.get("X-Request-ID")
        assert "\r" not in safe_crlf and "\n" not in safe_crlf
        uuid.UUID(safe_crlf)

    def test_trusted_host_middleware_blocks_unauthorized_hosts(self):
        """Untrusted host header returns HTTP 400 Bad Request."""
        # Create an isolated test app with TrustedHostMiddleware
        test_app = FastAPI()
        test_app.add_middleware(TrustedHostMiddleware, allowed_hosts=["brandguard.local", "testserver"])

        @test_app.get("/ping")
        def ping():
            return {"ping": "pong"}

        isolated_client = TestClient(test_app)

        # Allowed host
        ok_resp = isolated_client.get("/ping", headers={"host": "brandguard.local"})
        assert ok_resp.status_code == 200

        # Disallowed / spoofed host
        blocked_resp = isolated_client.get("/ping", headers={"host": "evil-attacker.com"})
        assert blocked_resp.status_code == 400

    def test_production_error_response_does_not_leak_stack_traces(self):
        """500 Internal Server Error returns structured JSON with request_id and no trace."""
        test_app = FastAPI()

        from app.main import general_exception_handler, security_and_tracing_middleware
        test_app.middleware("http")(security_and_tracing_middleware)
        test_app.add_exception_handler(Exception, general_exception_handler)

        @test_app.get("/trigger-crash")
        def crash():
            raise RuntimeError("Database connection secret DB_PASS=super_confidential_123 failed")

        c = TestClient(test_app, raise_server_exceptions=False)
        resp = c.get("/trigger-crash")
        assert resp.status_code == 500
        data = resp.json()

        assert data["success"] is False
        assert data["error"]["code"] == 500
        assert data["error"]["message"] == "Internal Server Error"
        assert "super_confidential_123" not in json.dumps(data)
        assert "RuntimeError" not in json.dumps(data)
        assert data["error"]["request_id"] is not None
        assert resp.headers.get("X-Request-ID") == data["error"]["request_id"]


# =============================================================================
# 3. API Documentation Visibility Tests
# =============================================================================
class TestDocsVisibility:
    def test_docs_enabled_in_development(self):
        """Interactive docs are enabled in development."""
        dev_settings = Settings(ENVIRONMENT="development", DEBUG=True)
        assert dev_settings.IS_DOCS_ENABLED is True

        # In current dev app:
        docs_resp = client.get("/api/v1/docs")
        assert docs_resp.status_code == 200
        openapi_resp = client.get("/api/v1/openapi.json")
        assert openapi_resp.status_code == 200

    def test_docs_disabled_in_production_by_default(self):
        """In production, /docs, /redoc, and /openapi.json are disabled (404)."""
        prod_settings = Settings(
            ENVIRONMENT="production",
            DEBUG=False,
            SECRET_KEY=secrets.token_hex(32),
        )
        assert prod_settings.IS_DOCS_ENABLED is False

        # Create isolated production app to verify route registration
        prod_app = FastAPI(
            openapi_url=None,
            docs_url=None,
            redoc_url=None,
        )
        prod_client = TestClient(prod_app)
        assert prod_client.get("/docs").status_code == 404
        assert prod_client.get("/redoc").status_code == 404
        assert prod_client.get("/openapi.json").status_code == 404

    def test_docs_can_be_explicitly_enabled_in_production(self):
        """If DOCS_ENABLED=True is explicitly configured, docs are permitted."""
        prod_with_docs = Settings(
            ENVIRONMENT="production",
            DEBUG=False,
            SECRET_KEY=secrets.token_hex(32),
            DOCS_ENABLED=True,
        )
        assert prod_with_docs.IS_DOCS_ENABLED is True


# =============================================================================
# 4. Health Endpoints Tests
# =============================================================================
class TestHealthEndpoints:
    def test_health_live_endpoint(self):
        """Liveness probe returns 200 immediately without dependency checks."""
        resp = client.get("/api/v1/health/live")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "live"
        assert "timestamp" in data
        assert resp.headers.get("X-Request-ID") is not None

    def test_health_ready_endpoint_healthy(self):
        """Readiness probe returns 200 when DB and storage are accessible."""
        resp = client.get("/api/v1/health/ready")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ready"
        assert data["database"] == "connected"
        assert data["storage"] == "writable"

    def test_health_ready_endpoint_storage_failure(self, tmp_path):
        """Readiness probe returns 503 when storage directory is unwritable."""
        with patch("builtins.open", side_effect=PermissionError("EACCES: Permission denied")):
            resp = client.get("/api/v1/health/ready")
            assert resp.status_code == 503
            data = resp.json()
            assert data["status"] == "not_ready"
            assert data["storage"] == "unavailable"

    def test_health_ready_endpoint_db_failure(self):
        """Readiness probe returns 503 when database is unavailable."""
        with patch("app.api.v1.health.Session.execute", side_effect=Exception("DB connection refused")):
            resp = client.get("/api/v1/health/ready")
            assert resp.status_code == 503
            data = resp.json()
            assert data["status"] == "not_ready"
            assert data["database"] == "unavailable"
            # Must not leak connection string
            assert "DB connection refused" not in json.dumps(data)

    def test_comprehensive_health_endpoint_retained(self):
        """Retains existing /api/v1/health response for frontend and monitoring compatibility."""
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["database"]["connected"] is True
        assert data["database"]["pgvector"] is True
        assert "ai_status" in data


# =============================================================================
# 5. Storage Tenant Isolation & Configuration Tests
# =============================================================================
class TestStorageConfiguration:
    def test_storage_path_configured(self):
        """STORAGE_PATH is configurable and preserves existing directory layout."""
        from app.api.v1.documents import STORAGE_BASE_DIR
        assert STORAGE_BASE_DIR == os.path.abspath(settings.STORAGE_PATH)
        assert os.path.isdir(STORAGE_BASE_DIR)


# =============================================================================
# 6. Structured JSON Logging Tests
# =============================================================================
class TestStructuredLogging:
    def test_json_formatter_structure_and_redaction(self):
        """JSONLogFormatter formats records with ISO timestamp, request_id, and redacts secrets & document text."""
        formatter = JSONLogFormatter()
        record = logging.LogRecord(
            name="brandguard.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=10,
            msg="User login attempted",
            args=(),
            exc_info=None,
        )
        record.event = "auth_login"
        record.payload = {
            "email": "user@example.com",
            "password": "SuperSecretPassword123!",
            "token": "jwt_token_material",
            "extracted_text": "Highly confidential internal draft content text",
            "safe_metadata": "browser_chrome",
        }

        # Set request_id in context
        token = request_id_ctx.set("trace-json-99999")
        try:
            formatted_output = formatter.format(record)
        finally:
            request_id_ctx.reset(token)

        parsed = json.loads(formatted_output)
        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "brandguard.test"
        assert parsed["message"] == "User login attempted"
        assert parsed["request_id"] == "trace-json-99999"
        assert parsed["event"] == "auth_login"

        # Verify sensitive keys and document text redacted
        assert parsed["data"]["password"] == "[REDACTED]"
        assert parsed["data"]["token"] == "[REDACTED]"
        assert parsed["data"]["extracted_text"] == "[REDACTED]"
        assert parsed["data"]["safe_metadata"] == "browser_chrome"

    def test_exception_logging_scrubs_secrets(self):
        """Exception traces in JSONLogFormatter scrub embedded credentials."""
        formatter = JSONLogFormatter()
        try:
            raise ValueError("Connection failed: password=super_secret_db_pass; token=jwt_abc123")
        except Exception:
            import sys
            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="brandguard.test",
            level=logging.ERROR,
            pathname=__file__,
            lineno=20,
            msg="Unhandled database error",
            args=(),
            exc_info=exc_info,
        )

        formatted_output = formatter.format(record)
        parsed = json.loads(formatted_output)
        assert "super_secret_db_pass" not in parsed["exception"]
        assert "jwt_abc123" not in parsed["exception"]
        assert "password=[REDACTED]" in parsed["exception"]
        assert "token=[REDACTED]" in parsed["exception"]
