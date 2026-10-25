import unittest

from app.models.tournament import Tournament
from app.models.user import User


class TournamentOwnershipTests(unittest.TestCase):
    def test_owner_is_recognized(self) -> None:
        tournament = Tournament(owner_id=7)
        owner = User(id=7, is_superuser=False)

        self.assertTrue(tournament.is_own_tournament(owner))

    def test_other_user_is_not_recognized_as_owner(self) -> None:
        tournament = Tournament(owner_id=7)
        other_user = User(id=8, is_superuser=False)

        self.assertFalse(tournament.is_own_tournament(other_user))

    def test_superuser_does_not_own_unowned_tournament(self) -> None:
        tournament = Tournament(owner_id=None)
        superuser = User(id=8, is_superuser=True)

        self.assertFalse(tournament.is_own_tournament(superuser))
