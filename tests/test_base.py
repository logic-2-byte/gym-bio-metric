# ** Base Modules
from unittest.mock import AsyncMock, MagicMock
from fastapi import status

# ** App Modules
from app.main import app, client
from app.core.database import get_db

# Mock DB Session
mock_db = AsyncMock()

async def override_get_db():
    yield mock_db

app.dependency_overrides[get_db] = override_get_db

def test_home() -> None:
    # Reset mock
    mock_db.execute.reset_mock()
    mock_db.execute.side_effect = None
    response = client.get("/api/health")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"message": "All Healthy"}


def test_iclock_cdata_get() -> None:
    response = client.get("/iclock/cdata")
    assert response.status_code == status.HTTP_200_OK
    assert response.text == "OK"


def test_iclock_cdata_post() -> None:
    # Setup mock return values for cdata logic
    mock_db.execute.reset_mock()
    
    mock_result_tenant = MagicMock()
    mock_result_tenant.fetchone.return_value = ("gym_1",)
    
    mock_result_member = MagicMock()
    mock_result_member.fetchone.return_value = ("ACTIVE", "NONE", True)
    
    mock_result_last_cmd = MagicMock()
    mock_result_last_cmd.fetchone.return_value = None
    
    mock_db.execute.side_effect = [
        MagicMock(),  # update_device_last_seen execute
        mock_result_tenant,
        MagicMock(),  # att_query execute
        mock_result_member,
        mock_result_last_cmd,
        MagicMock()   # insert_cmd execute
    ]
    
    response = client.post("/iclock/cdata?SN=NCD8242500682&table=ATTLOG", content="111\t2026-06-07\t12:51:04\t255\t15")
    assert response.status_code == status.HTTP_200_OK
    assert response.text == "OK"


def test_iclock_getrequest_get() -> None:
    mock_db.execute.reset_mock()
    mock_db.execute.side_effect = None

    # Test when there is a pending command
    mock_result = MagicMock()
    mock_result.fetchone.return_value = (1, "DATA UPDATE USERINFO PIN=111\tGrp=3")
    mock_db.execute.return_value = mock_result
    
    response = client.get("/iclock/getrequest?SN=NCD8242500682")
    assert response.status_code == status.HTTP_200_OK
    assert response.text == "C:1:DATA UPDATE USERINFO PIN=111\tGrp=3"

    # Test when there are no pending commands
    mock_result_empty = MagicMock()
    mock_result_empty.fetchone.return_value = None
    mock_db.execute.return_value = mock_result_empty
    
    response_again = client.get("/iclock/getrequest?SN=NCD8242500682")
    assert response_again.status_code == status.HTTP_200_OK
    assert response_again.text == "OK"


def test_iclock_getrequest_post() -> None:
    response = client.post("/iclock/getrequest", content="ID=1&Return=0")
    assert response.status_code == status.HTTP_200_OK
    assert response.text == "OK"


def test_iclock_registry() -> None:
    response = client.post("/iclock/registry", content="test registry data")
    assert response.status_code == status.HTTP_200_OK
    assert response.text == "OK"


def test_iclock_devicecmd() -> None:
    mock_db.execute.reset_mock()
    mock_db.execute.side_effect = None
    mock_db.execute.return_value = MagicMock()
    
    response = client.post("/iclock/devicecmd?SN=NCD8242500682", content="ID=1&Return=0")
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


def test_get_device_status() -> None:
    mock_db.execute.reset_mock()
    mock_db.execute.side_effect = None
    
    import datetime
    mock_result = MagicMock()
    mock_result.fetchone.return_value = ("gym_1", "Gym name", datetime.datetime.now())
    mock_db.execute.return_value = mock_result
    
    response = client.get("/api/device/status?sn=NCD8242500682")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["status"] == "online"


def test_iclock_cdata_unregistered_member() -> None:
    from sqlalchemy.exc import IntegrityError
    mock_db.execute.reset_mock()
    
    mock_result_tenant = MagicMock()
    mock_result_tenant.fetchone.return_value = ("gym_1",)
    
    mock_db.execute.side_effect = [
        MagicMock(),  # update_device_last_seen execute
        mock_result_tenant,
        IntegrityError("insert violates fkey", params=None, orig=None)
    ]
    
    response = client.post("/iclock/cdata?SN=NCD8242500682&table=ATTLOG", content="5555\t2026-06-07\t17:04:10\t255\t15")
    assert response.status_code == status.HTTP_200_OK
    assert response.text == "OK"


def test_iclock_cdata_unregistered_member_no_db_record() -> None:
    mock_db.execute.reset_mock()
    
    mock_result_tenant = MagicMock()
    mock_result_tenant.fetchone.return_value = ("gym_1",)
    
    mock_result_member = MagicMock()
    mock_result_member.fetchone.return_value = None  # Not in database
    
    mock_db.execute.side_effect = [
        MagicMock(),  # update_device_last_seen execute
        mock_result_tenant,
        MagicMock(),  # att_query execute
        mock_result_member
    ]
    
    response = client.post("/iclock/cdata?SN=NCD8242500682&table=ATTLOG", content="6666\t2026-06-07\t17:04:10\t255\t15")
    assert response.status_code == status.HTTP_200_OK
    assert response.text == "OK"
    assert mock_db.execute.call_count == 4


def test_iclock_cdata_superadmin_bypass() -> None:
    mock_db.execute.reset_mock()
    
    mock_result_tenant = MagicMock()
    mock_result_tenant.fetchone.return_value = ("gym_1",)
    
    mock_db.execute.side_effect = [
        MagicMock(),  # update_device_last_seen execute
        mock_result_tenant,
        MagicMock()   # att_query execute
    ]
    
    response = client.post("/iclock/cdata?SN=NCD8242500682&table=ATTLOG", content="111\t2026-06-07\t17:04:10\t255\t15")
    assert response.status_code == status.HTTP_200_OK
    assert response.text == "OK"
    assert mock_db.execute.call_count == 3



