import uuid
import re
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy import text

from app.config import settings
from app.core.logging_config import setup_logging, request_id_ctx
from app.database import engine
from app.api.v1 import api_router

# Initialize structured or text logging according to configuration
setup_logging(log_format=settings.LOG_FORMAT)
logger = logging.getLogger("brandguard")

SAFE_REQUEST_ID_REGEX = re.compile(r"^[a-zA-Z0-9_\-]{8,64}$")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup validation
    logger.info("Initializing BrandGuard Backend Foundation...")
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1;"))
            vector_check = conn.execute(
                text("SELECT extversion FROM pg_extension WHERE extname = 'vector';")
            ).fetchone()
            if vector_check:
                logger.info("PostgreSQL connection verified. pgvector extension active (v%s).", vector_check[0])
            else:
                logger.warning("PostgreSQL connected, but pgvector extension is NOT active.")
    except Exception as e:
        logger.error("Failed to connect to database on startup: %s", e)
        raise e

    yield

    # Shutdown
    logger.info("Shutting down BrandGuard Backend...")


docs_enabled = settings.IS_DOCS_ENABLED

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json" if docs_enabled else None,
    docs_url=f"{settings.API_V1_STR}/docs" if docs_enabled else None,
    redoc_url=f"{settings.API_V1_STR}/redoc" if docs_enabled else None,
    lifespan=lifespan,
)


# -----------------------------------------------------------------------------
# Security & Request Tracing Middleware
# -----------------------------------------------------------------------------
@app.middleware("http")
async def security_and_tracing_middleware(request: Request, call_next):
    # Safe validation of incoming request ID, else generate fresh UUID4
    incoming_req_id = request.headers.get("x-request-id") or request.headers.get("X-Request-ID")
    if incoming_req_id and SAFE_REQUEST_ID_REGEX.match(incoming_req_id):
        request_id = incoming_req_id
    else:
        request_id = str(uuid.uuid4())

    request.state.request_id = request_id
    token = request_id_ctx.set(request_id)

    try:
        response: Response = await call_next(request)
    finally:
        request_id_ctx.reset(token)

    # Attach Request ID header to response
    response.headers["X-Request-ID"] = request_id

    # Attach hardened security headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    # Conditional HSTS: strictly when direct HTTPS is active OR when forwarded by a trusted proxy
    client_ip = request.client.host if request.client else ""
    is_trusted_proxy = client_ip in settings.TRUSTED_PROXY_IPS or "*" in settings.TRUSTED_PROXY_IPS
    forwarded_proto = request.headers.get("x-forwarded-proto", "").lower()

    if request.url.scheme == "https" or (is_trusted_proxy and forwarded_proto == "https"):
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    return response


# -----------------------------------------------------------------------------
# CORS Configuration
# -----------------------------------------------------------------------------
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# -----------------------------------------------------------------------------
# Trusted Host Boundary
# -----------------------------------------------------------------------------
if settings.ALLOWED_HOSTS:
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.ALLOWED_HOSTS,
    )


# -----------------------------------------------------------------------------
# Structured Error Handlers (without leaking stack traces in production)
# -----------------------------------------------------------------------------
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    req_id = getattr(request.state, "request_id", None)
    error_payload = {
        "code": exc.status_code,
        "message": exc.detail,
        "path": str(request.url.path),
    }
    if req_id:
        error_payload["request_id"] = req_id

    headers = {"X-Request-ID": req_id} if req_id else {}
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": error_payload,
        },
        headers=headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    req_id = getattr(request.state, "request_id", None)
    error_payload = {
        "code": 422,
        "message": "Validation Error",
        "details": exc.errors(),
        "path": str(request.url.path),
    }
    if req_id:
        error_payload["request_id"] = req_id

    headers = {"X-Request-ID": req_id} if req_id else {}
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "success": False,
            "error": error_payload,
        },
        headers=headers,
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    req_id = getattr(request.state, "request_id", None) or "unknown"
    logger.exception("Unhandled server error [request_id=%s]: %s", req_id, exc)
    headers = {"X-Request-ID": req_id} if req_id != "unknown" else {}
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "error": {
                "code": 500,
                "message": "Internal Server Error",
                "path": str(request.url.path),
                "request_id": req_id,
            },
        },
        headers=headers,
    )


# -----------------------------------------------------------------------------
# API Router Registration
# -----------------------------------------------------------------------------
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/")
def root():
    resp = {
        "message": "BrandGuard Pre-Publication Governance Platform API",
        "health": f"{settings.API_V1_STR}/health",
    }
    if settings.IS_DOCS_ENABLED:
        resp["docs"] = f"{settings.API_V1_STR}/docs"
    return resp
