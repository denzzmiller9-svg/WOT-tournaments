from datetime import datetime
from typing import TYPE_CHECKING
from app.models.base import Base
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Boolean, DateTime, UniqueConstraint, false, true

from app.models.message import Message

if TYPE_CHECKING:
    from app.models.tournament import Tournament
    from app.models.tournament_participant import TournamentParticipant

class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("wg_account_id", name="uq_users_wg_account_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    email: Mapped[str] = mapped_column(String(50), unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    wg_account_id: Mapped[int | None] = mapped_column(nullable=True)
    wg_access_token_encrypted: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
    )
    wg_access_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default=true(),
    )

    is_superuser: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=false(),
    )

    owned_tournaments: Mapped[list["Tournament"]] = relationship(back_populates="owner")

    tournament_participations: Mapped[list["TournamentParticipant"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    sended_messages: Mapped[list["Message"]] = relationship(
        back_populates="sender",
        foreign_keys=lambda: [Message.sender_id]
    )

    received_messages: Mapped[list["Message"]] = relationship(
        back_populates="receiver",
        foreign_keys=lambda: [Message.receiver_id]
    
    )
