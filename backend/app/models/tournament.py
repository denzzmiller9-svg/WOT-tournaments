from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any
from app.enums.tournament import TournamentStatus, TournamentType
from app.models.base import Base
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import \
    CheckConstraint, ForeignKey, Index, String, DateTime, Enum, Interval, Integer


if TYPE_CHECKING:
    from app.models.message import Message
    from app.models.tournament_participant import TournamentParticipant
    from app.models.user import User


class Tournament(Base):
    __tablename__ = "tournaments"

    __table_args__ = (
        Index("status_index", "status"),
        CheckConstraint("reward >= 0", "reward_positive_constraint")
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    description: Mapped[str | None] = mapped_column(String(500))
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recruitment_time: Mapped[timedelta] = mapped_column(Interval)
    tournament_time: Mapped[timedelta] = mapped_column(Interval)
    reward: Mapped[int] = mapped_column(Integer)
    status: Mapped[TournamentStatus] = mapped_column(
        Enum(
            TournamentStatus,
            name="tournament_status",
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        nullable=False,
        default=TournamentStatus.SCHEDULED,
        server_default=TournamentStatus.SCHEDULED.value,
    )

    tournament_type: Mapped[TournamentType] = mapped_column(
        Enum(
            TournamentType,
            name="tournament_type",
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        nullable=False,
        default=TournamentType.PUBLIC,
        server_default=TournamentType.PUBLIC.value,
    )

    # goal: Mapped[dict[str, Any]] = mapped_column(MutableDict.as_mutable(JSONB))
    
    permitted_vehicle: Mapped[str | None] = mapped_column(String(50))
    required_battle_count: Mapped[int] = mapped_column(Integer, default=5)

    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )

    owner: Mapped["User"] = relationship(
        back_populates="owned_tournaments",
        foreign_keys=[owner_id],
    )

    participant_links: Mapped[list["TournamentParticipant"]] = relationship(
        back_populates="tournament",
        cascade="all, delete-orphan",
    )

    invites: Mapped[list["Message"]] = relationship(back_populates="related_tournament")


    # ------------------------------------------------------ # 
    
    def is_private(self):
        return self.tournament_type == TournamentType.PRIVATE

    def is_scheduled(self):
        return self.status == TournamentStatus.SCHEDULED

    def is_recruiting(self):
        return self.status == TournamentStatus.RECRUITING

    def is_active(self):
        return self.status == TournamentStatus.IN_PROGRESS

    def is_own_tournament(self, current_user):
        if current_user.is_superuser:
            return self.owner_id == None

        return self.owner_id == current_user.id
