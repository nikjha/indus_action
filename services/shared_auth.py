"""
Shared authentication utilities for all services.
Supports Bearer token validation for both API endpoints and Swagger/OpenAPI documentation.
"""

import logging
import os
from datetime import datetime, timedelta

import jwt
from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

# Token configuration
JWT_SECRET = os.getenv("JWT_SECRET", "your-secret-key-change-in-production")
JWT_ALGORITHM = "HS256"
TOKEN_EXPIRY_MINUTES = 60


def generate_token(user_id: str, username: str = "app-user") -> str:
    """Generate a JWT token for testing/development."""
    payload = {
        "sub": user_id,
        "username": username,
        "exp": datetime.utcnow() + timedelta(minutes=TOKEN_EXPIRY_MINUTES),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> dict:
    """Verify and decode a JWT token."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        ) from err
    except jwt.InvalidTokenError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        ) from err


def extract_bearer_token(authorization: str) -> str:
    """Extract token from Authorization header."""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format. Use 'Bearer <token>'",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return parts[1]


def validate_bearer_token(authorization: str) -> dict:
    """Validate Bearer token from Authorization header."""
    token = extract_bearer_token(authorization)
    return verify_token(token)


def create_openapi_security_scheme():
    """Create OpenAPI security scheme configuration for Bearer token."""
    return {
        "openapi": "3.0.0",
        "info": {"title": "API", "version": "1.0.0"},
        "components": {
            "securitySchemes": {
                "Bearer": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT",
                    "description": "JWT Bearer token for authentication. Use token from /login endpoint.",
                }
            }
        },
        "security": [{"Bearer": []}],
    }
