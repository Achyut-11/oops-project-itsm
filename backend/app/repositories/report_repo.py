class ReportRepository:
    def __init__(self, cur):
        self._cur = cur

    def overview(self) -> dict:
        self._cur.execute("""
            SELECT
                COUNT(*),
                COUNT(*) FILTER (WHERE status NOT IN ('RESOLVED', 'CLOSED')),
                COUNT(*) FILTER (WHERE priority = 'P1'),

                COUNT(*) FILTER (WHERE status IN ('RESOLVED', 'CLOSED')),
                COUNT(*) FILTER (WHERE response_sla_breached OR resolution_sla_breached)
            FROM incidents;
        """)
        r = self._cur.fetchone()
        return {"total": r[0], "open": r[1], "critical": r[2],
                "resolved": r[3], "sla_violations": r[4]}

    def technician_workload(self) -> list[dict]:
        self._cur.execute("""
            SELECT u.id, u.name, COUNT(i.id) AS active_incidents
            FROM users u

            LEFT JOIN incidents i
                ON u.id = i.assigned_technician_id

                AND i.status IN ('ASSIGNED','IN_PROGRESS')
            WHERE u.role = 'TECHNICIAN' AND u.is_active = TRUE
            GROUP BY u.id, u.name
            ORDER BY active_incidents DESC, u.id ASC;
        """)
        return [{"technician_id": r[0], "name": r[1], "active_incidents": r[2]}
                for r in self._cur.fetchall()]

    def service_analysis(self) -> list[dict]:
        self._cur.execute("""
            SELECT category, COUNT(*) AS incident_count
            FROM incidents
            GROUP BY category
            ORDER BY incident_count DESC, category ASC;
        """)
        return [{"category": r[0], "incident_count": r[1]}
                for r in self._cur.fetchall()]