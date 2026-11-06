from typing import Dict, Any
from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    environment: str
    version: str
    database: Dict[str, Any]
    ai_status: Dict[str, Any]

