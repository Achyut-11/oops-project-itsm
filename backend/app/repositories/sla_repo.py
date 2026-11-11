class SLARepository:

    def __init__(self, cur):
        self.cur = cur

    def get_all(self):
        self.cur.execute(
            """
            SELECT priority, response_minutes, resolution_minutes,
                   updated_at, updated_by
            FROM sla_policies
            ORDER BY priority;
            """
        )

        return self.cur.fetchall()

    def get_by_priority(self, priority):
        self.cur.execute(
            """
            SELECT priority, response_minutes, resolution_minutes,
                   updated_at, updated_by
            FROM sla_policies
            WHERE priority = %s;
            """,
            (priority,)
        )

        return self.cur.fetchone()

    def update(self, priority, response_minutes, resolution_minutes, admin_id):
        old_policy = self.get_by_priority(priority)
        self.cur.execute(
            """
            UPDATE sla_policies
            SET response_minutes = %s,
                resolution_minutes = %s,
                updated_at = CURRENT_TIMESTAMP,
                updated_by = %s
            WHERE priority = %s
            RETURNING priority, response_minutes, resolution_minutes,
                      updated_at, updated_by;
            """,
            (response_minutes, resolution_minutes, admin_id, priority)
        )
        new_policy  = self.cur.fetchone()
        return old_policy, new_policy