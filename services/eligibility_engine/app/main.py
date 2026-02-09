import base64
import json
import json as _json
import logging
import os
import secrets
import sys
import time
from typing import Any

import httpx
import psycopg2
import redis
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel

# Add services directory to path for shared imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from shared_auth import validate_bearer_token

app = FastAPI(
    title="Eligibility Engine",
    description="Determines eligible users for tasks based on rules",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("eligibility-engine")

_db_conn = None

def get_db():
    global _db_conn
    if _db_conn:
        return _db_conn
    try:
        _db_conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "db"),
            port=int(os.getenv("DB_PORT", "5433")),
            user=os.getenv("DB_USER", "app"),
            password=os.getenv("DB_PASSWORD", "app#123#"),
            dbname=os.getenv("DB_NAME", "taskdb"),
        )
        cur = _db_conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS access_logs (
                id BIGSERIAL PRIMARY KEY,
                service TEXT NOT NULL,
                method TEXT NOT NULL,
                path TEXT NOT NULL,
                status INTEGER,
                time_ms INTEGER,
                req_headers JSONB,
                req_body TEXT,
                resp_headers JSONB,
                resp_body TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
            """
        )
        _db_conn.commit()
        return _db_conn
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}", exc_info=True)
        return None

def _redact_headers(h: dict[str, str]) -> dict[str, str]:
    out = dict(h)
    for k in list(out.keys()):
        if k.lower() in {"authorization", "cookie", "set-cookie"}:
            out[k] = "REDACTED"
    return out

@app.middleware("http")
async def log_middleware(request: Request, call_next):
    start = time.perf_counter()
    req_headers = _redact_headers(dict(request.headers))
    body_bytes = await request.body()
    body_text = body_bytes.decode("utf-8", errors="replace")
    logger.info(_json.dumps({"type": "request", "method": request.method, "path": str(request.url), "headers": req_headers, "body": body_text}))
    response = await call_next(request)
    resp_body = b""
    async for chunk in response.body_iterator:
        resp_body += chunk
    duration_ms = (time.perf_counter() - start) * 1000
    resp_text = resp_body.decode("utf-8", errors="replace")
    resp_headers = _redact_headers(dict(response.headers))
    logger.info(_json.dumps({"type": "response", "method": request.method, "path": str(request.url), "status": response.status_code, "time_ms": int(duration_ms), "headers": resp_headers, "body": resp_text}))
    db = get_db()
    if db:
        try:
            cur = db.cursor()
            cur.execute(
                "INSERT INTO access_logs (service, method, path, status, time_ms, req_headers, req_body, resp_headers, resp_body) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s::jsonb,%s);",
                ("eligibility-engine", request.method, str(request.url), int(response.status_code), int(duration_ms), _json.dumps(req_headers), body_text, _json.dumps(resp_headers), resp_text),
            )
            db.commit()
            logger.debug(f"Access log inserted for {request.method} {request.url}")
        except Exception as e:
            logger.error(f"Failed to insert access log: {e}", exc_info=True)
            try:
                db.rollback()
            except Exception:
                pass
    else:
        logger.warning("Database connection not available for access logging")

    async def body_iterator():
        yield resp_body
    response.body_iterator = body_iterator()
    return response

class RulePayload(BaseModel):
    task_id: int
    rules: dict[str, Any]

eligible_users_by_task: dict[int, list[dict[str, Any]]] = {}
eligible_tasks_by_user: dict[int, list[int]] = {}
_redis_client: redis.Redis | None = None

def get_redis() -> redis.Redis | None:
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379")
    try:
        _redis_client = redis.from_url(redis_url, decode_responses=True)
        _redis_client.ping()
        return _redis_client
    except Exception:
        return None

def check_user_rules(user: dict[str, Any], rules: dict[str, Any]) -> bool:
    d = rules.get("department")
    if d and user.get("department") != d:
        return False
    min_exp = rules.get("min_experience")
    if isinstance(min_exp, int) and int(user.get("experience_years", 0)) < min_exp:
        return False
    max_active = rules.get("max_active_tasks")
    if isinstance(max_active, int) and int(user.get("active_task_count", 0)) > max_active:
        return False
    return True

async def fetch_users() -> list[dict[str, Any]]:
    async with httpx.AsyncClient() as client:
        r = await client.get("http://user-service:8002/users")
        return r.json()

def score_user(user: dict[str, Any]) -> int:
    return (100 - int(user.get("active_task_count", 0))) * 3 + int(user.get("experience_years", 0)) * 2

@app.post("/evaluate")
async def evaluate(payload: RulePayload):
    rc = get_redis()
    if rc:
        lock_key = f"task_lock:{payload.task_id}"
        # acquire lock if available
        if not rc.set(lock_key, "1", nx=True, ex=30):
            return {"task_id": payload.task_id, "status": "locked"}
    users = await fetch_users()
    elig = [u for u in users if check_user_rules(u, payload.rules)]
    elig_sorted = sorted(elig, key=score_user, reverse=True)
    eligible_users_by_task[payload.task_id] = elig_sorted
    if rc:
        rc.set(f"eligible_users:{payload.task_id}", json.dumps(elig_sorted))
    db = get_db()
    if db:
        try:
            cur = db.cursor()
            # refresh eligibility entries for this task
            cur.execute("DELETE FROM task_eligible_users WHERE task_id=%s;", (payload.task_id,))
            for u in elig_sorted:
                uid = int(u.get("id"))
                cur.execute("INSERT INTO task_eligible_users (task_id, user_id, score) VALUES (%s,%s,%s) ON CONFLICT (task_id, user_id) DO UPDATE SET score=EXCLUDED.score, computed_at=NOW();", (payload.task_id, uid, score_user(u)))
            db.commit()
        except Exception:
            pass
    for u in elig_sorted:
        uid = int(u.get("id"))
        arr = eligible_tasks_by_user.get(uid, [])
        if payload.task_id not in arr:
            arr.append(payload.task_id)
        eligible_tasks_by_user[uid] = arr
        if rc:
            rc.sadd(f"user_eligible_tasks:{uid}", payload.task_id)
    if rc:
        try:
            rc.delete(f"task_lock:{payload.task_id}")
        except Exception:
            pass
    if elig_sorted:
        top = elig_sorted[0]
        async with httpx.AsyncClient() as client:
            try:
                await client.post("http://task-service:8003/assignments", json={"task_id": payload.task_id, "user_id": int(top.get("id")), "status": "ASSIGNED"})
            except Exception:
                pass
    return {"task_id": payload.task_id, "eligible_count": len(elig_sorted), "assigned_user_id": int(elig_sorted[0].get("id")) if elig_sorted else None}

@app.get("/tasks/{task_id}/eligible-users")
def eligible_users(task_id: int):
    rc = get_redis()
    if rc:
        cached = rc.get(f"eligible_users:{task_id}")
        if cached:
            try:
                return {"task_id": task_id, "users": json.loads(cached)}
            except Exception:
                pass
    return {"task_id": task_id, "users": eligible_users_by_task.get(task_id, [])}

@app.get("/my-eligible-tasks")
def my_tasks(user_id: int):
    rc = get_redis()
    if rc:
        tasks = rc.smembers(f"user_eligible_tasks:{user_id}")
        if tasks:
            try:
                return {"user_id": user_id, "tasks": [int(t) for t in tasks]}
            except Exception:
                pass
    return {"user_id": user_id, "tasks": eligible_tasks_by_user.get(user_id, [])}

@app.post("/recompute")
async def recompute(req: Request):
    data = await req.json()
    task_id = int(data.get("task_id"))
    rules = data.get("rules") or {}
    return await evaluate(RulePayload(task_id=task_id, rules=rules))

def _check_basic_auth(auth_header: str | None):
    user = os.getenv("DOCS_USER", "docs")
    pwd = os.getenv("DOCS_PASS", "docs123")
    expected = "Basic " + base64.b64encode(f"{user}:{pwd}".encode()).decode()
    if not auth_header or not secrets.compare_digest(auth_header, expected):
        raise HTTPException(status_code=401, detail="Unauthorized", headers={"WWW-Authenticate": "Basic"})

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title="Eligibility Engine",
        version="1.0.0",
        description="Determines eligible users for tasks based on rules",
        routes=app.routes,
    )
    
    # Add security schemes
    openapi_schema["components"]["securitySchemes"] = {
        "Bearer": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "JWT Bearer token from /login endpoint",
        }
    }
    
    # Apply Bearer security globally
    openapi_schema["security"] = [{"Bearer": []}]
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

@app.get("/docs", tags=["Documentation"])
def protected_docs(authorization: str | None = Header(default=None)):
    """Swagger UI documentation. Requires Bearer token or basic auth."""
    # Try Bearer token first
    if authorization and authorization.startswith("Bearer "):
        try:
            validate_bearer_token(authorization)
            return get_swagger_ui_html(
                openapi_url="/openapi.json",
                title="Eligibility Engine - Swagger UI",
                swagger_ui_parameters={"persistAuthorization": True}
            )
        except HTTPException:
            pass
    
    # Fall back to basic auth
    _check_basic_auth(authorization)
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title="Eligibility Engine - Swagger UI",
        swagger_ui_parameters={"persistAuthorization": True}
    )

@app.get("/redoc", tags=["Documentation"])
def protected_redoc(authorization: str | None = Header(default=None)):
    """ReDoc documentation. Requires Bearer token or basic auth."""
    # Try Bearer token first
    if authorization and authorization.startswith("Bearer "):
        try:
            validate_bearer_token(authorization)
            return get_redoc_html(openapi_url="/openapi.json", title="Eligibility Engine - ReDoc")
        except HTTPException:
            pass
    
    # Fall back to basic auth
    _check_basic_auth(authorization)
    return get_redoc_html(openapi_url="/openapi.json", title="Eligibility Engine - ReDoc")

@app.get("/openapi.json", tags=["Documentation"])
def protected_openapi(authorization: str | None = Header(default=None)):
    """OpenAPI schema. Requires Bearer token or basic auth."""
    # Try Bearer token first
    if authorization and authorization.startswith("Bearer "):
        try:
            validate_bearer_token(authorization)
            return app.openapi()
        except HTTPException:
            pass
    
    # Fall back to basic auth
    _check_basic_auth(authorization)
    return app.openapi()

@app.get("/health")
def health():
    return {"status": "ok", "service": "eligibility-engine"}
