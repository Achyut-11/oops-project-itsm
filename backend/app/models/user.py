from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class User:
    id: int
    name: str
    email: str
    role: str
    is_active: bool
    created_at: datetime
    years_of_experience: int | None
    skills: list[str]

    @classmethod
    def from_row(cls, row) -> "User":
        return cls(
            id=row[0], name=row[1], email=row[2], role=row[3],
            is_active=row[4], created_at=row[5],
            years_of_experience=row[6], skills=list(row[7] or []),
        )

    def to_dict(self) -> dict:
        return asdict(self)