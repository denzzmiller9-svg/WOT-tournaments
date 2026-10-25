from typing import Annotated
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urljoin
import logging

import httpx
import jwt
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from app.models.user import User
from app.schemas.user_schema import (
    AccessTokenResponse,
    RegisterRequest,
    UserPublic,
    WGRegistrationRequest,
)
from app.api.deps import CurrentUser, SessionDep
from app.core.security import (
    authenticate_user,
    create_access_token,
    create_wg_link_state,
    create_wg_login_state,
    create_wg_registration_token,
    decode_access_token,
    encrypt_wargaming_access_token,
    hash_password,
)
from fastapi.responses import RedirectResponse
from app.core.config import get_settings


router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)


@router.get("/wargaming/login")
async def wargaming_login() -> RedirectResponse:
    settings = get_settings()
    query_params = {
        "application_id": settings.wg_app_id,
        "redirect_uri": settings.wg_redirect_uri,
        "expires_at": int(
            (datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()
        ),
    }
    redirect = RedirectResponse(
        url=f"{settings.wg_authenticate_url}?{urlencode(query_params)}",
        status_code=status.HTTP_302_FOUND,
    )
    redirect.set_cookie(
        key="wg_login_state",
        value=create_wg_login_state(),
        max_age=600,
        httponly=True,
        secure=settings.wg_redirect_uri.startswith("https://"),
        samesite="lax",
        path=settings.wg_redirect_uri.rsplit("/", 1)[0],
    )
    return redirect


async def _verify_wargaming_identity(
    access_token: str,
    account_id: int,
    nickname: str,
) -> None:
    settings = get_settings()
    account_info_url = urljoin(settings.wg_authenticate_url, "../../account/info/")

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                account_info_url,
                params={
                    "application_id": settings.wg_app_id,
                    "access_token": access_token,
                    "account_id": account_id,
                    "fields": "account_id,nickname",
                },
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Unable to verify Wargaming account identity")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not verify the Wargaming account",
        ) from exc

    account_data = payload.get("data") if isinstance(payload, dict) else None
    account = account_data.get(str(account_id)) if isinstance(account_data, dict) else None
    if (
        not isinstance(payload, dict)
        or payload.get("status") != "ok"
        or not isinstance(account, dict)
        or str(account.get("account_id")) != str(account_id)
        or account.get("nickname") != nickname
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Wargaming account verification failed",
        )


def _wargaming_access_token_expiration(expires_at: int | None) -> datetime:
    if expires_at is not None:
        return datetime.fromtimestamp(expires_at, tz=timezone.utc)
    return datetime.now(timezone.utc) + timedelta(minutes=59)


@router.get("/wargaming/callback")
async def wargaming_callback(
    session: SessionDep,
    wg_login_state: Annotated[str | None, Cookie()] = None,
    wg_status: Annotated[str | None, Query(alias="status")] = None,
    access_token: str | None = None,
    expires_at: int | None = None,
    account_id: int | None = None,
    nickname: str | None = None,
) -> RedirectResponse:
    if wg_login_state is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Wargaming login was not started from this browser",
        )

    try:
        state_claims = decode_access_token(wg_login_state)
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Wargaming login state is invalid or expired",
        ) from exc
    state_purpose = state_claims.get("purpose")
    if state_purpose not in {"wg_login_state", "wg_link_state"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Wargaming login state is invalid",
        )
    link_user_id = state_claims.get("user_id")
    if state_purpose == "wg_link_state" and (
        not isinstance(link_user_id, int) or link_user_id <= 0
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Wargaming link state is invalid",
        )

    settings = get_settings()
    cookie_path = settings.wg_redirect_uri.rsplit("/", 1)[0]

    if wg_status != "ok" or not access_token or account_id is None or not nickname:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Wargaming authentication was not completed",
        )

    await _verify_wargaming_identity(access_token, account_id, nickname)
    encrypted_access_token = encrypt_wargaming_access_token(access_token)
    access_token_expires_at = _wargaming_access_token_expiration(expires_at)

    if state_purpose == "wg_link_state":
        user = await session.get(User, link_user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="The account to link no longer exists",
            )
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is deactivated",
            )
        if user.wg_account_id is not None and user.wg_account_id != account_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A Wargaming account is already linked",
            )

        linked_user = await session.scalar(
            select(User).where(User.wg_account_id == account_id)
        )
        if linked_user is not None and linked_user.id != user.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This Wargaming account is already linked to another user",
            )

        user.wg_account_id = account_id
        user.wg_access_token_encrypted = encrypted_access_token
        user.wg_access_token_expires_at = access_token_expires_at
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This Wargaming account is already linked to another user",
            ) from exc

        redirect = RedirectResponse(
            url=(
                f"{settings.frontend_host.rstrip('/')}/#"
                f"{urlencode({'access_token': create_access_token(user.name), 'wg_linked': '1'})}"
            ),
            status_code=status.HTTP_302_FOUND,
        )
        redirect.delete_cookie("wg_login_state", path=cookie_path)
        return redirect

    user = await session.scalar(
        select(User).where(User.wg_account_id == account_id)
    )
    if user is not None:
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is deactivated",
            )
        if user.name != nickname:
            name_owner = await session.scalar(
                select(User).where(User.name == nickname, User.id != user.id)
            )
            if name_owner is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Wargaming nickname is already used",
                )
            user.name = nickname

        user.wg_access_token_encrypted = encrypted_access_token
        user.wg_access_token_expires_at = access_token_expires_at
        await session.commit()

        redirect = RedirectResponse(
            url=(
                f"{settings.frontend_host.rstrip('/')}/#"
                f"{urlencode({'access_token': create_access_token(user.name), 'name': user.name})}"
            ),
            status_code=status.HTTP_302_FOUND,
        )
        redirect.delete_cookie("wg_login_state", path=cookie_path)
        return redirect

    registration_token = create_wg_registration_token(
        account_id,
        nickname,
        encrypted_access_token,
        access_token_expires_at,
    )
    redirect = RedirectResponse(
        url=(
            f"{settings.frontend_host.rstrip('/')}/#"
            f"{urlencode({'registration_token': registration_token, 'name': nickname})}"
        ),
        status_code=status.HTTP_302_FOUND,
    )
    redirect.delete_cookie("wg_login_state", path=cookie_path)
    return redirect

