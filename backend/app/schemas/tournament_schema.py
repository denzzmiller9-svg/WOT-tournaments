from datetime import datetime, timedelta, timezone
from pydantic import BaseModel, ConfigDict, field_validator


def normalize_start_date_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class TournamentBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    @field_validator("start_date")
    @classmethod
    def normalize_start_date(cls, value: datetime) -> datetime:
        return normalize_start_date_utc(value)

    name: str
    description: str
    start_date: datetime
    recruitment_time: timedelta
    tournament_time: timedelta
    reward: int
    required_battle_count: int
    permitted_vehicle: str

    # goal: dict[str, Any]


class TournamentPublicResponse(TournamentBase):
    id: int
    owner_id: int | None
    status: str
    tournament_type: str
    is_participating: bool = False
    own_tournament: bool = False
    owner_name: str | None = None


class TournamentCreateRequest(TournamentBase):
    pass

class TournamentUpdate(BaseModel):

    @field_validator("start_date")
    @classmethod
    def normalize_start_date(cls, value: datetime | None) -> datetime | None:
        return normalize_start_date_utc(value) if value is not None else None
    
    name: str | None = None
    description: str | None = None
    start_date: datetime | None = None
    recruitment_time: timedelta | None = None
    tournament_time: timedelta | None = None
    reward: int | None
    required_battle_count: int | None
    permitted_vehicle: str | None

    # goal: dict[str, Any] | None


class TournamentParticipationInviteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: int
    tournament_id: int

class TournamentParticipationRead(BaseModel):

    user_id: int
    average_damage: int
    average_experience: int
    average_destroyed_tanks: int
    average_wtr: int


    place: int | None
    battle_count: int