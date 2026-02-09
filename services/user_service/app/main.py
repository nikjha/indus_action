import base64
import hashlib
import json
import logging
import os
import secrets
import sys
import time

import httpx
import psycopg2
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel

# Add services directory to path for shared imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from shared_auth import validate_bearer_token

app = FastAPI(
    title="User Service",
    description="User management service",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("user-service")

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
    try:
        parsed = json.loads(body_text or "{}")
        if isinstance(parsed, dict) and "password" in parsed:
            parsed["password"] = "REDACTED"
            body_text = json.dumps(parsed)
    except Exception:
        pass
    logger.info(json.dumps({"type": "request", "method": request.method, "path": str(request.url), "headers": req_headers, "body": body_text}))
    response = await call_next(request)
    resp_body = b""
    async for chunk in response.body_iterator:
        resp_body += chunk
    duration_ms = (time.perf_counter() - start) * 1000
    resp_text = resp_body.decode("utf-8", errors="replace")
    resp_headers = _redact_headers(dict(response.headers))
    logger.info(json.dumps({"type": "response", "method": request.method, "path": str(request.url), "status": response.status_code, "time_ms": int(duration_ms), "headers": resp_headers, "body": resp_text}))
    db = get_db()
    if db:
        try:
            cur = db.cursor()
            cur.execute(
                "INSERT INTO access_logs (service, method, path, status, time_ms, req_headers, req_body, resp_headers, resp_body) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s::jsonb,%s);",
                ("user-service", request.method, str(request.url), int(response.status_code), int(duration_ms), json.dumps(req_headers), body_text, json.dumps(resp_headers), resp_text),
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

class User(BaseModel):
    id: int
    name: str
    department: str
    experience_years: int
    active_task_count: int = 0
    location: str | None = None
    uid: str | None = None
    email: str | None = None
    role: str | None = "USER"
    password: str | None = None

users: list[User] = []
conn = None

def get_db():
    global conn
    if conn:
        return conn
    try:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "db"),
            port=int(os.getenv("DB_PORT", "5433")),
            user=os.getenv("DB_USER", "app"),
            password=os.getenv("DB_PASSWORD", "app"),
            dbname=os.getenv("DB_NAME", "appdb"),
        )
        cur = conn.cursor()
        cur.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                department TEXT NOT NULL,
                experience_years INTEGER NOT NULL,
                active_task_count INTEGER NOT NULL,
                location TEXT,
                uid UUID NOT NULL DEFAULT uuid_generate_v4(),
                email TEXT,
                role TEXT NOT NULL DEFAULT 'USER',
                password_hash TEXT
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
        conn.commit()
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}", exc_info=True)
        return None

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
        title="User Service",
        version="1.0.0",
        description="User management service",
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
                title="User Service - Swagger UI",
                swagger_ui_parameters={"persistAuthorization": True}
            )
        except HTTPException:
            pass
    
    # Fall back to basic auth
    _check_basic_auth(authorization)
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title="User Service - Swagger UI",
        swagger_ui_parameters={"persistAuthorization": True}
    )

@app.get("/redoc", tags=["Documentation"])
def protected_redoc(authorization: str | None = Header(default=None)):
    """ReDoc documentation. Requires Bearer token or basic auth."""
    # Try Bearer token first
    if authorization and authorization.startswith("Bearer "):
        try:
            validate_bearer_token(authorization)
            return get_redoc_html(openapi_url="/openapi.json", title="User Service - ReDoc")
        except HTTPException:
            pass
    
    # Fall back to basic auth
    _check_basic_auth(authorization)
    return get_redoc_html(openapi_url="/openapi.json", title="User Service - ReDoc")

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
    return {"status": "ok", "service": "user-service"}

@app.get("/users")
def list_users():
    db = get_db()
    if db:
        cur = db.cursor()
        cur.execute("SELECT id, name, department, experience_years, active_task_count, location, uid, email, role FROM users;")
        rows = cur.fetchall()
        return [
            {
                "id": r[0],
                "name": r[1],
                "department": r[2],
                "experience_years": r[3],
                "active_task_count": r[4],
                "location": r[5],
                "uid": str(r[6]) if r[6] else None,
                "email": r[7],
                "role": r[8],
            }
            for r in rows
        ]
    return users

