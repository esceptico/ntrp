from fastapi.testclient import TestClient

from ntrp.server.app import app


def test_provider_routes_are_registered_once():
    paths = TestClient(app).get("/openapi.json").json()["paths"]

    assert "/providers" in paths
    assert "/providers/{provider_id}/connect" in paths
    assert "/services" in paths
    assert "/services/{service_id}/connect" in paths
    assert "/tool-providers" in paths
