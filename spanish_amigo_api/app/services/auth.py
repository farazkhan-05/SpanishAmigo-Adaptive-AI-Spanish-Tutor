import json
import logging
from typing import Any, cast

import firebase_admin
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from firebase_admin import auth, credentials

from app.config import get_settings

logger = logging.getLogger("spanish-amigo-ai")
settings = get_settings()

# Initialize Firebase Admin app once for token verification.
if not firebase_admin._apps:
    if settings.FIREBASE_SERVICE_ACCOUNT_JSON:
        service_account = json.loads(settings.FIREBASE_SERVICE_ACCOUNT_JSON)
        cred = credentials.Certificate(service_account)

        firebase_admin.initialize_app(
            cred,
            {"projectId": settings.FIREBASE_PROJECT_ID},
        )
    else:
        firebase_admin.initialize_app(
            options={"projectId": settings.FIREBASE_PROJECT_ID}
        )

security = HTTPBearer()


def _http_401(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict[str, Any]:
    """
    Verify Firebase ID token and return decoded identity claims.
    """
    token = credentials.credentials

    try:
        return cast(dict[str, Any], auth.verify_id_token(token))
    except auth.ExpiredIdTokenError:
        logger.warning("Auth token expired")
        raise _http_401("Authentication failed. Please sign in again.")
    except auth.InvalidIdTokenError:
        logger.warning("Auth token invalid")
        raise _http_401("Authentication failed. Please sign in again.")
    except Exception as exc:
        logger.error("Auth verification error: %s", exc, exc_info=True)
        raise _http_401("Authentication failed. Please try again.")