@router.post("/wargaming/link")
async def wargaming_link(
    response: Response,
    current_user: CurrentUser,
) -> dict[str, str]:
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated",
        )
    settings = get_settings()
    query_params = {
        "application_id": settings.wg_app_id,
        "redirect_uri": settings.wg_redirect_uri,
        "expires_at": int(
            (datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()
        ),
    }
    response.set_cookie(
        key="wg_login_state",
        value=create_wg_link_state(current_user.id),
        max_age=600,
        httponly=True,
        secure=settings.wg_redirect_uri.startswith("https://"),
        samesite="lax",
        path=settings.wg_redirect_uri.rsplit("/", 1)[0],
    )
    return {
        "authorization_url": (
            f"{settings.wg_authenticate_url}?{urlencode(query_params)}"
        )
    }


@router.post("/wargaming/register", response_model=AccessTokenResponse)
async def register_wargaming_user(
    payload: WGRegistrationRequest,
    session: SessionDep,
) -> AccessTokenResponse:
    try:
        claims = decode_access_token(payload.registration_token)
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Wargaming registration token is invalid or expired",
        ) from exc

    account_id = claims.get("wg_account_id")
    nickname = claims.get("wg_nickname")
    encrypted_access_token = claims.get("wg_access_token_encrypted")
    access_token_expires_at = claims.get("wg_access_token_expires_at")
    if (
        claims.get("purpose") != "wg_registration"
        or not isinstance(account_id, int)
        or account_id <= 0
        or not isinstance(nickname, str)
        or not nickname
        or not isinstance(encrypted_access_token, str)
        or not encrypted_access_token
        or not isinstance(access_token_expires_at, int)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Wargaming registration token is invalid",
        )

    email = str(payload.email).lower()
    if await session.scalar(select(User).where(User.email == email)) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already registered",
        )
    if await session.scalar(select(User).where(User.name == nickname)) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Wargaming nickname is already registered",
        )
    if await session.scalar(select(User).where(User.wg_account_id == account_id)) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Wargaming account is already registered",
        )

    user = User(
        name=nickname,
        email=email,
        password_hash=None,
        wg_account_id=account_id,
        wg_access_token_encrypted=encrypted_access_token,
        wg_access_token_expires_at=datetime.fromtimestamp(
            access_token_expires_at,
            tz=timezone.utc,
        ),
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Wargaming account, nickname, or email is already registered",
        ) from exc

    return AccessTokenResponse(
        access_token=create_access_token(user.name),
        token_type="bearer",
    )


@router.post("/login")
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: SessionDep
) -> AccessTokenResponse:
    user = await authenticate_user(session, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(user.name)
    return AccessTokenResponse(access_token=access_token, token_type="bearer")


@router.post(
    "/register",
    response_model=UserPublic,
    status_code=status.HTTP_201_CREATED,
)
async def register(payload: RegisterRequest, session: SessionDep) -> User:
    email = str(payload.email).lower()
    if await session.scalar(select(User).where(User.email == email)) is not None:
        raise HTTPException(status_code=409, detail="Email is already registered")
    if await session.scalar(select(User).where(User.name == payload.name)) is not None:
        raise HTTPException(status_code=409, detail="Nickname is already registered")

    user = User(
        name=payload.name, 
        email=email, 
        password_hash=hash_password(payload.password)
    )

    session.add(user)
    try:
        await session.commit()
    except IntegrityError as exc:  # handles two concurrent registrations for the same email
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Email or nickname is already registered",
        ) from exc

    await session.refresh(user)
    return user
