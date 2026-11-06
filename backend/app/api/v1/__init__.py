from fastapi import APIRouter
from app.api.v1.health import router as health_router
from app.api.v1.auth import router as auth_router
from app.api.v1.users import router as users_router
from app.api.v1.audit import router as audit_router
from app.api.v1.constitution import router as constitution_router
from app.api.v1.documents import router as documents_router
from app.api.v1.analysis import router as analysis_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["Health"])
api_router.include_router(auth_router, prefix="/auth", tags=["Authentication"])
api_router.include_router(users_router, prefix="/users", tags=["Users"])
api_router.include_router(audit_router, prefix="/audit", tags=["Audit"])
api_router.include_router(constitution_router, prefix="/constitution", tags=["Constitution"])
api_router.include_router(documents_router, prefix="/documents", tags=["Documents"])
api_router.include_router(analysis_router, prefix="/analysis", tags=["Brand Analysis"])
