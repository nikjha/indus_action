import base64
import json
import logging
import os
import secrets
import sys
import time
from typing import Any

import httpx
import jwt
import psycopg2
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel

# Load environment configuration for local development and Docker
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Add services directory to path for shared imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from shared_auth import validate_bearer_token


# Request/Response Schemas
class LoginRequest(BaseModel):
    username: str
    password: str

class UserSchema(BaseModel):
    id: int | None = None
    name: str
    department: str
    experience_years: int
    active_task_count: int | None = 0

class TaskSchema(BaseModel):
    id: int | None = None
    title: str
    rules: dict[str, Any]
    uid: str | None = None
    description: str | None = None
    status: str | None = None
    priority: int | None = None
    due_date: str | None = None

class AssignmentSchema(BaseModel):
    task_id: int | None = None
    user_id: int | None = None
    task_uid: str | None = None
    user_uid: str | None = None
    status: str | None = "ASSIGNED"

class RecomputePayload(BaseModel):
    rules: dict[str, Any] | None = {}

app = FastAPI(
    title="API Gateway",
    description="API Gateway for all microservices",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration management
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s"
)
logger = logging.getLogger("api-gateway")

logger.info(f"Starting API Gateway (Environment: {ENVIRONMENT}, Debug: {DEBUG})")

_db_conn = None

def get_db():
    """Get or create database connection with automatic retry for local development"""
    global _db_conn
    if _db_conn:
        try:
            # Test connection
            cursor = _db_conn.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            return _db_conn
        except Exception as e:
            logger.warning(f"Database connection lost: {e}. Reconnecting...")
            _db_conn = None
    
    try:
        db_host = os.getenv("DB_HOST", "db")
        db_port = int(os.getenv("DB_PORT", "5433"))
        db_user = os.getenv("DB_USER", "app")
        db_password = os.getenv("DB_PASSWORD", "app")
        db_name = os.getenv("DB_NAME", "appdb")
        
        logger.debug(f"Connecting to database at {db_host}:{db_port}/{db_name}")
        
        _db_conn = psycopg2.connect(
            host=db_host,
            port=db_port,
            user=db_user,
            password=db_password,
            dbname=db_name,
            connect_timeout=5,
            autocommit=False
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
        logger.info("Database connected and access_logs table ready")
        return _db_conn
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
        title="API Gateway",
        version="1.0.0",
        description="API Gateway for all microservices",
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
                title="API Gateway - Swagger UI",
                swagger_ui_parameters={"persistAuthorization": True}
            )
        except HTTPException:
            pass
    
    # Fall back to basic auth
    _check_basic_auth(authorization)
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title="API Gateway - Swagger UI",
        swagger_ui_parameters={"persistAuthorization": True}
    )

