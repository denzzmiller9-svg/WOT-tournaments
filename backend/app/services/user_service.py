from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import joinedload, selectinload
from app.exceptions import AlreadyParticipatingError, AnotheActiveTournamentError, ForbiddenTournamentError, \
    SuperuserParticipantError
from app.enums.message import MsgStatus, MsgType
from app.enums.tournament import TournamentStatus, TournamentType
from app.models.message import Message
from app.models.tournament import Tournament
from app.models.tournament_participant import TournamentParticipant
from app.models.user import User



class UserService:

    def __init__(self, session: AsyncSession, user: User) -> None:
        self.session = session
        self.user = user

    async def try_participate(self, tournament):
        if self.user.is_superuser:
            raise SuperuserParticipantError

        active_tournament = await self.get_active_participation()

        if active_tournament:
            if active_tournament.tournament_id == tournament.id:
                raise AlreadyParticipatingError

            else:
                raise AnotheActiveTournamentError

        if tournament.tournament_type == TournamentType.PUBLIC:
            return

        invites = await self.get_invites()

        if not (
            tournament.is_private()
            and (
                tournament.owner_id == self.user.id
                or tournament.id in [
                    invite.related_tournament_id
                    for invite in invites
                ]
            )
        ):
            raise ForbiddenTournamentError

        for invite in invites:
            invite.accept()

    async def get_active_participation(self):
        return await self.session.scalar(
            select(TournamentParticipant)
            .join(Tournament)
            .where(
                TournamentParticipant.user_id == self.user.id,
                Tournament.status != TournamentStatus.COMPLETED
            )
        )

    async def get_invites(self) -> list[Message]:
        return list(await self.session.scalars(
            select(Message).where(
                Message.receiver_id == self.user.id,
                Message.msg_type == MsgType.TOURNAMENT_INVITE,
                Message.status == MsgStatus.DELIVERED,
            )
        ))

    async def set_user_status(self, active_status=True):
        self.user.is_active = active_status
        await self.session.commit()
        await self.session.refresh(self.user)

        return self.user

    
  