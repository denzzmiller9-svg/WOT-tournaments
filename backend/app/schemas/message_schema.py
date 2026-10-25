from pydantic import BaseModel, ConfigDict
from app.enums.message import MsgStatus, MsgType


class MessageBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    related_tournament_id: int

    
class MessageResponce(MessageBase):
    id: int
    sender_id: int | None
    receiver_id: int
    msg_type: MsgType
    status: MsgStatus
    text: str


class MessageCreateInvite(MessageBase):
    receiver_id: int