@app.get("/redoc", tags=["Documentation"])
def protected_redoc(authorization: str | None = Header(default=None)):
    """ReDoc documentation. Requires Bearer token or basic auth."""
    # Try Bearer token first
    if authorization and authorization.startswith("Bearer "):
        try:
            validate_bearer_token(authorization)
            return get_redoc_html(openapi_url="/openapi.json", title="API Gateway - ReDoc")
        except HTTPException:
            pass
    
    # Fall back to basic auth
    _check_basic_auth(authorization)
    return get_redoc_html(openapi_url="/openapi.json", title="API Gateway - ReDoc")

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
    logger.info(json.dumps({"type": "request", "method": request.method, "path": str(request.url), "headers": req_headers, "body": body_text}))
    response = await call_next(request)
    resp_body = b""
    async for chunk in response.body_iterator:
        resp_body += chunk
    duration_ms = (time.perf_counter() - start) * 1000
    resp_text = resp_body.decode("utf-8", errors="replace")
    resp_headers = _redact_headers(dict(response.headers))
    logger.info(json.dumps({"type": "response", "method": request.method, "path": str(request.url), "status": response.status_code, "time_ms": int(duration_ms), "headers": resp_headers, "body": resp_text}))
    
    # Log to database
    db = get_db()
    if db:
        try:
            cur = db.cursor()
            cur.execute(
                "INSERT INTO access_logs (service, method, path, status, time_ms, req_headers, req_body, resp_headers, resp_body) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s::jsonb,%s);",
                ("api-gateway", request.method, str(request.url), int(response.status_code), int(duration_ms), json.dumps(req_headers), body_text, json.dumps(resp_headers), resp_text),
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

 

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/env")
def env(req: Request):
    scheme = req.url.scheme or "http"
    host = req.headers.get("host") or "localhost:8000"
    return {"gateway_base": f"{scheme}://{host}"}
    
async def forward(method: str, url: str, body: dict | None = None, headers: dict[str, str] | None = None):
    """Forward request to internal service with environment-aware addressing"""
    start = time.perf_counter()
    safe_headers = _redact_headers(headers or {})
    logger.debug(json.dumps({
        "type": "outbound_request",
        "method": method,
        "url": url,
        "headers": safe_headers,
        "body": json.dumps(body or {})
    }))
    
    # Support both Docker (service-name:port) and local (localhost:port) addressing
    environment_aware_url = url
    if ENVIRONMENT == "local":
        # Convert Docker service names to localhost
        environment_aware_url = url.replace("auth-service:8001", "localhost:8001")
        environment_aware_url = environment_aware_url.replace("user-service:8002", "localhost:8002")
        environment_aware_url = environment_aware_url.replace("task-service:8003", "localhost:8003")
        environment_aware_url = environment_aware_url.replace("eligibility-engine:8004", "localhost:8004")
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            if method.lower() == "get":
                r = await client.get(environment_aware_url, headers=headers)
            elif method.lower() == "post":
                r = await client.post(environment_aware_url, json=body, headers=headers)
            elif method.lower() == "patch":
                r = await client.patch(environment_aware_url, json=body, headers=headers)
            elif method.lower() == "delete":
                r = await client.delete(environment_aware_url, headers=headers)
            else:
                r = await client.request(method.upper(), environment_aware_url, json=body, headers=headers)
    except Exception as e:
        logger.error(f"Error forwarding request to {environment_aware_url}: {e}")
        raise HTTPException(status_code=502, detail="Service unavailable") from e
    
    duration_ms = (time.perf_counter() - start) * 1000
    logger.debug(json.dumps({
        "type": "outbound_response",
        "method": method,
        "url": environment_aware_url,
        "status": r.status_code,
        "time_ms": int(duration_ms),
        "headers": _redact_headers(dict(r.headers)),
        "body": r.text[:500]  # Truncate long responses
    }))
    
    if r.status_code >= 400:
        logger.warning(f"Service returned error: {r.status_code} from {environment_aware_url}")
    
    return r.json()

@app.post("/login")
async def login(payload: LoginRequest):
    return await forward("post", "http://auth-service:8001/login", payload.dict())

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
async def create_task(payload: TaskSchema, authorization: str | None = Header(default=None)):
    info = parse_token(authorization)
    if info["role"] != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin role required")
    return await forward("post", "http://task-service:8003/tasks", payload.dict(), headers={"Authorization": authorization})

@app.get("/tasks/{task_id}/eligible-users")
async def eligible_users(task_id: int, authorization: str | None = Header(default=None)):
    parse_token(authorization)
    return await forward("get", f"http://task-service:8003/tasks/{task_id}/eligible-users", headers={"Authorization": authorization})

@app.get("/my-eligible-tasks")
async def my_tasks(user_id: int | None = None, authorization: str | None = Header(default=None)):
    parse_token(authorization)
    uid = user_id if user_id is not None else 0
    return await forward("get", f"http://task-service:8003/my-eligible-tasks?user_id={uid}", headers={"Authorization": authorization})

@app.post("/tasks/recompute-eligibility")
async def recompute(payload: RecomputePayload, authorization: str | None = Header(default=None)):
    info = parse_token(authorization)
    if info["role"] != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin role required")
    return await forward("post", "http://task-service:8003/tasks/recompute-eligibility", payload.dict(), headers={"Authorization": authorization})

@app.get("/users")
async def list_users(authorization: str | None = Header(default=None)):
    parse_token(authorization)
    return await forward("get", "http://user-service:8002/users", headers={"Authorization": authorization})

@app.post("/users")
async def create_user(payload: UserSchema, authorization: str | None = Header(default=None)):
    info = parse_token(authorization)
    if info["role"] != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin role required")
    return await forward("post", "http://user-service:8002/users", payload.dict(), headers={"Authorization": authorization})

@app.patch("/users/{user_id}")
async def update_user(user_id: int, payload: UserSchema, authorization: str | None = Header(default=None)):
    info = parse_token(authorization)
    if info["role"] != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin role required")
    return await forward("patch", f"http://user-service:8002/users/{user_id}", payload.dict(), headers={"Authorization": authorization})

@app.delete("/users/{user_id}")
async def delete_user(user_id: int, authorization: str | None = Header(default=None)):
    info = parse_token(authorization)
    if info["role"] != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin role required")
    return await forward("delete", f"http://user-service:8002/users/{user_id}", headers={"Authorization": authorization})

@app.get("/tasks")
async def list_tasks(authorization: str | None = Header(default=None)):
    parse_token(authorization)
    return await forward("get", "http://task-service:8003/tasks", headers={"Authorization": authorization})

@app.get("/tasks/{task_id}")
async def get_task(task_id: int, authorization: str | None = Header(default=None)):
    parse_token(authorization)
    return await forward("get", f"http://task-service:8003/tasks/{task_id}", headers={"Authorization": authorization})

@app.patch("/tasks/{task_id}")
async def update_task(task_id: int, payload: TaskSchema, authorization: str | None = Header(default=None)):
    info = parse_token(authorization)
    if info["role"] != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin role required")
    return await forward("patch", f"http://task-service:8003/tasks/{task_id}", payload.dict(), headers={"Authorization": authorization})

@app.delete("/tasks/{task_id}")
async def delete_task(task_id: int, authorization: str | None = Header(default=None)):
    info = parse_token(authorization)
    if info["role"] != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin role required")
    return await forward("delete", f"http://task-service:8003/tasks/{task_id}", headers={"Authorization": authorization})

@app.get("/assignments")
async def list_assignments(authorization: str | None = Header(default=None)):
    info = parse_token(authorization)
    if info["role"] != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin role required")
    return await forward("get", "http://task-service:8003/assignments", headers={"Authorization": authorization})

@app.get("/assignments/{task_id}")
async def get_assignment(task_id: int, authorization: str | None = Header(default=None)):
    info = parse_token(authorization)
    if info["role"] != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin role required")
    return await forward("get", f"http://task-service:8003/assignments/{task_id}", headers={"Authorization": authorization})

@app.get("/assignments/user/{user_id}")
async def assignments_by_user(user_id: int, authorization: str | None = Header(default=None)):
    info = parse_token(authorization)
    if info["role"] != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin role required")
    return await forward("get", f"http://task-service:8003/assignments/user/{user_id}", headers={"Authorization": authorization})

@app.post("/assignments")
async def upsert_assignment(payload: AssignmentSchema, authorization: str | None = Header(default=None)):
    info = parse_token(authorization)
    if info["role"] != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin role required")
    return await forward("post", "http://task-service:8003/assignments", payload.dict(), headers={"Authorization": authorization})

@app.patch("/assignments/{task_id}/status")
async def update_assignment_status(task_id: int, payload: AssignmentSchema, authorization: str | None = Header(default=None)):
    info = parse_token(authorization)
    if info["role"] != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin role required")
    return await forward("patch", f"http://task-service:8003/assignments/{task_id}/status", payload.dict(), headers={"Authorization": authorization})

@app.patch("/assignments/uid/{task_uid}/status")
async def update_assignment_status_by_uid(task_uid: str, payload: AssignmentSchema, authorization: str | None = Header(default=None)):
    info = parse_token(authorization)
    if info["role"] != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin role required")
    return await forward("patch", f"http://task-service:8003/assignments/uid/{task_uid}/status", payload.dict(), headers={"Authorization": authorization})
