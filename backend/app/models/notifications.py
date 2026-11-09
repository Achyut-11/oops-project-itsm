from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class Notification:
    id: int
    user_id: int
    incident_id: int | None
    type: str
    message: str
    is_read: bool
    created_at: datetime

    COLUMNS = "id, user_id, incident_id, type, message, is_read, created_at"

    @classmethod
    def from_row(cls, row) -> "Notification":
        return cls(*row[:7])

    def to_dict(self) -> dict:
        return asdict(self)