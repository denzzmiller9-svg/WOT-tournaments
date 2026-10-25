from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, SessionDep
from app.exceptions import AlreadyInvitedError
from app.models.tournament import Tournament
from app.schemas.message_schema import MessageCreateInvite, MessageResponce
from app.models.message import Message
from app.services.message_service import MessageService


router = APIRouter(prefix="/messages", tags=["messages"])

@router.get(
    "",
    response_model=list[MessageResponce],
    summary="Get all users messages",
    description="Retrieve a list of all users messages."
)
async def get_messages(
    session: SessionDep,
    current_user: CurrentUser
):
    return await session.scalars(
        select(Message).where(Message.receiver_id == current_user.id)
    )


@router.post(
    "",
    response_model=MessageResponce,
)
async def send_invite(
    payload: MessageCreateInvite,
    session: SessionDep,
    current_user: CurrentUser
):
    related_tournament = await session.get(Tournament, payload.related_tournament_id)

    if (
        related_tournament is None or
        related_tournament.owner_id != current_user.id or
        not related_tournament.is_recruiting()
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",
        )

    try:
        return await MessageService(session).send_invite(
            sender_id=current_user.id,
            receiver_id=payload.receiver_id,
            related_tournament_id=payload.related_tournament_id
        )

    except AlreadyInvitedError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Player already invited",
        )
        