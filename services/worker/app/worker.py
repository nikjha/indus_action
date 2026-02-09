import json
import os
import time

import httpx
import redis


def loop():
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    rc = redis.from_url(redis_url, decode_responses=True)
    item = rc.blpop(["task_assignment_queue", "eligibility_recompute_queue"], timeout=5)
    if not item:
        time.sleep(1)
        return
    _, payload = item
    try:
        data = json.loads(payload)
    except Exception:
        return
    task_id = data.get("task_id")
    rules = data.get("rules") or {}
    with httpx.Client() as client:
        client.post("http://eligibility-engine:8004/evaluate", json={"task_id": task_id, "rules": rules})

if __name__ == "__main__":
    while True:
        loop()
