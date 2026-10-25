from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums.message import MsgType
from app.enums.tournament import TournamentStatus
from app.exceptions import AlreadyInvitedError
from app.models.message import Message
from app.models.tournament import Tournament


class MessageService:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def send_message(
        self, 
        sender_id, 
        receiver_id: int, 
        related_tournament_id: int, 
        text: str,
        msg_type: MsgType = MsgType.TOURNAMENT_INVITE
    ):
        new_invite_message = Message(
            text=text, 
            sender_id=sender_id,
            receiver_id=receiver_id,
            related_tournament_id=related_tournament_id,
            msg_type=msg_type
        )

        self.session.add(new_invite_message)
        await self.session.commit()
        await self.session.refresh(new_invite_message)
        return new_invite_message

    async def send_invite(self, sender_id, receiver_id: int, related_tournament_id: int):

        invites = await self.session.scalar(
            select(Message).where(
                Message.receiver_id == receiver_id,
                Message.related_tournament_id == related_tournament_id,
                Message.sender_id == sender_id,
                Message.msg_type == MsgType.TOURNAMENT_INVITE
            )
        )

        if invites is not None:
            raise AlreadyInvitedError
        
        return await self.send_message(
            text="you have been invited",
            sender_id=sender_id,
            receiver_id=receiver_id,
            related_tournament_id=related_tournament_id
        )

    async def send_turnament_status_upate(
            self, 
            related_tournament: Tournament, 
            new_status: TournamentStatus
        ):

        for participant in related_tournament.participant_links:
            await self.send_message(
                None,
                participant.user_id, 
                participant.tournament_id, 
                f"tournament {related_tournament.name} is now {new_status.value}",
                MsgType.TOURNAMENT_STATUS_UPDATE
            )
        