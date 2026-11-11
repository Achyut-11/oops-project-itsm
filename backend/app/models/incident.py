from dataclasses import dataclass, asdict
from datetime import datetime
from app.exceptions import Forbidden, ValidationError, InvalidStateTransition

ALLOWED_TRANSITIONS = {
    "NEW": ["ASSIGNED"],
    "ASSIGNED": ["IN_PROGRESS"],
    "IN_PROGRESS": ["RESOLVED"],
    "RESOLVED": ["CLOSED"],
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
    closed_at: datetime | None

    COLUMNS = (
        "id, title, description, category, status, estimated_complexity, "
        "business_criticality, affected_percentage, priority, "
        "reported_by_user_id, assigned_technician_id, response_deadline, "
        "resolution_deadline, acknowledged_at, resolved_at, "
        "response_sla_breached, resolution_sla_breached, closed_at"
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
            closed_at = row[17]
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

    def ensure_can_be_resolved_by(self, user: dict) -> None:
            if user["role"] != "TECHNICIAN":
                raise Forbidden("Only technicians can resolve incidents")
             
            if self.assigned_technician_id != user["id"]:
                raise Forbidden("You can only resolve incidents assigned to you")
            
            if self.resolved_at is not None:
                raise ValidationError("Incident has already been resolved")
            
            if self.status != "IN_PROGRESS":
                raise InvalidStateTransition(
                    "Only incidents with IN_PROGRESS status can be resolved"
                )

    def ensure_can_be_closed_by(self, user: dict) -> None:
            if user["role"] != "ADMIN" :
                raise Forbidden("Only admins can close incidents")
            
            if self.status != "RESOLVED":
                raise InvalidStateTransition(
                    "Only incidents with RESOLVED status can be closed"
                )

    
    def ensure_can_be_reassigned_to(self, technician_id: int) -> None:
        if self.status not in ("ASSIGNED"):
            raise ValidationError(f"Cannot reassign an incident in {self.status} status")
        if self.assigned_technician_id == technician_id:
            raise ValidationError("Incident is already assigned to this technician")