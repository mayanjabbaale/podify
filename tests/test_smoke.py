"""Smoke tests for the M1 skeleton.

Covers:
- /health returns 200 with the expected JSON shape (db ok; redis may be error
  in CI, in which case the endpoint should still return 503 with the same shape)
- The Celery ping task returns 'pong' in eager mode
- The root URL renders the upload page
"""

from __future__ import annotations


def test_ping_task_returns_pong() -> None:
    from app.tasks import ping

    assert ping.apply().get() == "pong"


def test_root_renders_upload_page(client) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Upload a PDF" in response.text


def test_health_returns_expected_shape(client) -> None:
    response = client.get("/health")
    body = response.json()
    assert body["status"] in {"ok", "degraded"}
    assert body["db"] in {"ok", "error"}
    assert body["redis"] in {"ok", "error"}
    # If both subsystems are ok -> 200; otherwise 503.
    if body["status"] == "ok":
        assert response.status_code == 200
    else:
        assert response.status_code == 503
