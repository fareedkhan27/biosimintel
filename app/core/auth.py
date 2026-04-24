from __future__ import annotations

import os

from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

security = HTTPBearer(auto_error=False)


def verify_api_key(
    credentials: HTTPAuthorizationCredentials | None = Security(security),
) -> str:
    """Verify the BIOSIM_API_KEY bearer token."""
    expected = os.getenv("BIOSIM_API_KEY", "")
    if not expected:
        # If no API key is configured, allow all requests (dev mode)
        return ""

    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    token = credentials.credentials
    if token != expected:
        raise HTTPException(status_code=403, detail="Invalid API key")

    return token
