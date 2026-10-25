import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs

import httpx

from app.models.user import User
from app.services.user_rating_service import UserRaitingService


class UserRaitingServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_access_token_is_prolonged_before_expiration(self) -> None:
        observed_requests: list[httpx.Request] = []

        def handle_request(request: httpx.Request) -> httpx.Response:
            observed_requests.append(request)
            return httpx.Response(
                200,
                json={
                    "status": "ok",
                    "data": {
                        "access_token": "renewed-wg-token",
                        "expires_at": int(
                            (datetime.now(timezone.utc) + timedelta(days=1)).timestamp()
                        ),
                    },
                },
            )

        real_async_client = httpx.AsyncClient

        def create_client(*args: object, **kwargs: object) -> httpx.AsyncClient:
            return real_async_client(
                *args,
                transport=httpx.MockTransport(handle_request),
                **kwargs,
            )

        user = User(
            id=7,
            name="WGPlayer",
            email="player@example.com",
            wg_account_id=12345,
            wg_access_token_encrypted="encrypted-old-token",
            wg_access_token_expires_at=(
                datetime.now(timezone.utc) + timedelta(minutes=2)
            ),
        )
        settings = SimpleNamespace(
            wg_app_id="test-application-id",
            wg_authenticate_url="https://api.worldoftanks.eu/wot/auth/login/",
        )
        with (
            patch(
                "app.services.user_rating_service.get_settings",
                return_value=settings,
            ),
            patch(
                "app.services.user_rating_service.decrypt_wargaming_access_token",
                return_value="old-wg-token",
            ),
            patch(
                "app.services.user_rating_service.encrypt_wargaming_access_token",
                return_value="encrypted-renewed-token",
            ),
            patch(
                "app.services.user_rating_service.httpx.AsyncClient",
                side_effect=create_client,
            ),
        ):
            access_token = await UserRaitingService().get_valid_access_token(user)

        self.assertEqual(access_token, "renewed-wg-token")
        self.assertEqual(user.wg_access_token_encrypted, "encrypted-renewed-token")
        self.assertEqual(len(observed_requests), 1)
        self.assertEqual(observed_requests[0].url.path, "/wot/auth/prolongate/")
        self.assertEqual(observed_requests[0].method, "POST")
        self.assertEqual(
            parse_qs(observed_requests[0].content.decode())["access_token"],
            ["old-wg-token"],
        )

    async def test_initial_snapshot_and_last_battle_deltas(self) -> None:
        responses = [
            {
                "status": "ok",
                "data": {
                    "42": {
                        "tank_id": 42,
                        "name": "ИС-7",
                    }
                },
            },
            self._account_info(100),
            self._tank_stats(42, 1000, 100, 2, 4),
            self._account_info(200),
            self._tank_stats(42, 1450, 800, 3, 5),
            self._account_info(200),
        ]
        observed_requests: list[httpx.Request] = []

        def handle_request(request: httpx.Request) -> httpx.Response:
            observed_requests.append(request)
            return httpx.Response(200, json=responses.pop(0))

        settings = SimpleNamespace(
            wg_app_id="test-application-id",
            wg_authenticate_url="https://api.worldoftanks.eu/wot/auth/login/",
        )
        real_async_client = httpx.AsyncClient

        def create_client(*args: object, **kwargs: object) -> httpx.AsyncClient:
            return real_async_client(
                *args,
                transport=httpx.MockTransport(handle_request),
                **kwargs,
            )

        with (
            patch(
                "app.services.user_rating_service.get_settings",
                return_value=settings,
            ),
            patch(
                "app.services.user_rating_service.httpx.AsyncClient",
                side_effect=create_client,
            ),
        ):
            service = UserRaitingService()
            initial = await service.get_initial_statistics(
                12345,
                "private-access-token",
                "ИС-7",
            )
            result = await service.get_last_battle_results(
                12345,
                "private-access-token",
                dict(initial),
            )
            assert result is not None
            no_second_result = await service.get_last_battle_results(
                12345,
                "private-access-token",
                dict(result.snapshot),
            )

        self.assertEqual(
            initial,
            {
                "tank_id": 42,
                "last_battle_time": 100,
                "battles": 4,
                "damage_dealt": 1000,
                "experience": 100,
                "destroyed_tanks": 2,
            },
        )
        self.assertEqual(result.damage, 450)
        self.assertEqual(result.experience, 700)
        self.assertEqual(result.destroyed_tanks, 1)
        self.assertIsNone(no_second_result)
        self.assertEqual(len(observed_requests), 6)
        self.assertTrue(
            observed_requests[0].url.path.endswith("/wot/encyclopedia/vehicles/")
        )
        self.assertEqual(observed_requests[1].url.path, "/wot/account/info/")
        self.assertEqual(
            observed_requests[1].url.params["access_token"],
            "private-access-token",
        )
        self.assertEqual(
            observed_requests[1].url.params["fields"],
            "last_battle_time",
        )
        self.assertEqual(observed_requests[2].url.path, "/wot/tanks/stats/")
        self.assertNotIn("last_battle_time", observed_requests[2].url.params["fields"])
        self.assertEqual(
            observed_requests[3].url.params.get("access_token"),
            "private-access-token",
        )
        self.assertEqual(
            observed_requests[4].url.params.get("tank_id"),
            "42",
        )

    @staticmethod
    def _account_info(last_battle_time: int) -> dict[str, object]:
        return {
            "status": "ok",
            "data": {
                "12345": {
                    "last_battle_time": last_battle_time,
                }
            },
        }

    @staticmethod
    def _tank_stats(
        tank_id: int,
        damage_dealt: int,
        experience: int,
        destroyed_tanks: int,
        battles: int,
    ) -> dict[str, object]:
        return {
            "status": "ok",
            "data": [
                {
                    "tank_id": tank_id,
                    "all": {
                        "damage_dealt": damage_dealt,
                        "xp": experience,
                        "frags": destroyed_tanks,
                        "battles": battles,
                    },
                }
            ],
        }
