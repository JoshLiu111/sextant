from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health_reports_service_is_ok():
    response = client.get("/api/compute/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "sextant-compute",
        "version": "0.1.0",
    }


def test_unknown_compute_route_is_404():
    response = client.get("/api/compute/does-not-exist")

    assert response.status_code == 404
