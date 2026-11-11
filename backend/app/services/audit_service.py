def log_audit(cur, incident_id = None, changed_by = None, action = None, old_value  = None, new_value = None):
    cur.execute(
        """
        INSERT INTO incident_audit
            (incident_id, changed_by, action, old_value, new_value)
        VALUES (%s, %s, %s, %s, %s);
        """,
        (incident_id, changed_by, action, old_value, new_value)
    )

def getlogs(cur, incident_id:int):
    cur.execute(
        """
        SELECT id, incident_id, changed_by, action,
        old_value, new_value, changed_at
        FROM incident_audit
        WHERE incident_id = %s
        ORDER BY changed_at ASC, id ASC;
        """,(incident_id,)
    )
    rows = cur.fetchall()

    return [
        {
            "id": row[0],
            "incident_id": row[1],
            "changed_by": row[2],
            "action": row[3],
            "old_value": row[4],
            "new_value": row[5],
            "changed_at": row[6]
        }
        for row in rows
    ]

def getlogsnonincident(cur):
    cur.execute(
        """
        SELECT id, incident_id, changed_by, action,
        old_value, new_value, changed_at
        FROM incident_audit
        WHERE incident_id IS NULL
        ORDER BY changed_at ASC, id ASC;
        """
    )
    rows = cur.fetchall()

    return [
        {
            "id": row[0],
            "incident_id": row[1],
            "changed_by": row[2],
            "action": row[3],
            "old_value": row[4],
            "new_value": row[5],
            "changed_at": row[6]
        }
        for row in rows
    ]