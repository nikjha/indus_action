import os
import time

import jwt
import pytest
from fastapi import HTTPException

from services.api_gateway.app.main import parse_token


def test_parse_token_valid_jwt():
    secret = os.getenv("AUTH_SECRET", "dev-secret")
    now = int(time.time())
    token = jwt.encode({"sub": "admin1", "role": "ADMIN", "iat": now}, secret, algorithm="HS256")
    info = parse_token(f"Bearer {token}")
    assert info["username"] == "admin1"
    assert info["role"] == "ADMIN"


def test_parse_token_invalid_jwt():
    with pytest.raises(HTTPException):
        parse_token("Bearer not-a-jwt")