@app.post("/users")
def create_user(user: User):
    db = get_db()
    if db:
        cur = db.cursor()
        pwd_hash = None
        if user.password:
            # Hash using PBKDF2-SHA256 with per-user salt
            salt = secrets.token_hex(16)
            iterations = 260000
            dk = hashlib.pbkdf2_hmac("sha256", user.password.encode(), salt.encode(), iterations)
            pwd_hash = f"pbkdf2_sha256${iterations}${salt}${dk.hex()}"
        cur.execute(
            "INSERT INTO users (id, name, department, experience_years, active_task_count, location, email, role, password_hash) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name, department=EXCLUDED.department, experience_years=EXCLUDED.experience_years, active_task_count=EXCLUDED.active_task_count, location=EXCLUDED.location, email=EXCLUDED.email, role=EXCLUDED.role, password_hash=COALESCE(EXCLUDED.password_hash, users.password_hash);",
            (user.id, user.name, user.department, user.experience_years, user.active_task_count, user.location, user.email, user.role or "USER", pwd_hash),
        )
        db.commit()
        # fetch uid for response
        cur.execute("SELECT uid FROM users WHERE id=%s;", (user.id,))
        r = cur.fetchone()
        out = user.dict()
        out["uid"] = str(r[0]) if r and r[0] else None
        out.pop("password", None)
        return out
    users.append(user)
    return user

@app.patch("/users/{user_id}")
def update_user(user_id: int, user: User):
    db = get_db()
    if db:
        cur = db.cursor()
        pwd_hash = None
        if user.password:
            salt = secrets.token_hex(16)
            iterations = 260000
            dk = hashlib.pbkdf2_hmac("sha256", user.password.encode(), salt.encode(), iterations)
            pwd_hash = f"pbkdf2_sha256${iterations}${salt}${dk.hex()}"
        cur.execute(
            "UPDATE users SET name=%s, department=%s, experience_years=%s, active_task_count=%s, location=%s, email=%s, role=%s, password_hash=COALESCE(%s,password_hash) WHERE id=%s;",
            (user.name, user.department, user.experience_years, user.active_task_count, user.location, user.email, user.role or "USER", pwd_hash, user_id),
        )
        db.commit()
        # Trigger targeted recompute for impacted tasks (department-based)
        try:
            cur.execute("SELECT id, rules FROM tasks WHERE (rules->>'department') = %s;", (user.department,))
            rows = cur.fetchall()
            for r in rows:
                tid, rules = int(r[0]), r[1]
                try:
                    httpx.post("http://eligibility-engine:8004/evaluate", json={"task_id": tid, "rules": rules}, timeout=5.0)
                except Exception:
                    pass
        except Exception:
            pass
        return {"updated": True}
    for i, u in enumerate(users):
        if u.id == user_id:
            users[i] = user
            return {"updated": True}
    raise HTTPException(status_code=404, detail="Not found")

class VerifyLogin(BaseModel):
    username: str
    password: str

@app.post("/users/verify-login")
def verify_login(payload: VerifyLogin):
    db = get_db()
    if not db:
        raise HTTPException(status_code=500, detail="DB unavailable")
    cur = db.cursor()
    cur.execute("SELECT id, name, role, password_hash, uid FROM users WHERE name=%s;", (payload.username,))
    r = cur.fetchone()
    if not r or not r[3]:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    try:
        _, iter_str, salt, hexdigest = r[3].split("$")
        iterations = int(iter_str)
        dk = hashlib.pbkdf2_hmac("sha256", payload.password.encode(), salt.encode(), iterations)
        ok = secrets.compare_digest(dk.hex(), hexdigest)
    except Exception:
        ok = False
    if not ok:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"id": r[0], "name": r[1], "role": r[2], "uid": str(r[4]) if r[4] else None}

@app.delete("/users/{user_id}")
def delete_user(user_id: int):
    db = get_db()
    if db:
        cur = db.cursor()
        cur.execute("DELETE FROM users WHERE id=%s;", (user_id,))
        db.commit()
        return {"deleted": True}
    for i, u in enumerate(users):
        if u.id == user_id:
            users.pop(i)
            return {"deleted": True}
    raise HTTPException(status_code=404, detail="Not found")
