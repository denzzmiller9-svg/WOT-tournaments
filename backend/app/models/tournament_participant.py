from typing import TYPE_CHECKING
from app.models.base import Base
from sqlalchemy import ForeignKey, Integer, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.mutable import MutableDict

if TYPE_CHECKING:
    from app.models.tournament import Tournament
    from app.models.user import User


class TournamentParticipant(Base):
    __tablename__ = "tournament_participants"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    
    tournament_id: Mapped[int] = mapped_column(
        ForeignKey("tournaments.id", ondelete="CASCADE"),
        primary_key=True,
    )

    total_damage: Mapped[int] = mapped_column(Integer, default=0)
    total_experience: Mapped[int] = mapped_column(Integer, default=0)
    total_destroyed_tanks: Mapped[int] = mapped_column(Integer, default=0)
    total_wtr: Mapped[int] = mapped_column(Integer, default=0)

    statistics_snapshot: Mapped[dict[str, int] | None] = mapped_column(
        MutableDict.as_mutable(JSONB),
        nullable=True,
    )

    place: Mapped[int | None] = mapped_column(Integer)
    battle_count: Mapped[int] = mapped_column(Integer, default=0)

    compleat_result: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped["User"] = relationship(
        back_populates="tournament_participations",
    )

    tournament: Mapped["Tournament"] = relationship(
        back_populates="participant_links",
    )

    # -------------------------------------------

    def get_avarege_raiting(self):
        return {
            "average_damage": int(self.total_damage / self.battle_count if self.battle_count != 0 else 0),
            "average_experience": int(self.total_experience / self.battle_count if self.battle_count != 0 else 0),
            "average_destroyed_tanks": int(self.total_destroyed_tanks / self.battle_count if self.battle_count != 0 else 0),
            "average_wtr": int(self.total_wtr / self.battle_count if self.battle_count != 0 else 0)
        }

    def update_raiting(
        self,
        last_battle_damage: int,
        last_battle_experience: int,
        last_battle_destroyed_tanks: int,
    ):
        self.total_damage += last_battle_damage
        self.total_experience += last_battle_experience
        self.total_destroyed_tanks += last_battle_destroyed_tanks
