# ** Base Modules
from fastapi import status

# ** App Modules
import app.router.iclock
from app.main import client


def test_home() -> None:
    response = client.get("/api/health")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"message": "All Healthy"}


def test_iclock_cdata_get() -> None:
    response = client.get("/iclock/cdata")
    assert response.status_code == status.HTTP_200_OK
    assert response.text == "OK"


def test_iclock_cdata_post() -> None:
    response = client.post("/iclock/cdata", content="test body data")
    assert response.status_code == status.HTTP_200_OK
    assert response.text == "OK"


def test_iclock_getrequest_get() -> None:
    app.router.iclock.command_sent = False  # Reset flag for test isolation
    app.router.iclock.user_action = "disable"
    response = client.get("/iclock/getrequest")
    assert response.status_code == status.HTTP_200_OK
    assert response.text == "C:1:DATA QUERY tablename=user,filter=Pin=111"

    # Subsequent request should return OK
    response_again = client.get("/iclock/getrequest")
    assert response_again.status_code == status.HTTP_200_OK
    assert response_again.text == "OK"

    # Test enable action
    app.router.iclock.command_sent = False  # Reset flag
    app.router.iclock.user_action = "enable"
    response_enable = client.get("/iclock/getrequest")
    assert response_enable.status_code == status.HTTP_200_OK
    assert response_enable.text == "C:1:DATA QUERY tablename=user,filter=Pin=111"


def test_iclock_getrequest_post() -> None:
    response = client.post("/iclock/getrequest", content="ID=1&Return=0")
    assert response.status_code == status.HTTP_200_OK
    assert response.text == "OK"


def test_iclock_registry() -> None:
    response = client.post("/iclock/registry", content="test registry data")
    assert response.status_code == status.HTTP_200_OK
    assert response.text == "OK"


def test_iclock_devicecmd() -> None:
    response = client.post("/iclock/devicecmd", content="test devicecmd data")
    assert response.status_code == status.HTTP_200_OK
    assert response.text == "OK"


def test_catch_all_route() -> None:
    response = client.get("/some/unhandled/path?param=value")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == "OK"


def test_root_route() -> None:
    response = client.get("/")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"ok": True}
