import hmac

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

bearer_scheme = HTTPBearer()


def verify_token(
    credential: str,
    admin_token: str,
) -> bool:
    if not admin_token or not credential:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing token",
        )
    if not hmac.compare_digest(credential.encode(), admin_token.encode()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing token",
        )
    return True


def require_auth(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> bool:
    return verify_token(
        credential=credentials.credentials,
        admin_token=settings.admin_token,
    )
