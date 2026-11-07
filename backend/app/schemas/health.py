from typing import Dict, Any
from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    environment: str
    version: str
    database: Dict[str, Any]
    ai_status: Dict[str, Any]


class LivenessResponse(BaseModel):
    status: str
    timestamp: str


class ReadinessResponse(BaseModel):
    status: str
    database: str
    storage: str
