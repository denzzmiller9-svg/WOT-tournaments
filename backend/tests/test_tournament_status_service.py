import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession
from app.enums.tournament import TournamentStatus
from app.api.rotes.tournaments import create_tournament
from app.models.user import User
from app.schemas.tournament_schema import TournamentCreateRequest, TournamentUpdate
from app.services.tournament_service import TournamentService


class DetermineTournamentStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.start_date = datetime(2026, 11, 10, 12)
        self.recruitment_time = timedelta(days=2)
        self.tournament_time = timedelta(hours=3)

    def test_before_recruitment_is_scheduled(self) -> None:
        status = TournamentService.determine_tournament_status(
            self.start_date,
            self.recruitment_time,
            self.tournament_time,
            datetime(2026, 11, 8, 11, 59),
        )
        self.assertEqual(status, TournamentStatus.SCHEDULED)

    def test_future_timezone_aware_start_is_not_in_progress(self) -> None:
        now = datetime(2026, 11, 8, 11, tzinfo=timezone.utc)
        start_date = datetime(2026, 11, 10, 12, tzinfo=timezone.utc)

        status = TournamentService.determine_tournament_status(
            start_date,
            self.recruitment_time,
            self.tournament_time,
            now,
        )

        self.assertEqual(status, TournamentStatus.SCHEDULED)

    def test_naive_dates_are_interpreted_as_utc(self) -> None:
        status = TournamentService.determine_tournament_status(
            self.start_date,
            self.recruitment_time,
            self.tournament_time,
            datetime(2026, 11, 8, 11, 59, tzinfo=timezone.utc),
        )

        self.assertEqual(status, TournamentStatus.SCHEDULED)

    def test_recruitment_starts_at_start_minus_recruitment_time(self) -> None:
        status = TournamentService.determine_tournament_status(
            self.start_date,
            self.recruitment_time,
            self.tournament_time,
            datetime(2026, 11, 8, 12),
        )
        self.assertEqual(status, TournamentStatus.RECRUITING)

    def test_tournament_starts_at_start_date(self) -> None:
        status = TournamentService.determine_tournament_status(
            self.start_date,
            self.recruitment_time,
            self.tournament_time,
            self.start_date,
        )
        self.assertEqual(status, TournamentStatus.IN_PROGRESS)

    def test_tournament_completes_after_its_duration(self) -> None:
        status = TournamentService.determine_tournament_status(
            self.start_date,
            self.recruitment_time,
            self.tournament_time,
            self.start_date + self.tournament_time,
        )
        self.assertEqual(status, TournamentStatus.COMPLETED)


class TournamentTimeZoneTests(unittest.TestCase):
    def test_create_schema_normalizes_naive_start_date_to_utc(self) -> None:
        payload = TournamentCreateRequest(
            name="Test tournament",
            description="Description",
            start_date=datetime(2026, 11, 10, 12),
            recruitment_time=timedelta(hours=1),
            tournament_time=timedelta(hours=1),
            reward=0,
            required_battle_count=1,
            permitted_vehicle="Test vehicle",
        )

        self.assertEqual(payload.start_date.tzinfo, timezone.utc)

    def test_update_schema_converts_offset_start_date_to_utc(self) -> None:
        payload = TournamentUpdate(
            start_date=datetime.fromisoformat("2026-11-10T12:00:00+03:00"),
            reward=None,
            required_battle_count=None,
            permitted_vehicle=None,
        )

        self.assertEqual(
            payload.start_date,
            datetime(2026, 11, 10, 9, tzinfo=timezone.utc),
        )


class CreateTournamentStatusTests(unittest.IsolatedAsyncioTestCase):
    async def test_future_tournament_is_created_as_scheduled(self) -> None:
        class FakeSession:
            def add(self, _: object) -> None:
                pass

            async def commit(self) -> None:
                pass

            async def refresh(self, _: object) -> None:
                pass

        session = FakeSession()
        payload = TournamentCreateRequest(
            name="Future tournament",
            description="Starts in two hours",
            start_date=datetime.now(timezone.utc) + timedelta(hours=2),
            recruitment_time=timedelta(hours=1),
            tournament_time=timedelta(hours=1),
            reward=0,
            required_battle_count=1,
            permitted_vehicle="Test vehicle",
        )

        tournament = await create_tournament(
            payload,
            cast(AsyncSession, session),
            cast(User, SimpleNamespace(id=1, is_superuser=True)),
        )

        self.assertEqual(tournament.status, TournamentStatus.SCHEDULED)
