import pytest
from fastapi import Response
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.mark.parametrize(
    "configured, origin, expected",
    [
        ("http://localhost:8000", "http://localhost:8000", 204),
        ("http://localhost:8000", "http://127.0.0.1:8000", 204),
        ("http://127.0.0.1:8000", "http://localhost:8000", 204),
        ("http://localhost:80", "http://127.0.0.1", 204),
        ("http://localhost:8000", None, 403),
        ("http://localhost:8000", "null", 403),
        ("http://localhost:8000", "http://127.0.0.1:8001", 403),
        ("http://localhost:8000", "https://127.0.0.1:8000", 403),
        ("http://localhost:8000", "http://localhost.evil.example:8000", 403),
        ("http://localhost:8000", "https://other.example.com", 403),
        ("http://example.com:8000", "http://example.com:8000", 204),
        ("http://example.com:8000", "http://localhost:8000", 403),
        ("https://localhost:8000", "https://127.0.0.1:8000", 403),
    ],
)
@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_origin_gate_allows_only_configured_site_and_local_http_alias(
    configured, origin, expected, method, tmp_path
):
    settings = Settings(
        _env_file=None,
        database_url="postgresql://localhost/unused",
        app_origin=configured,
        cookie_secure=configured.startswith("https://"),
        uploads_dir=tmp_path,
    )
    application = create_app(settings)

    @application.api_route("/api/origin-probe", methods=["POST", "PUT", "PATCH", "DELETE"])
    def probe():
        return Response(status_code=204)

    with TestClient(application) as client:
        headers = {"Origin": origin} if origin is not None else {}
        response = client.request(method, "/api/origin-probe", headers=headers)
        assert response.status_code == expected
        if expected == 403:
            assert response.json()["error"]["code"] == "ORIGIN_INVALID"
