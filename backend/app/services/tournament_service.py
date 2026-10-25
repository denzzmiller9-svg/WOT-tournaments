from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from app.enums.tournament import TournamentStatus
from app.exceptions import AnotheActiveTournamentError, ForbiddenTournamentError, \
    RecruitmentClosedError, SuperuserParticipantError
from app.models.tournament import Tournament
from app.models.tournament_participant import TournamentParticipant
from app.models.user import User
from app.services.message_service import MessageService
from app.services.user_rating_service import UserRaitingService
from app.services.user_service import UserService


class TournamentService:

    def __init__(self, session: AsyncSession, tournament: Tournament) -> None:
        self.session = session
        self.tournament = tournament

    async def add_participant(self, user: User) -> TournamentParticipant:
        
        if not self.tournament.is_recruiting():
            raise RecruitmentClosedError    

        try:
            await UserService(self.session, user).try_participate(self.tournament)
        except (
            SuperuserParticipantError,
            AnotheActiveTournamentError,
            ForbiddenTournamentError
        ):
            raise

        participation = TournamentParticipant(
            user_id=user.id,
            tournament_id=self.tournament.id,
        )
        
        self.session.add(participation)
        await self.session.commit()
        await self.session.refresh(participation)

        return participation

    @staticmethod
    def determine_tournament_status(
        start_date: datetime,
        recruitment_time: timedelta,
        tournament_time: timedelta,
        now: datetime,
    ) -> TournamentStatus:
        if start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        recruitment_start = start_date - recruitment_time
        if now < recruitment_start:
            return TournamentStatus.SCHEDULED
        if now < start_date:
            return TournamentStatus.RECRUITING
        if now < start_date + tournament_time:
            return TournamentStatus.IN_PROGRESS
        return TournamentStatus.COMPLETED

    async def refresh_status(self):
        current_time = datetime.now(tz=timezone.utc)

        new_status = self.determine_tournament_status(
            start_date=self.tournament.start_date,
            recruitment_time=self.tournament.recruitment_time,
            tournament_time=self.tournament.tournament_time,
            now=current_time,
        )
        if self.tournament.status != new_status:
            if (
                new_status == TournamentStatus.COMPLETED
                and self.tournament.is_active()
            ):
                for participant in self.tournament.participant_links:
                    await self.refresh_participant_raiting(participant)

            self.tournament.status = new_status

            await self.session.flush()
            await self.session.refresh(self.tournament)

            if new_status == TournamentStatus.IN_PROGRESS:
                user_raiting_service = UserRaitingService()
                for participant in self.tournament.participant_links:
                    account_id = participant.user.wg_account_id
                    if account_id is None:
                        raise ValueError(
                            "A linked Wargaming account is required to track tournament results"
                        )
                    access_token = await user_raiting_service.get_valid_access_token(
                        participant.user
                    )
                    snapshot = await user_raiting_service.get_initial_statistics(
                        account_id,
                        access_token,
                        self.tournament.permitted_vehicle,
                    )
                    participant.statistics_snapshot = (
                        user_raiting_service.snapshot_to_dict(snapshot)
                    )

            message_service = MessageService(self.session)
            await message_service.send_turnament_status_upate(
                self.tournament,
                new_status
            )

            if new_status == TournamentStatus.COMPLETED:
                for invite in self.tournament.invites:
                    invite.retire()

    async def refresh_participant_raiting(self, participant: TournamentParticipant):
        if not self.tournament.is_active():
            return

        if not participant.compleat_result:
            account_id = participant.user.wg_account_id
            if account_id is None:
                raise ValueError(
                    "A linked Wargaming account is required to track tournament results"
                )

            user_raiting_service = UserRaitingService()
            access_token = await user_raiting_service.get_valid_access_token(
                participant.user
            )
            if participant.statistics_snapshot is None:
                snapshot = await user_raiting_service.get_initial_statistics(
                    account_id,
                    access_token,
                    self.tournament.permitted_vehicle,
                )
                participant.statistics_snapshot = (
                    user_raiting_service.snapshot_to_dict(snapshot)
                )
                return

            last_battle_results = await user_raiting_service.get_last_battle_results(
                account_id,
                access_token,
                participant.statistics_snapshot,
            )

            if last_battle_results:
                participant.update_raiting(
                    last_battle_results.damage,
                    last_battle_results.experience,
                    last_battle_results.destroyed_tanks,
                )
                participant.statistics_snapshot = (
                    user_raiting_service.snapshot_to_dict(
                        last_battle_results.snapshot
                    )
                )

                participant.battle_count += 1

                if participant.battle_count >= self.tournament.required_battle_count:
                    participant.compleat_result = True
                
