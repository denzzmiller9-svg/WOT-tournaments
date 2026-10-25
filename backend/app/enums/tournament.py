import enum


class TournamentStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    RECRUITING = "recruiting"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class TournamentType(str, enum.Enum):
    PUBLIC = "public"
    PRIVATE = "private"