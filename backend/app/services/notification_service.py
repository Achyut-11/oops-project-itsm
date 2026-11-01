def create_notification(cur, user_id, incident_id, notification_type, message):
    cur.execute(
        """
        INSERT INTO notifications
            (user_id, incident_id, type, message)
        VALUES (%s, %s, %s, %s)
        RETURNING id;
        """,
        (user_id, incident_id, notification_type, message)
    )

    return cur.fetchone()[0]