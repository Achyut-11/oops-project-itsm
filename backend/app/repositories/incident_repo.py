from datetime import timedelta

from app.exceptions import IncidentNotFound
from app.models.incident import Incident


class IncidentRepository:

    def __init__(self, cur):
        self._cur = cur

    def get_by_id(self, incident_id: int) -> Incident:
        self._cur.execute(
            f"SELECT {Incident.COLUMNS} FROM incidents WHERE id = %s",
            (incident_id,),
        )
        row = self._cur.fetchone()
        if row is None:
            raise IncidentNotFound()
        return Incident.from_row(row)

    def get_visible_to(self, incident_id: int, user: dict) -> Incident:
        """Role-scoped lookup. Hidden incidents look like 'not found'."""
        incident = self.get_by_id(incident_id)
        role = user["role"]
        if role == "ADMIN":
            return incident
        if role == "TECHNICIAN" and incident.assigned_technician_id == user["id"]:
            return incident
        if role == "EMPLOYEE" and incident.reported_by_user_id == user["id"]:
            return incident
        raise IncidentNotFound()

    def search(self, user: dict, q) -> list[Incident]:
        """q is the IncidentQuery pydantic object from main.py."""
        sql = f"SELECT {Incident.COLUMNS} FROM incidents WHERE TRUE"
        params: list = []

        if user["role"] == "EMPLOYEE":
            sql += " AND reported_by_user_id = %s"
            params.append(user["id"])
        elif user["role"] == "TECHNICIAN":
            sql += " AND assigned_technician_id = %s"
            params.append(user["id"])

        filters = [
            (q.status, "status = %s"),
            (q.priority, "priority = %s"),
            (q.category, "category = %s"),
            (q.assigned_technician_id, "assigned_technician_id = %s"),
            (q.response_sla_breached, "response_sla_breached = %s"),
            (q.resolution_sla_breached, "resolution_sla_breached = %s"),
        ]
        for value, clause in filters:
            if value is not None:
                sql += f" AND {clause}"
                params.append(value)

        if q.start_date is not None:
            sql += " AND created_at >= %s"
            params.append(q.start_date)
        if q.end_date is not None:
            sql += " AND created_at < %s"
            params.append(q.end_date + timedelta(days=1))

        sql += " ORDER BY id ASC"
        self._cur.execute(sql, params)
        return [Incident.from_row(r) for r in self._cur.fetchall()]


    def create(self, data, reporter_id, priority,
               response_deadline, resolution_deadline) -> Incident:
        self._cur.execute(
            f"""
            INSERT INTO incidents
                (title, description, category, estimated_complexity,
                 business_criticality, affected_percentage, priority,
                 reported_by_user_id, response_deadline, resolution_deadline)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING {Incident.COLUMNS}
            """,
            (
                data.title, data.description, data.category,
                data.estimated_complexity, data.business_criticality,
                data.affected_percentage, priority, reporter_id,
                response_deadline, resolution_deadline,
            ),
        )
        return Incident.from_row(self._cur.fetchone())

    def assign_new(self, incident_id: int, technician_id: int) -> Incident:
        """First assignment at creation time."""
        self._cur.execute(
            f"""
            UPDATE incidents
            SET status = 'ASSIGNED', assigned_technician_id = %s
            WHERE id = %s
            RETURNING {Incident.COLUMNS}
            """,
            (technician_id, incident_id),
        )
        return Incident.from_row(self._cur.fetchone())

    def mark_acknowledged(self, incident_id: int) -> Incident | None:
      
        self._cur.execute(
            f"""
            UPDATE incidents
            SET status = 'IN_PROGRESS', acknowledged_at = CURRENT_TIMESTAMP
            WHERE id = %s
              AND status = 'ASSIGNED'
              AND acknowledged_at IS NULL
            RETURNING {Incident.COLUMNS}
            """,
            (incident_id,),
        )
        row = self._cur.fetchone()
        return Incident.from_row(row) if row else None

    def mark_resolved(self, incident_id: int) -> Incident | None:
            
            self._cur.execute(
                f"""
                UPDATE incidents
                SET status = 'RESOLVED', resolved_at = CURRENT_TIMESTAMP
                WHERE id = %s
                  AND status = 'IN_PROGRESS'
                  AND resolved_at IS NULL
                RETURNING {Incident.COLUMNS}
                """,
                (incident_id,),
            )
            row = self._cur.fetchone()
            return Incident.from_row(row) if row else None

    def mark_closed(self, incident_id: int) -> Incident | None:
                
                self._cur.execute(
                    f"""
                    UPDATE incidents
                    SET status = 'CLOSED', closed_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                      AND status = 'RESOLVED'
                      AND closed_at IS NULL
                    RETURNING {Incident.COLUMNS}
                    """,
                    (incident_id,),
                )
                row = self._cur.fetchone()
                return Incident.from_row(row) if row else None

    def update_status(self, incident_id: int, new_status: str) -> Incident:
        self._cur.execute(
            f"""
            UPDATE incidents
            SET status = %s,
                resolved_at = CASE
                    WHEN %s = 'RESOLVED' AND resolved_at IS NULL
                    THEN CURRENT_TIMESTAMP ELSE resolved_at END
            WHERE id = %s
            RETURNING {Incident.COLUMNS}
            """,
            (new_status, new_status, incident_id),
        )
        return Incident.from_row(self._cur.fetchone())

    def reassign(self, incident_id: int, technician_id: int) -> Incident | None:
        """Manual admin reassignment. None means the status changed underneath us."""
        self._cur.execute(
            f"""
            UPDATE incidents
            SET assigned_technician_id = %s,
                status = 'ASSIGNED',
                acknowledged_at = NULL,
                auto_reassigned = TRUE,
                reassigned_at = CURRENT_TIMESTAMP,
                escalation_admin_notified = FALSE
            WHERE id = %s
              AND status = 'ASSIGNED'
            RETURNING {Incident.COLUMNS}
            """,
            (technician_id, incident_id),
        )
        row = self._cur.fetchone()
        return Incident.from_row(row) if row else None