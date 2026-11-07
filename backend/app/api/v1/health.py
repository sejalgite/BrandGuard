import os
import uuid
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.database import get_db
from app.config import settings
from app.schemas.health import HealthResponse, LivenessResponse, ReadinessResponse

logger = logging.getLogger("brandguard")

router = APIRouter()


@router.get("/health/live", response_model=LivenessResponse)
def liveness_check():
    """
    Lightweight process liveness probe for orchestrators (Docker, Kubernetes).
    Performs NO downstream dependency checks; returns 200 immediately if process is alive.
    """
    return LivenessResponse(
        status="live",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@router.get("/health/ready", response_model=ReadinessResponse)
def readiness_check(db: Session = Depends(get_db)):
    """
    Readiness probe verifying operational dependencies:
    1. PostgreSQL database connectivity
    2. Local file storage directory writeability
    Optional AI/Ollama endpoints do NOT fail readiness if deterministic analysis can operate.
    Never exposes internal connection strings, credentials, or stack traces.
    Uses unique non-colliding probe files and guarantees cleanup in a finally block.
    """
    db_connected = False
    try:
        db.execute(text("SELECT 1;"))
        db_connected = True
    except Exception:
        logger.warning("Readiness probe: database connectivity check failed.")

    storage_writable = False
    probe_file = None
    try:
        storage_dir = os.path.abspath(settings.STORAGE_PATH)
        os.makedirs(storage_dir, exist_ok=True)
        probe_file = os.path.join(storage_dir, f".readiness_probe_{uuid.uuid4().hex}")
        with open(probe_file, "w", encoding="utf-8") as f:
            f.write("probe")
        storage_writable = True
    except Exception:
        logger.warning("Readiness probe: storage writeability check failed.")
    finally:
        if probe_file and os.path.exists(probe_file):
            try:
                os.remove(probe_file)
            except OSError:
                pass

    if not (db_connected and storage_writable):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "not_ready",
                "database": "connected" if db_connected else "unavailable",
                "storage": "writable" if storage_writable else "unavailable",
            },
        )

    return ReadinessResponse(
        status="ready",
        database="connected",
        storage="writable",
    )


@router.get("/health", response_model=HealthResponse)
def health_check(db: Session = Depends(get_db)):
    """
    Comprehensive system health endpoint verifying:
    1. FastAPI application status
    2. PostgreSQL connection and pgvector extension status
    3. AI provider configuration status
    """
    db_status = {"connected": False, "pgvector": False, "version": None}

    try:
        # Check basic DB query & version
        version_row = db.execute(text("SELECT version();")).fetchone()
        if version_row:
            db_status["connected"] = True
            db_status["version"] = version_row[0].split(",")[0]

        # Check pgvector extension
        ext_row = db.execute(
            text("SELECT extversion FROM pg_extension WHERE extname = 'vector';")
        ).fetchone()
        if ext_row:
            db_status["pgvector"] = True
            db_status["pgvector_version"] = ext_row[0]
        else:
            db_status["pgvector"] = False
    except Exception:
        logger.warning("Comprehensive health check: database query failed.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database health check failed",
        )

    ai_status = {
        "gemini_configured": bool(settings.GEMINI_API_KEY),
        "ollama_endpoint": settings.OLLAMA_BASE_URL,
        "mode": "live" if settings.GEMINI_API_KEY else "offline_deterministic_fallback",
    }

    return HealthResponse(
        status="healthy",
        environment=settings.ENVIRONMENT,
        version="1.0.0",
        database=db_status,
        ai_status=ai_status,
    )
