import os

import pytest
import requests

INTEGRATION = os.getenv("INTEGRATION") == "1"
BASE = os.getenv("GATEWAY_BASE", "http://localhost:8000")


@pytest.mark.skipif(not INTEGRATION, reason="Integration tests require running stack")
def test_login_and_flow():
    r = requests.post(
        f"{BASE}/login",
        json={"username": "admin1", "password": "x"},
        timeout=10,
    )
    assert r.status_code == 200
    tok = r.json()["access_token"]
    # create task
    r2 = requests.post(
        f"{BASE}/tasks",
        headers={"Authorization": f"Bearer {tok}"},
        json={"id": 9, "title": "Task9", "rules": {"department": "Finance", "min_experience": 2, "max_active_tasks": 5}},
        timeout=10,
    )
    assert r2.status_code == 200
    # eligible users
    r3 = requests.get(
        f"{BASE}/tasks/9/eligible-users",
        headers={"Authorization": f"Bearer {tok}"},
        timeout=10,
    )
    assert r3.status_code == 200
    # my eligible tasks
    r4 = requests.get(
        f"{BASE}/my-eligible-tasks",
        params={"user_id": 4},
        headers={"Authorization": f"Bearer {tok}"},
        timeout=10,
    )
    assert r4.status_code == 200
