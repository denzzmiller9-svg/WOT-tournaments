
from enum import Enum


class MsgType(str, Enum):
    TOURNAMENT_STATUS_UPDATE = "tournament_status_update"
    TOURNAMENT_RESULT = "tournament_result"
    TOURNAMENT_INVITE = "tournament_invite"
    TOURNAMENT_INVITE_STATUS = "tournament_invite_staus"


class MsgStatus(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "tournament_invite"
    NOT_RELEVANT = "no_relevant"
    DELIVERED = "delivered"
