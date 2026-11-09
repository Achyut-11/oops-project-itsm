from dataclasses import dataclass, asdict
from datetime import datetime
from app.exceptions import Forbidden, ValidationError, InvalidStateTransition

ALLOWED_TRANSITIONS = {
    "NEW": ["ASSIGNED"],
    "ASSIGNED": ["ACKNOWLEDGED"],
    "ACKNOWLEDGED": ["IN_PROGRESS"],
    "IN_PROGRESS": ["RESOLVED"],
    "RESOLVED": ["VERIFIED"],
    "VERIFIED": ["CLOSED"],
    "CLOSED": [],
}


@dataclass
class Incident:
    id: int
    title: str
    description: str
    category: str
    status: str
    estimated_complexity: str
    business_criticality: str
    affected_percentage: float
    priority: str
    reported_by_user_id: int
    assigned_technician_id: int | None
    response_deadline: datetime
    resolution_deadline: datetime
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    response_sla_breached: bool | None
    resolution_sla_breached: bool | None

    COLUMNS = (
        "id, title, description, category, status, estimated_complexity, "
        "business_criticality, affected_percentage, priority, "
        "reported_by_user_id, assigned_technician_id, response_deadline, "
        "resolution_deadline, acknowledged_at, resolved_at, "
        "response_sla_breached, resolution_sla_breached"
    )

    @classmethod
    def from_row(cls, row) -> "Incident":
        return cls(
            id=row[0],
            title=row[1],
            description=row[2],
            category=row[3],
            status=row[4],
            estimated_complexity=row[5],
            business_criticality=row[6],
            affected_percentage=float(row[7]),
            priority=row[8],
            reported_by_user_id=row[9],
            assigned_technician_id=row[10],
            response_deadline=row[11],
            resolution_deadline=row[12],
            acknowledged_at=row[13],
            resolved_at=row[14],
            response_sla_breached=row[15],
            resolution_sla_breached=row[16],
        )

    def to_dict(self) -> dict:
        return asdict(self)


    def ensure_can_be_acknowledged_by(self, user: dict) -> None:
        if self.assigned_technician_id != user["id"]:
            raise Forbidden("Unauthorized user")
        if self.acknowledged_at is not None:
            raise ValidationError("Incident has already been acknowledged")
        if self.status != "ASSIGNED":
            raise InvalidStateTransition(
                "Only incidents with ASSIGNED status can be acknowledged"
            )

    def ensure_can_move_to(self, new_status: str, user: dict) -> None:
        role = user["role"]

        if new_status == "ACKNOWLEDGED":
            raise ValidationError(
                "Use the acknowledgement endpoint to acknowledge incidents"
            )

        if role == "TECHNICIAN":
            if self.assigned_technician_id != user["id"]:
                raise Forbidden("You can only update incidents assigned to you")
            if new_status in ("VERIFIED", "CLOSED"):
                raise Forbidden("Only the reporter or an admin can verify or close")
        elif role == "EMPLOYEE":
            if self.reported_by_user_id != user["id"] or new_status not in ("VERIFIED", "CLOSED"):
                raise Forbidden("Employees can only verify or close their own incidents")

        if new_status not in ALLOWED_TRANSITIONS[self.status]:
            raise InvalidStateTransition(
                f"Can't change status from {self.status} to {new_status}"
            )

    def ensure_can_be_reassigned_to(self, technician_id: int) -> None:
        if self.status not in ("ASSIGNED", "ACKNOWLEDGED"):
            raise ValidationError(f"Cannot reassign an incident in {self.status} status")
        if self.assigned_technician_id == technician_id:
            raise ValidationError("Incident is already assigned to this technician")