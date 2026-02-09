import base64
import json
import logging
import os
import secrets
import sys
import time

import httpx
import jwt
import psycopg2
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel

# Add services directory to path for shared imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from shared_auth import validate_bearer_token

app = FastAPI(
    title="Auth Service",
    description="Authentication service for the application",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s %(message)s")
logger = logging.getLogger("auth-service")

_db_conn = None

def get_db():
    """Get or create database connection"""
    global _db_conn
    if _db_conn:
        try:
            cursor = _db_conn.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            return _db_conn
        except Exception as e:
            logger.warning(f"Database connection lost: {e}. Reconnecting...")
            _db_conn = None
    
    try:
        db_host = os.getenv("DB_HOST", "localhost")
        db_port = int(os.getenv("DB_PORT", "5433"))
        db_user = os.getenv("DB_USER", "app")
        db_password = os.getenv("DB_PASSWORD", "app#123#")
        db_name = os.getenv("DB_NAME", "taskdb")
        
        _db_conn = psycopg2.connect(
            host=db_host,
            port=db_port,
            user=db_user,
            password=db_password,
            dbname=db_name,
            connect_timeout=5
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
                ("auth-service", request.method, str(request.url), int(response.status_code), int(duration_ms), json.dumps(req_headers), body_text, json.dumps(resp_headers), resp_text),
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

class LoginRequest(BaseModel):
    username: str
    password: str

@app.post("/login")
def login(payload: LoginRequest):
    if not payload.username or not payload.password:
        raise HTTPException(status_code=400, detail="Username and password are required")
    try:
        r = httpx.post("http://user-service:8002/users/verify-login", json={"username": payload.username, "password": payload.password}, timeout=5.0)
    except Exception as err:
        raise HTTPException(status_code=502, detail="User service unavailable") from err
    if r.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    info = r.json()
    now = int(time.time())
    secret = os.getenv("AUTH_SECRET", "dev-secret")
    role = info.get("role") or "USER"
    access = jwt.encode({"sub": payload.username, "role": role, "iat": now}, secret, algorithm="HS256")
    refresh = jwt.encode({"sub": payload.username, "type": "refresh", "iat": now}, secret, algorithm="HS256")
    return {"access_token": access, "refresh_token": refresh, "role": role, "user": {"username": payload.username, "uid": info.get("uid")}}

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
        title="Auth Service",
        version="1.0.0",
        description="Authentication service for the application",
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
                title="Auth Service - Swagger UI",
                swagger_ui_parameters={"persistAuthorization": True}
            )
        except HTTPException:
            pass
    
    # Fall back to basic auth
    _check_basic_auth(authorization)
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title="Auth Service - Swagger UI",
        swagger_ui_parameters={"persistAuthorization": True}
    )

@app.get("/redoc", tags=["Documentation"])
def protected_redoc(authorization: str | None = Header(default=None)):
    """ReDoc documentation. Requires Bearer token or basic auth."""
    # Try Bearer token first
    if authorization and authorization.startswith("Bearer "):
        try:
            validate_bearer_token(authorization)
            return get_redoc_html(openapi_url="/openapi.json", title="Auth Service - ReDoc")
        except HTTPException:
            pass
    
    # Fall back to basic auth
    _check_basic_auth(authorization)
    return get_redoc_html(openapi_url="/openapi.json", title="Auth Service - ReDoc")

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
    return {"status": "ok", "service": "auth-service"}
