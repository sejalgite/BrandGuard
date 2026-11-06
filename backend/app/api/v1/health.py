from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.database import get_db
from app.config import settings
from app.schemas.health import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health_check(db: Session = Depends(get_db)):
    """
    Health check endpoint verifying:
    1. FastAPI application status
    2. Live PostgreSQL connection
    3. pgvector extension active status
    4. AI service configuration status
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
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database health check failed: {str(e)}",
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

