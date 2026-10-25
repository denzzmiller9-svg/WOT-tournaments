from dataclasses import dataclass
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Literal, TypedDict
from urllib.parse import urljoin

import httpx

from app.core.config import get_settings
from app.core.security import decrypt_wargaming_access_token, encrypt_wargaming_access_token
from app.models.user import User


class TankStatisticsSnapshot(TypedDict):
    tank_id: int
    last_battle_time: int
    battles: int
    damage_dealt: int
    experience: int
    destroyed_tanks: int


@dataclass(frozen=True)
class LastBattleResults:
    damage: int
    experience: int
    destroyed_tanks: int
    snapshot: TankStatisticsSnapshot


class WargamingAPIError(RuntimeError):
    pass


class UserRaitingService:
    @staticmethod
    def snapshot_to_dict(snapshot: TankStatisticsSnapshot) -> dict[str, int]:
        return {
            "tank_id": snapshot["tank_id"],
            "last_battle_time": snapshot["last_battle_time"],
            "battles": snapshot["battles"],
            "damage_dealt": snapshot["damage_dealt"],
            "experience": snapshot["experience"],
            "destroyed_tanks": snapshot["destroyed_tanks"],
        }

    async def get_initial_statistics(
        self,
        account_id: int,
        access_token: str,
        vehicle: str | None,
    ) -> TankStatisticsSnapshot:
        if not vehicle:
            raise ValueError("A permitted vehicle is required to track tournament battles")

        tank_id = await self._get_vehicle_id(vehicle)
        last_battle_time = await self._get_account_last_battle_time(
            account_id,
            access_token,
        )
        tank_stats = await self._get_tank_statistics(account_id, tank_id)
        return TankStatisticsSnapshot(
            tank_id=tank_id,
            last_battle_time=last_battle_time,
            battles=tank_stats["battles"],
            damage_dealt=tank_stats["damage_dealt"],
            experience=tank_stats["experience"],
            destroyed_tanks=tank_stats["destroyed_tanks"],
        )

    async def get_last_battle_results(
        self,
        account_id: int,
        access_token: str,
        previous_statistics: Mapping[str, object],
    ) -> LastBattleResults | None:
        previous = self._validate_snapshot(previous_statistics)
        last_battle_time = await self._get_account_last_battle_time(
            account_id,
            access_token,
        )
        if last_battle_time <= previous["last_battle_time"]:
            return None

        current = await self._get_tank_statistics(account_id, previous["tank_id"])
        if current["battles"] <= previous["battles"]:
            return None

        current["last_battle_time"] = last_battle_time
        damage = current["damage_dealt"] - previous["damage_dealt"]
        experience = current["experience"] - previous["experience"]
        destroyed_tanks = current["destroyed_tanks"] - previous["destroyed_tanks"]
        if min(damage, experience, destroyed_tanks) < 0:
            raise WargamingAPIError("Wargaming tank statistics decreased between polls")

        return LastBattleResults(
            damage=damage,
            experience=experience,
            destroyed_tanks=destroyed_tanks,
            snapshot=current,
        )

    async def get_valid_access_token(self, user: User) -> str:
        encrypted_token = user.wg_access_token_encrypted
        expires_at = user.wg_access_token_expires_at
        if encrypted_token is None or expires_at is None:
            raise WargamingAPIError(
                "Wargaming account authorization is required; please link the account again"
            )

        if expires_at.tzinfo is None or expires_at.utcoffset() is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        access_token = decrypt_wargaming_access_token(encrypted_token)
        if expires_at > datetime.now(timezone.utc) + timedelta(minutes=5):
            return access_token

        settings = get_settings()
        payload = await self._request(
            urljoin(settings.wg_authenticate_url, "../../auth/prolongate/"),
            {
                "application_id": settings.wg_app_id,
                "access_token": access_token,
                "expires_at": int(
                    (datetime.now(timezone.utc) + timedelta(days=14)).timestamp()
                ),
            },
            method="POST",
        )
        data = payload.get("data")
        if not isinstance(data, dict):
            raise WargamingAPIError("Wargaming token renewal returned an invalid response")
        renewed_token = data.get("access_token")
        renewed_expiration = data.get("expires_at")
        if (
            not isinstance(renewed_token, str)
            or not renewed_token
            or not isinstance(renewed_expiration, int)
        ):
            raise WargamingAPIError("Wargaming token renewal omitted token details")

        user.wg_access_token_encrypted = encrypt_wargaming_access_token(renewed_token)
        user.wg_access_token_expires_at = datetime.fromtimestamp(
            renewed_expiration,
            tz=timezone.utc,
        )
        return renewed_token

    async def _get_vehicle_id(self, vehicle_name: str) -> int:
        settings = get_settings()
        payload = await self._request(
            urljoin(settings.wg_authenticate_url, "../../encyclopedia/vehicles/"),
            {
                "application_id": settings.wg_app_id,
                "fields": "tank_id,name",
                "language": "ru",
                "limit": 1000,
            },
        )
        data = payload.get("data")
        if not isinstance(data, dict):
            raise WargamingAPIError("Wargaming vehicle catalog has an invalid response")

        normalized_name = vehicle_name.strip().casefold()
        for vehicle_data in data.values():
            if not isinstance(vehicle_data, dict):
                continue
            name = vehicle_data.get("name")
            tank_id = vehicle_data.get("tank_id")
            if isinstance(name, str) and name.strip().casefold() == normalized_name:
                if isinstance(tank_id, int):
                    return tank_id
                raise WargamingAPIError("Wargaming vehicle catalog returned an invalid vehicle ID")

        raise WargamingAPIError("The permitted vehicle was not found in the Wargaming catalog")

    async def _get_tank_statistics(
        self,
        account_id: int,
        tank_id: int,
    ) -> TankStatisticsSnapshot:
        settings = get_settings()
        payload = await self._request(
            urljoin(settings.wg_authenticate_url, "../../tanks/stats/"),
            {
                "application_id": settings.wg_app_id,
                "account_id": account_id,
                "tank_id": tank_id,
                "fields": "tank_id,all",
            },
        )
        data = payload.get("data")[f'{account_id}']
        if not isinstance(data, list):
            raise WargamingAPIError("Wargaming tank statistics have an invalid response")

        vehicle_stats = next(
            (
                item
                for item in data
                if isinstance(item, dict) and item.get("tank_id") == tank_id
            ),
            None,
        )
        if vehicle_stats is None:
            return TankStatisticsSnapshot(
                tank_id=tank_id,
                last_battle_time=0,
                battles=0,
                damage_dealt=0,
                experience=0,
                destroyed_tanks=0,
            )

        all_stats = vehicle_stats.get("all")
        if not isinstance(all_stats, dict):
            raise WargamingAPIError("Wargaming tank statistics are missing aggregate values")

        return TankStatisticsSnapshot(
            tank_id=tank_id,
            last_battle_time=0,
            battles=self._read_nonnegative_int(all_stats, "battles"),
            damage_dealt=self._read_nonnegative_int(all_stats, "damage_dealt"),
            experience=self._read_nonnegative_int(all_stats, "xp"),
            destroyed_tanks=self._read_nonnegative_int(all_stats, "frags"),
        )

    async def _get_account_last_battle_time(
        self,
        account_id: int,
        access_token: str,
    ) -> int:
        settings = get_settings()
        payload = await self._request(
            urljoin(settings.wg_authenticate_url, "../../account/info/"),
            {
                "application_id": settings.wg_app_id,
                "access_token": access_token,
                "account_id": account_id,
                "fields": "last_battle_time",
            },
        )
        data = payload.get("data")
        account = data.get(str(account_id)) if isinstance(data, dict) else None
        if not isinstance(account, dict):
            raise WargamingAPIError("Wargaming account info omitted the requested account")
        return self._read_nonnegative_int(account, "last_battle_time")

    async def _request(
        self,
        url: str,
        params: dict[str, str | int],
        *,
        method: Literal["GET", "POST"] = "GET",
    ) -> dict[str, object]:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                if method == "POST":
                    response = await client.post(url, data=params)
                else:
                    response = await client.get(url, params=params)
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise WargamingAPIError("Unable to retrieve statistics from Wargaming") from exc

        if not isinstance(payload, dict) or payload.get("status") != "ok":
            raise WargamingAPIError("Wargaming returned an unsuccessful API response")
        return payload

    @staticmethod
    def _read_nonnegative_int(data: Mapping[str, object], field: str) -> int:
        value = data.get(field)
        if not isinstance(value, int) or value < 0:
            raise WargamingAPIError(
                f"Wargaming returned an invalid {field} tank statistic"
            )
        return value

    @classmethod
    def _validate_snapshot(
        cls,
        snapshot: Mapping[str, object],
    ) -> TankStatisticsSnapshot:
        return TankStatisticsSnapshot(
            tank_id=cls._read_nonnegative_int(snapshot, "tank_id"),
            last_battle_time=cls._read_nonnegative_int(snapshot, "last_battle_time"),
            battles=cls._read_nonnegative_int(snapshot, "battles"),
            damage_dealt=cls._read_nonnegative_int(snapshot, "damage_dealt"),
            experience=cls._read_nonnegative_int(snapshot, "experience"),
            destroyed_tanks=cls._read_nonnegative_int(snapshot, "destroyed_tanks"),
        )
