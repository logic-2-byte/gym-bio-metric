# ** Base Modules
from fastapi import status

# ** App Modules
from app.main import client


def test_home() -> None:
    response = client.get("/api/health")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"message": "All Healthy"}


def test_iclock_cdata_get() -> None:
    response = client.get("/iclock/cdata")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == "OK"


def test_iclock_cdata_post() -> None:
    response = client.post("/iclock/cdata", content="test body data")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == "OK"


def test_catch_all_route() -> None:
    response = client.get("/some/unhandled/path?param=value")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == "OK"
