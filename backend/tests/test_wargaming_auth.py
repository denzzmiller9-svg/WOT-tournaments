import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import cast
from urllib.parse import parse_qs, urlparse
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.rotes.auth import (
    _verify_wargaming_identity,
    register,
    register_wargaming_user,
    wargaming_link,
    wargaming_callback,
    wargaming_login,
)
from app.core.security import (
    decrypt_wargaming_access_token,
    encrypt_wargaming_access_token,
)
from app.models.user import User
from app.schemas.user_schema import RegisterRequest, WGRegistrationRequest


def make_session(**methods: object) -> AsyncSession:
    return cast(AsyncSession, SimpleNamespace(**methods))


class WargamingIdentityTests(unittest.IsolatedAsyncioTestCase):
    async def test_wargaming_access_tokens_are_encrypted_at_rest(self) -> None:
        with patch(
            "app.core.security.settings",
            SimpleNamespace(secret_key="test-secret-key-with-sufficient-entropy"),
        ):
            encrypted_token = encrypt_wargaming_access_token("private-wg-token")
            decrypted_token = decrypt_wargaming_access_token(encrypted_token)

        self.assertNotEqual(encrypted_token, "private-wg-token")
        self.assertEqual(decrypted_token, "private-wg-token")

    async def test_wargaming_registration_persists_encrypted_token_and_expiration(self) -> None:
        expiration = int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())
        created_users: list[User] = []
        commit = AsyncMock()
        session = make_session(
            scalar=AsyncMock(return_value=None),
            add=created_users.append,
            commit=commit,
        )
        payload = WGRegistrationRequest(
            registration_token="signed-registration-token",
            email="player@example.com",
        )
        with (
            patch(
                "app.api.rotes.auth.decode_access_token",
                return_value={
                    "purpose": "wg_registration",
                    "wg_account_id": 12345,
                    "wg_nickname": "WGPlayer",
                    "wg_access_token_encrypted": "encrypted-wg-token",
                    "wg_access_token_expires_at": expiration,
                },
            ),
            patch("app.api.rotes.auth.create_access_token", return_value="site-token"),
        ):
            response = await register_wargaming_user(payload, session)

        self.assertEqual(response.access_token, "site-token")
        self.assertEqual(created_users[0].wg_access_token_encrypted, "encrypted-wg-token")
        self.assertEqual(
            created_users[0].wg_access_token_expires_at,
            datetime.fromtimestamp(expiration, tz=timezone.utc),
        )
        commit.assert_awaited_once()

    async def test_login_redirect_uses_registered_callback_and_future_expiry(self) -> None:
        settings = SimpleNamespace(
            wg_app_id="test-application-id",
            wg_authenticate_url="https://api.worldoftanks.eu/wot/auth/login/",
            wg_redirect_uri="http://localhost:8000/api/v1/auth/wargaming/callback",
        )
        with (
            patch("app.api.rotes.auth.get_settings", return_value=settings),
            patch("app.api.rotes.auth.create_wg_login_state", return_value="signed-state"),
        ):
            response = await wargaming_login()

        parsed_location = urlparse(response.headers["location"])
        query = parse_qs(parsed_location.query)
        expires_at = int(query["expires_at"][0])
        now = int(datetime.now(timezone.utc).timestamp())

        self.assertEqual(parsed_location.path, "/wot/auth/login/")
        self.assertEqual(query["application_id"], ["test-application-id"])
        self.assertEqual(
            query["redirect_uri"],
            ["http://localhost:8000/api/v1/auth/wargaming/callback"],
        )
        self.assertGreater(expires_at, now)
        self.assertLessEqual(expires_at - now, 3600)
        self.assertIn("wg_login_state=signed-state", response.headers["set-cookie"])

    async def test_callback_redirects_existing_user_with_access_token(self) -> None:
        user = SimpleNamespace(name="WGPlayer", is_active=True, id=1)
        commit = AsyncMock()
        session = make_session(scalar=AsyncMock(return_value=user), commit=commit)
        settings = SimpleNamespace(
            wg_redirect_uri="http://localhost:8000/api/v1/auth/wargaming/callback",
            frontend_host="http://localhost:8000",
        )
        with (
            patch("app.api.rotes.auth.get_settings", return_value=settings),
            patch(
                "app.api.rotes.auth.decode_access_token",
                return_value={"purpose": "wg_login_state"},
            ),
            patch("app.api.rotes.auth._verify_wargaming_identity", new_callable=AsyncMock),
            patch(
                "app.api.rotes.auth.encrypt_wargaming_access_token",
                return_value="encrypted-wg-token",
            ),
            patch("app.api.rotes.auth.create_access_token", return_value="signed-access"),
        ):
            response = await wargaming_callback(
                session=session,
                wg_login_state="signed-state",
                wg_status="ok",
                access_token="wg-token",
                account_id=12345,
                nickname="WGPlayer",
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.headers["location"],
            "http://localhost:8000/#access_token=signed-access&name=WGPlayer",
        )
        self.assertEqual(user.wg_access_token_encrypted, "encrypted-wg-token")
        self.assertIsNotNone(user.wg_access_token_expires_at)
        commit.assert_awaited_once()
        self.assertIn("wg_login_state", response.headers["set-cookie"])

    async def test_callback_redirects_new_user_to_email_registration(self) -> None:
        session = make_session(scalar=AsyncMock(return_value=None))
        settings = SimpleNamespace(
            wg_redirect_uri="http://localhost:8000/api/v1/auth/wargaming/callback",
            frontend_host="http://localhost:8000",
        )
        with (
            patch("app.api.rotes.auth.get_settings", return_value=settings),
            patch(
                "app.api.rotes.auth.decode_access_token",
                return_value={"purpose": "wg_login_state"},
            ),
            patch("app.api.rotes.auth._verify_wargaming_identity", new_callable=AsyncMock),
            patch(
                "app.api.rotes.auth.encrypt_wargaming_access_token",
                return_value="encrypted-wg-token",
            ),
            patch(
                "app.api.rotes.auth.create_wg_registration_token",
                return_value="signed-registration",
            ) as create_registration_token,
        ):
            response = await wargaming_callback(
                session=session,
                wg_login_state="signed-state",
                wg_status="ok",
                access_token="wg-token",
                account_id=12345,
                nickname="WGPlayer",
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.headers["location"],
            "http://localhost:8000/#registration_token=signed-registration&name=WGPlayer",
        )
        self.assertEqual(create_registration_token.call_args.args[:3], (
            12345,
            "WGPlayer",
            "encrypted-wg-token",
        ))

    async def test_regular_registration_creates_user_without_wg_account(self) -> None:
        commit = AsyncMock()
        session = make_session(
            scalar=AsyncMock(return_value=None),
            add=lambda _: None,
            commit=commit,
            refresh=AsyncMock(),
        )
        payload = RegisterRequest(
            name="RegularPlayer",
            email="player@example.com",
            password="strong-password-123",
        )
        with patch(
            "app.api.rotes.auth.hash_password",
            return_value="hashed-password",
        ):
            user = await register(payload, session)

        self.assertEqual(user.name, "RegularPlayer")
        self.assertEqual(user.email, "player@example.com")
        self.assertEqual(user.password_hash, "hashed-password")
        self.assertIsNone(user.wg_account_id)
        commit.assert_awaited_once()

    async def test_regular_registration_rejects_duplicate_nickname(self) -> None:
        session = make_session(
            scalar=AsyncMock(side_effect=[None, SimpleNamespace(id=2)]),
        )
        payload = RegisterRequest(
            name="RegularPlayer",
            email="player@example.com",
            password="strong-password-123",
        )

        with self.assertRaises(HTTPException) as raised:
            await register(payload, session)

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(raised.exception.detail, "Nickname is already registered")

    async def test_link_start_requires_authenticated_user_and_sets_link_state(self) -> None:
        current_user = User(
            id=7,
            name="RegularPlayer",
            email="player@example.com",
            is_active=True,
        )
        response = Response()
        settings = SimpleNamespace(
            wg_app_id="test-application-id",
            wg_authenticate_url="https://api.worldoftanks.eu/wot/auth/login/",
            wg_redirect_uri="http://localhost:8000/api/v1/auth/wargaming/callback",
        )
        with (
            patch("app.api.rotes.auth.get_settings", return_value=settings),
            patch(
                "app.api.rotes.auth.create_wg_link_state",
                return_value="signed-link-state",
            ) as create_state,
        ):
            result = await wargaming_link(response, current_user)

        self.assertEqual(
            result["authorization_url"].split("?")[0],
            "https://api.worldoftanks.eu/wot/auth/login/",
        )
        self.assertIn("wg_login_state=signed-link-state", response.headers["set-cookie"])
        create_state.assert_called_once_with(7)

    async def test_callback_links_verified_wg_account_to_authenticated_user(self) -> None:
        user = SimpleNamespace(
            id=7,
            name="CustomUsername",
            is_active=True,
            wg_account_id=None,
        )
        user = User(
            id=7,
            name="CustomUsername",
            email="player@example.com",
            is_active=True,
        )
        commit = AsyncMock()
        session = make_session(
            get=AsyncMock(return_value=user),
            scalar=AsyncMock(return_value=None),
            commit=commit,
        )
        settings = SimpleNamespace(
            wg_redirect_uri="http://localhost:8000/api/v1/auth/wargaming/callback",
            frontend_host="http://localhost:8000",
        )
        with (
            patch("app.api.rotes.auth.get_settings", return_value=settings),
            patch(
                "app.api.rotes.auth.decode_access_token",
                return_value={"purpose": "wg_link_state", "user_id": 7},
            ),
            patch("app.api.rotes.auth._verify_wargaming_identity", new_callable=AsyncMock),
            patch(
                "app.api.rotes.auth.encrypt_wargaming_access_token",
                return_value="encrypted-wg-token",
            ),
            patch("app.api.rotes.auth.create_access_token", return_value="updated-access"),
        ):
            response = await wargaming_callback(
                session=session,
                wg_login_state="signed-link-state",
                wg_status="ok",
                access_token="wg-token",
                account_id=12345,
                nickname="WargamingNickname",
            )

        self.assertEqual(user.wg_account_id, 12345)
        self.assertEqual(user.name, "CustomUsername")
        self.assertEqual(user.wg_access_token_encrypted, "encrypted-wg-token")
        self.assertIsNotNone(user.wg_access_token_expires_at)
        self.assertEqual(
            response.headers["location"],
            "http://localhost:8000/#access_token=updated-access&wg_linked=1",
        )
        commit.assert_awaited_once()

    async def test_link_rejects_wg_account_already_bound_to_another_user(self) -> None:
        user = User(
            id=7,
            name="CustomUsername",
            email="player@example.com",
            is_active=True,
        )
        other_user = User(
            id=8,
            name="OtherPlayer",
            email="other@example.com",
        )
        session = make_session(
            get=AsyncMock(return_value=user),
            scalar=AsyncMock(return_value=other_user),
        )
        settings = SimpleNamespace(
            wg_redirect_uri="http://localhost:8000/api/v1/auth/wargaming/callback",
            frontend_host="http://localhost:8000",
        )
        with (
            patch("app.api.rotes.auth.get_settings", return_value=settings),
            patch(
                "app.api.rotes.auth.decode_access_token",
                return_value={"purpose": "wg_link_state", "user_id": 7},
            ),
            patch("app.api.rotes.auth._verify_wargaming_identity", new_callable=AsyncMock),
        ):
            with self.assertRaises(HTTPException) as raised:
                await wargaming_callback(
                    session=session,
                    wg_login_state="signed-link-state",
                    wg_status="ok",
                    access_token="wg-token",
                    account_id=12345,
                    nickname="WargamingNickname",
                )

        self.assertEqual(raised.exception.status_code, 409)
        self.assertIsNone(user.wg_account_id)

    async def test_validates_identity_using_account_info_api(self) -> None:
        observed_requests: list[httpx.Request] = []

        def handle_request(request: httpx.Request) -> httpx.Response:
            observed_requests.append(request)
            return httpx.Response(
                200,
                json={
                    "status": "ok",
                    "data": {
                        "12345": {
                            "account_id": 12345,
                            "nickname": "WGPlayer",
                        }
                    },
                },
            )

        transport = httpx.MockTransport(handle_request)
        real_async_client = httpx.AsyncClient

        def create_client(*args: object, **kwargs: object) -> httpx.AsyncClient:
            return real_async_client(*args, transport=transport, **kwargs)

        settings = SimpleNamespace(
            wg_authenticate_url="https://api.worldoftanks.eu/wot/auth/login/",
            wg_app_id="test-application-id",
        )
        with (
            patch("app.api.rotes.auth.get_settings", return_value=settings),
            patch("app.api.rotes.auth.httpx.AsyncClient", side_effect=create_client),
        ):
            await _verify_wargaming_identity("private-access-token", 12345, "WGPlayer")

        self.assertEqual(len(observed_requests), 1)
        request = observed_requests[0]
        self.assertEqual(request.url.path, "/wot/account/info/")
        self.assertEqual(request.url.params["application_id"], "test-application-id")
        self.assertEqual(request.url.params["access_token"], "private-access-token")
        self.assertEqual(request.url.params["account_id"], "12345")
        self.assertEqual(request.url.params["fields"], "account_id,nickname")

    async def test_rejects_nickname_that_does_not_match_verified_account(self) -> None:
        transport = httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={
                    "status": "ok",
                    "data": {
                        "12345": {
                            "account_id": 12345,
                            "nickname": "DifferentPlayer",
                        }
                    },
                },
            )
        )
        real_async_client = httpx.AsyncClient

        def create_client(*args: object, **kwargs: object) -> httpx.AsyncClient:
            return real_async_client(*args, transport=transport, **kwargs)

        settings = SimpleNamespace(
            wg_authenticate_url="https://api.worldoftanks.eu/wot/auth/login/",
            wg_app_id="test-application-id",
        )
        with (
            patch("app.api.rotes.auth.get_settings", return_value=settings),
            patch("app.api.rotes.auth.httpx.AsyncClient", side_effect=create_client),
        ):
            with self.assertRaises(HTTPException) as raised:
                await _verify_wargaming_identity(
                    "private-access-token",
                    12345,
                    "ClaimedPlayer",
                )

        self.assertEqual(raised.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
