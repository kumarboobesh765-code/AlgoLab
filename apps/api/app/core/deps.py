import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import decode_access_token
from app.db.session import get_db
from app.marketdata.base import MarketDataProvider
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

DbSession = Annotated[AsyncSession, Depends(get_db)]

LOCAL_USER_EMAIL = "local@strategylab.dev"


async def ensure_local_user(db: AsyncSession) -> User:
    """Return the shared single-user account, creating it on first use."""
    result = await db.execute(select(User).where(User.email == LOCAL_USER_EMAIL))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            email=LOCAL_USER_EMAIL,
            hashed_password="!",  # not loginable; password auth unused in local mode
            full_name="Local Trader",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return user


def get_provider_instance() -> MarketDataProvider:
    """FastAPI dependency wrapper so tests can override the active provider."""
    from app.marketdata.factory import get_provider as factory_get_provider

    return factory_get_provider()


ProviderDep = Annotated[MarketDataProvider, Depends(get_provider_instance)]


async def get_current_user(
    db: DbSession,
    token: Annotated[str | None, Depends(oauth2_scheme)],
) -> User:
    if not get_settings().AUTH_ENABLED:
        return await ensure_local_user(db)

    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    subject = decode_access_token(token)
    if subject is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        user_id = uuid.UUID(subject)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject") from exc

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
