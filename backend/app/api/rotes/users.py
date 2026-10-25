

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, SessionDep, get_current_user_admin
from app.models.user import User
from app.schemas.user_schema import UserNamePublic, UserPublic
from app.services.user_service import UserService


router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserPublic)
async def read_current_user(user: CurrentUser) -> UserPublic:
    return UserPublic.model_validate(user)


@router.get(
    "", 
    response_model=list[UserPublic],
)
async def get_users(
    session: SessionDep,
    current_use: CurrentUser
) -> list[User]:

    users = \
        await session.scalars(select(User)) if current_use.is_superuser else \
        await session.scalars(select(User).where(User.is_active == True))

    return list(users)


@router.get(
    "/public/{user_id}",
    response_model=UserNamePublic,
)
async def get_public_user(
    session: SessionDep,
    user_id: int,
) -> User:
    user = await session.scalar(
        select(User).where(User.is_active == True, User.id == user_id)
    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="user not found",
        )

    return user


@router.get(
    "/{user_id}", 
    response_model=UserPublic,
)
async def get_user(
    session: SessionDep,
    current_use: CurrentUser,
    user_id: int
) -> User:

    user = \
        await session.scalar(
            select(User).where(User.id == user_id)
        ) if current_use.is_superuser else \
        await session.scalar(
            select(User).where(User.is_active == True, User.id == user_id)
        )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="user not found",
        )
    
    return user


@router.patch(
    "/{user_id}/deactivate",
    response_model=UserPublic,
    dependencies=[Depends(get_current_user_admin)]
)
async def deactivate_user(
    user_id: int,
    session: SessionDep,
) -> User:
    user = await session.get(User, user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="user not found",
        )

    user_service = UserService(session, user)
    return await user_service.set_user_status(False)


@router.patch(
    "/{user_id}/activate",
    response_model=UserPublic,
    dependencies=[Depends(get_current_user_admin)]
)
async def activate_user(
    user_id: int,
    session: SessionDep,
) -> User:
    user = await session.get(User, user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="user not found",
        )

    user_service = UserService(session, user)
    return await user_service.set_user_status(True)
