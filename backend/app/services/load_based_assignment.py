def load_based_assignment(cur):
    cur.execute("""
        SELECT
            u.id,
            COUNT(i.id) AS workload
        FROM users u
        LEFT JOIN incidents i
            ON u.id = i.assigned_technician_id
            AND i.status IN ('ASSIGNED', 'ACKNOWLEDGED', 'IN_PROGRESS')
        WHERE u.role = 'TECHNICIAN'
            AND u.is_active = TRUE
        GROUP BY u.id
        ORDER BY workload ASC, u.id ASC
        LIMIT 1;
    """)

    row = cur.fetchone()

    if row is None:
        return None

    return row[0]