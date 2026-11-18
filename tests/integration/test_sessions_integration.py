from uuid import uuid4

import pytest

from app.dao.session_dao import SessionDAO


pytestmark = pytest.mark.integration


def test_session_table_bootstrap_can_run_twice(ddb_client):
    name = "session_test_" + uuid4().hex
    dao = SessionDAO(ddb_client, name)
    try:
        dao.ensure_table()
        dao.ensure_table()
        description = ddb_client.describe_time_to_live(TableName=name)["TimeToLiveDescription"]
        assert description["TimeToLiveStatus"] in ("ENABLED", "ENABLING")
        assert description["AttributeName"] == "ttl"
    finally:
        try:
            ddb_client.delete_table(TableName=name)
        except ddb_client.exceptions.ResourceNotFoundException:
            pass
