from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "BrandGuard" in data["message"]
    assert data["health"] == "/api/v1/health"
    assert response.headers.get("X-Request-ID") is not None
    assert response.headers.get("X-Content-Type-Options") == "nosniff"


def test_health_check_endpoint():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"]["connected"] is True
    assert data["database"]["pgvector"] is True
    assert "0.8.6" in data["database"]["pgvector_version"]


def test_health_live_endpoint():
    response = client.get("/api/v1/health/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "live"
    assert "timestamp" in data


def test_health_ready_endpoint():
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["database"] == "connected"
    assert data["storage"] == "writable"
