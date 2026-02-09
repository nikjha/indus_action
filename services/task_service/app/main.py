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
import jwt
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
    title="Task Service",
    description="Task management and assignment service",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("task-service")

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
                ("task-service", request.method, str(request.url), int(response.status_code), int(duration_ms), _json.dumps(req_headers), body_text, _json.dumps(resp_headers), resp_text),
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

class Task(BaseModel):
    id: int
    title: str
    rules: dict[str, Any]
    uid: str | None = None

tasks: dict[int, Task] = {}
_redis_client: redis.Redis | None = None
_db_conn = None

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

def get_db():
    global _db_conn
    if _db_conn:
        return _db_conn
    try:
        _db_conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "db"),
            port=int(os.getenv("DB_PORT", "5433")),
            user=os.getenv("DB_USER", "app"),
            password=os.getenv("DB_PASSWORD", "app"),
            dbname=os.getenv("DB_NAME", "appdb"),
        )
        cur = _db_conn.cursor()
        cur.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                department TEXT,
                experience_years INTEGER,
                active_task_count INTEGER,
                location TEXT,
                uid UUID,
                email TEXT,
                role TEXT
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT,
                rules JSONB NOT NULL DEFAULT '{}'::jsonb,
                uid UUID NOT NULL DEFAULT uuid_generate_v4(),
                status TEXT NOT NULL DEFAULT 'TODO' CHECK (status IN ('TODO','IN_PROGRESS','DONE','WAITING_FOR_ELIGIBLE_USER')),
                priority INTEGER NOT NULL DEFAULT 0,
                due_date DATE
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS assignments (
                id SERIAL PRIMARY KEY,
                task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                status TEXT NOT NULL DEFAULT 'ASSIGNED',
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                task_uid UUID,
                user_uid UUID
            );
            """
        )
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
        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_assignments_task_unique ON assignments (task_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_assignments_user ON assignments (user_id);")
        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_assignments_task_uid_unique ON assignments (task_uid);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_assignments_user_uid ON assignments (user_uid);")
        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_uid_unique ON tasks (uid);")
        _db_conn.commit()
        return _db_conn
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}", exc_info=True)
        return None

def parse_token(auth: str | None) -> dict[str, str]:
    if not auth or not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = auth.removeprefix("Bearer ").strip()
    secret = os.getenv("AUTH_SECRET", "dev-secret")
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        role = payload.get("role")
        sub = payload.get("sub")
        if not role or not sub:
            raise HTTPException(status_code=401, detail="Invalid token payload")
        return {"username": sub, "role": role}
    except Exception as err:
        raise HTTPException(status_code=401, detail="Invalid token") from err

@app.post("/tasks")
async def create_task(req: Request, authorization: str | None = Header(default=None)):
    info = parse_token(authorization)
    if info["role"] != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin role required")
    data = await req.json()
    task = Task(**{k: v for k, v in data.items() if k in {"id", "title", "rules"}})
    tasks[task.id] = task
    db = get_db()
    if db:
        cur = db.cursor()
        cur.execute(
            "INSERT INTO tasks (id, title, description, rules, status, priority, due_date) VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO UPDATE SET title=EXCLUDED.title, description=EXCLUDED.description, rules=EXCLUDED.rules, status=EXCLUDED.status, priority=EXCLUDED.priority, due_date=EXCLUDED.due_date;",
            (
                task.id,
                task.title,
                data.get("description"),
                json.dumps(task.rules),
                data.get("status") or "TODO",
                int(data.get("priority") or 0),
                data.get("due_date"),
            ),
        )
        db.commit()
    rc = get_redis()
    if rc:
        rc.lpush("task_assignment_queue", json.dumps({"task_id": task.id, "rules": task.rules}))
    else:
        async with httpx.AsyncClient() as client:
            await client.post("http://eligibility-engine:8004/evaluate", json={"task_id": task.id, "rules": task.rules})
    return {"status": "accepted", "task_id": task.id}

@app.patch("/tasks/{task_id}")
async def update_task(task_id: int, req: Request, authorization: str | None = Header(default=None)):
    info = parse_token(authorization)
    if info["role"] != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin role required")
    data = await req.json()
    title = data.get("title")
    rules = data.get("rules")
    description = data.get("description")
    status = data.get("status")
    priority = data.get("priority")
    due_date = data.get("due_date")
    if title is None and rules is None and description is None and status is None and priority is None and due_date is None:
        raise HTTPException(status_code=400, detail="Nothing to update")
    t = tasks.get(task_id)
    if t:
        if title is not None:
            t.title = title
        if rules is not None:
            t.rules = rules
        tasks[task_id] = t
    db = get_db()
    if db:
        cur = db.cursor()
        cur.execute(
            "UPDATE tasks SET title=COALESCE(%s,title), description=COALESCE(%s,description), rules=COALESCE(%s,rules), status=COALESCE(%s,status), priority=COALESCE(%s,priority), due_date=COALESCE(%s,due_date) WHERE id=%s;",
            (
                title,
                description,
                json.dumps(rules) if rules is not None else None,
                status,
                int(priority) if priority is not None else None,
                due_date,
                task_id,
            ),
        )
        db.commit()
    rc = get_redis()
    if rc and rules is not None:
        rc.lpush("task_assignment_queue", json.dumps({"task_id": task_id, "rules": rules}))
    return {"updated": True}

@app.delete("/tasks/{task_id}")
async def delete_task(task_id: int, authorization: str | None = Header(default=None)):
    info = parse_token(authorization)
    if info["role"] != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin role required")
    tasks.pop(task_id, None)
    db = get_db()
    if db:
        cur = db.cursor()
        cur.execute("DELETE FROM tasks WHERE id=%s;", (task_id,))
        db.commit()
    rc = get_redis()
    if rc:
        try:
            rc.delete(f"eligible_users:{task_id}")
        except Exception:
            pass
    return {"deleted": True}
@app.get("/tasks")
async def list_tasks(authorization: str | None = Header(default=None)):
    parse_token(authorization)
    db = get_db()
    if db:
        cur = db.cursor()
        cur.execute("SELECT id, title, description, rules, uid, status, priority, due_date FROM tasks ORDER BY id;")
        rows = cur.fetchall()
        return [{"id": r[0], "title": r[1], "description": r[2], "rules": r[3], "uid": str(r[4]) if r[4] else None, "status": r[5], "priority": r[6], "due_date": str(r[7]) if r[7] else None} for r in rows]
    return [{"id": t.id, "title": t.title, "rules": t.rules} for t in tasks.values()]

@app.get("/tasks/{task_id}")
async def get_task(task_id: int, authorization: str | None = Header(default=None)):
    parse_token(authorization)
    db = get_db()
    if db:
        cur = db.cursor()
        cur.execute("SELECT id, title, description, rules, uid, status, priority, due_date FROM tasks WHERE id=%s;", (task_id,))
        r = cur.fetchone()
        if r:
            return {"id": r[0], "title": r[1], "description": r[2], "rules": r[3], "uid": str(r[4]) if r[4] else None, "status": r[5], "priority": r[6], "due_date": str(r[7]) if r[7] else None}
        raise HTTPException(status_code=404, detail="Not found")
    t = tasks.get(task_id)
    if t:
        return {"id": t.id, "title": t.title, "rules": t.rules}
    raise HTTPException(status_code=404, detail="Not found")
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
        title="Task Service",
        version="1.0.0",
        description="Task management and assignment service",
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
                title="Task Service - Swagger UI",
                swagger_ui_parameters={"persistAuthorization": True}
            )
        except HTTPException:
            pass
    
    # Fall back to basic auth
    _check_basic_auth(authorization)
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title="Task Service - Swagger UI",
        swagger_ui_parameters={"persistAuthorization": True}
    )

@app.get("/redoc", tags=["Documentation"])
def protected_redoc(authorization: str | None = Header(default=None)):
    """ReDoc documentation. Requires Bearer token or basic auth."""
    # Try Bearer token first
    if authorization and authorization.startswith("Bearer "):
        try:
            validate_bearer_token(authorization)
            return get_redoc_html(openapi_url="/openapi.json", title="Task Service - ReDoc")
        except HTTPException:
            pass
    
    # Fall back to basic auth
    _check_basic_auth(authorization)
    return get_redoc_html(openapi_url="/openapi.json", title="Task Service - ReDoc")

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
    return {"status": "ok", "service": "task-service"}

@app.get("/tasks/{task_id}/eligible-users")
async def eligible_users(task_id: int, authorization: str | None = Header(default=None)):
    parse_token(authorization)
    async with httpx.AsyncClient() as client:
        r = await client.get(f"http://eligibility-engine:8004/tasks/{task_id}/eligible-users")
    return r.json()

@app.get("/my-eligible-tasks")
async def my_tasks(user_id: int, authorization: str | None = Header(default=None)):
    parse_token(authorization)
    db = get_db()
    if not db:
        return {"user_id": user_id, "tasks": []}
    cur = db.cursor()
    cur.execute(
        "SELECT t.id, t.title, t.rules, t.uid, a.status, a.updated_at FROM assignments a JOIN tasks t ON a.task_id=t.id WHERE a.user_id=%s ORDER BY a.updated_at DESC;",
        (user_id,),
    )
    rows = cur.fetchall()
    return {
        "user_id": user_id,
        "tasks": [
            {
                "id": r[0],
                "title": r[1],
                "rules": r[2],
                "uid": str(r[3]) if r[3] else None,
                "status": r[4],
                "updated_at": str(r[5]),
            }
            for r in rows
        ],
    }

@app.post("/tasks/recompute-eligibility")
async def recompute(req: Request, authorization: str | None = Header(default=None)):
    info = parse_token(authorization)
    if info["role"] != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin role required")
    data = await req.json()
    async with httpx.AsyncClient() as client:
        r = await client.post("http://eligibility-engine:8004/recompute", json=data)
    return r.json()

@app.post("/assignments")
async def upsert_assignment(req: Request):
    data = await req.json()
    task_id_raw = data.get("task_id")
    user_id_raw = data.get("user_id")
    task_uid = data.get("task_uid")
    user_uid = data.get("user_uid")
    status = data.get("status") or "ASSIGNED"
    db = get_db()
    if not db:
        raise HTTPException(status_code=500, detail="DB unavailable")
    cur = db.cursor()
    # resolve IDs via UUIDs if provided
    task_id = int(task_id_raw) if task_id_raw is not None else None
    user_id = int(user_id_raw) if user_id_raw is not None else None
    if task_id is None and task_uid:
        cur.execute("SELECT id FROM tasks WHERE uid=%s;", (task_uid,))
        r = cur.fetchone()
        if not r:
            raise HTTPException(status_code=404, detail="Task UID not found")
        task_id = int(r[0])
    if user_id is None and user_uid:
        cur.execute("SELECT id FROM users WHERE uid=%s;", (user_uid,))
        r = cur.fetchone()
        if not r:
            raise HTTPException(status_code=404, detail="User UID not found")
        user_id = int(r[0])
    if task_id is None or user_id is None:
        raise HTTPException(status_code=400, detail="Missing task_id/user_id or task_uid/user_uid")
    cur.execute(
        "INSERT INTO assignments (task_id, user_id, status, task_uid, user_uid) VALUES (%s,%s,%s,%s,%s) ON CONFLICT (task_id) DO UPDATE SET user_id=EXCLUDED.user_id, status=EXCLUDED.status, updated_at=NOW(), task_uid=COALESCE(EXCLUDED.task_uid, assignments.task_uid), user_uid=COALESCE(EXCLUDED.user_uid, assignments.user_uid);",
        (task_id, user_id, status, task_uid, user_uid),
    )
    db.commit()
    return {"task_id": task_id, "user_id": user_id, "task_uid": task_uid, "user_uid": user_uid, "status": status}

@app.get("/assignments")
async def list_assignments(authorization: str | None = Header(default=None)):
    parse_token(authorization)
    db = get_db()
    if not db:
        return []
    cur = db.cursor()
    cur.execute("SELECT id, task_id, user_id, status, created_at, updated_at, task_uid, user_uid FROM assignments ORDER BY id DESC;")
    rows = cur.fetchall()
    return [{"id": r[0], "task_id": r[1], "user_id": r[2], "status": r[3], "created_at": str(r[4]), "updated_at": str(r[5]), "task_uid": str(r[6]) if r[6] else None, "user_uid": str(r[7]) if r[7] else None} for r in rows]

@app.get("/assignments/{task_id}")
async def get_assignment(task_id: int, authorization: str | None = Header(default=None)):
    parse_token(authorization)
    db = get_db()
    if not db:
        raise HTTPException(status_code=404, detail="Not found")
    cur = db.cursor()
    cur.execute("SELECT id, task_id, user_id, status, created_at, updated_at, task_uid, user_uid FROM assignments WHERE task_id=%s;", (task_id,))
    r = cur.fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Not found")
    return {"id": r[0], "task_id": r[1], "user_id": r[2], "status": r[3], "created_at": str(r[4]), "updated_at": str(r[5]), "task_uid": str(r[6]) if r[6] else None, "user_uid": str(r[7]) if r[7] else None}

@app.get("/assignments/user/{user_id}")
async def list_assignments_by_user(user_id: int, authorization: str | None = Header(default=None)):
    parse_token(authorization)
    db = get_db()
    if not db:
        return []
    cur = db.cursor()
    cur.execute("SELECT id, task_id, user_id, status, created_at, updated_at, task_uid, user_uid FROM assignments WHERE user_id=%s ORDER BY id DESC;", (user_id,))
    rows = cur.fetchall()
    return [{"id": r[0], "task_id": r[1], "user_id": r[2], "status": r[3], "created_at": str(r[4]), "updated_at": str(r[5]), "task_uid": str(r[6]) if r[6] else None, "user_uid": str(r[7]) if r[7] else None} for r in rows]

@app.patch("/assignments/{task_id}/status")
async def update_assignment_status(task_id: int, req: Request, authorization: str | None = Header(default=None)):
    info = parse_token(authorization)
    if info["role"] != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin role required")
    data = await req.json()
    status = data.get("status")
    if not status:
        raise HTTPException(status_code=400, detail="Missing status")
    db = get_db()
    if not db:
        raise HTTPException(status_code=500, detail="DB unavailable")
    cur = db.cursor()
    cur.execute("UPDATE assignments SET status=%s, updated_at=NOW() WHERE task_id=%s;", (status, task_id))
    db.commit()
    return {"task_id": task_id, "status": status}

@app.patch("/assignments/uid/{task_uid}/status")
async def update_assignment_status_by_uid(task_uid: str, req: Request, authorization: str | None = Header(default=None)):
    info = parse_token(authorization)
    if info["role"] != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin role required")
    data = await req.json()
    status = data.get("status")
    if not status:
        raise HTTPException(status_code=400, detail="Missing status")
    db = get_db()
    if not db:
        raise HTTPException(status_code=500, detail="DB unavailable")
    cur = db.cursor()
    cur.execute("UPDATE assignments SET status=%s, updated_at=NOW() WHERE task_uid=%s;", (status, task_uid))
    db.commit()
    return {"task_uid": task_uid, "status": status}
