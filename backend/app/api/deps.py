from typing import Annotated
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from typing import Annotated
from fastapi import Depends, HTTPException, status
import jwt
from app.core.config import get_settings
from app.core.security import decode_access_token
from app.models.user import User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_session


settings = get_settings()


SessionDep = Annotated[AsyncSession, Depends(get_session)]
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.api_v1_str}/auth/login")
optional_oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.api_v1_str}/auth/login",
    auto_error=False,
)


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    session: SessionDep
):
    return await _get_user_from_token(token, session)


async def get_optional_current_user(
    token: Annotated[str | None, Depends(optional_oauth2_scheme)],
    session: SessionDep,
) -> User | None:
    if token is None:
        return None

    return await _get_user_from_token(token, session)


async def _get_user_from_token(token: str, session: AsyncSession) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_access_token(token)

        username = payload.get("sub")
        if username is None:
            raise credentials_exception

    except jwt.InvalidTokenError:
        raise credentials_exception

    user = await session.scalar(
        select(User).where(User.name == username)
    )

    if user is None:
        raise credentials_exception
    
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalCurrentUser = Annotated[User | None, Depends(get_optional_current_user)]


async def get_current_wg_user(current_user: CurrentUser) -> User:
    if current_user.wg_account_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Привяжите аккаунт Wargaming, чтобы участвовать в турнирах",
        )

    return current_user


CurrentWgUser = Annotated[User, Depends(get_current_wg_user)]


async def get_current_user_admin(current_user: CurrentUser):
    if current_user.is_superuser:
        return current_user

    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",
        )


CurrentUserAdmin = Annotated[User, Depends(get_current_user_admin)]