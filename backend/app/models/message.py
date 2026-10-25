from typing import TYPE_CHECKING
from app.enums.message import MsgStatus, MsgType
from app.models.base import Base
from sqlalchemy import Boolean, ForeignKey, String, Enum, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship


if TYPE_CHECKING:
    from app.models.tournament import Tournament
    from app.models.user import User


class Message(Base):
    __tablename__ = "messages"

    __table_args__ = (
        UniqueConstraint(
            "related_tournament_id",
            "sender_id",
            "receiver_id",
            "msg_type",
            name="sender_receiver_tournament_unique_constraint"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    text: Mapped[str] = mapped_column(String(100))

    msg_type: Mapped[MsgType] = mapped_column(
        Enum(
            MsgType,
            name="msg_type",
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        nullable=False,
    )

    related_tournament_id: Mapped[int | None] = mapped_column(
        ForeignKey("tournaments.id", ondelete="CASCADE")
    )
    sender_id: Mapped[int | None]  = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    receiver_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL")) 

    status: Mapped[MsgStatus] = mapped_column(
        Enum(
            MsgStatus,
            name="msg_status",
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        default=MsgStatus.DELIVERED,
        nullable=False,
    )

    sender: Mapped["User"] = relationship(
        back_populates="sended_messages",
        foreign_keys=lambda: [Message.sender_id]
    )
    receiver: Mapped["User"] = relationship(
        back_populates="received_messages",
        foreign_keys=lambda: [Message.receiver_id]
    )
    related_tournament: Mapped["Tournament"] = relationship(back_populates="invites")

    # ---------------------------------------------------

    def accept(self):
        self.status = MsgStatus.ACCEPTED

    def reject(self):
        self.status = MsgStatus.REJECTED

    def retire(self):
        self.status = MsgStatus.NOT_RELEVANT