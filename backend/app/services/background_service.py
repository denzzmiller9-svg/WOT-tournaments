import asyncio
import logging
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import joinedload, selectinload

from app.core.database import SessionFactory
from app.enums.tournament import TournamentStatus
from app.models.tournament import Tournament
from app.models.tournament_participant import TournamentParticipant
from app.services.tournament_service import TournamentService


logger = logging.getLogger(__name__)


class BackgroundService():

    STATUS_CHECK_INTERVAL = timedelta(seconds=10)
    RAITING_CHECK_INTERVAL = timedelta(seconds=60)

    @staticmethod
    async def update_tournament_statuses() -> None:

        async with SessionFactory() as session:
            tournaments = (await session.scalars(
                select(Tournament)
                .options(
                    selectinload(Tournament.participant_links).joinedload(
                        TournamentParticipant.user
                    )
                )
                .where(Tournament.status != TournamentStatus.COMPLETED)
            )).unique()

            for tournament in tournaments:
                tournament_service = TournamentService(session, tournament)
                await tournament_service.refresh_status()
            
            await session.commit()

    @staticmethod
    async def update_user_raiting():

        async with SessionFactory() as session:
            participant_links = await session.scalars(
                select(TournamentParticipant)
                .options(
                    joinedload(TournamentParticipant.tournament),
                    joinedload(TournamentParticipant.user)
                )
            )

            for participant in participant_links:
                await TournamentService(session, participant.tournament). \
                    refresh_participant_raiting(participant)

            await session.commit()

    async def run_update_tournament_statuses(self) -> None:
        while True:
            try:
                await self.update_tournament_statuses()
            except Exception:
                logger.exception("Failed to update tournament statuses")

            await asyncio.sleep(self.STATUS_CHECK_INTERVAL.total_seconds())

    async def run_update_user_raiting(self) -> None:
        while True:
            try:
                await self.update_user_raiting()
            except Exception:
                logger.exception("Failed to update user raiting")

            await asyncio.sleep(self.RAITING_CHECK_INTERVAL.total_seconds())
