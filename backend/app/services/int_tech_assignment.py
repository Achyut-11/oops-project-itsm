from fastapi import HTTPException

minimum_scores = {
    "P1": 70,
    "P2": 50,
    "P3": 20,
    "P4": 0
}

def int_tech_assignment(cur, incident_id):
    cur.execute(
        """
        SELECT category, priority
        FROM incidents
        WHERE id = %s;
        """,(incident_id,)
    )

    row1 = cur.fetchone()

    if row1 is None:
        raise HTTPException(
            status_code=404,
            detail="Incident does not exist"
        )

    cur.execute(
        """
        SELECT u.id, u.years_of_experience, ts.skill
        FROM users u
        JOIN technician_skills ts
            ON u.id = ts.technician_id
            WHERE u.role = 'TECHNICIAN'
                AND u.is_active = TRUE
                AND ts.skill = %s
        """,(row1[0],)
    )
    row2 = cur.fetchall()
    eligible_techs = []

    for row in row2:

        if row[1] is None:
            continue
        
        experiencescore = min(row[1]*10, 100)

        if experiencescore >=minimum_scores[row1[1]]:
            eligible_techs.append(row[0])


    if not eligible_techs:
            cur.execute(
                """
                SELECT u.id
                FROM users u
                JOIN technician_skills ts
                    on u.id = ts.technician_id
                WHERE u.role = 'TECHNICIAN'
                AND u.is_active = TRUE
                AND ts.skill = %s
                AND u.years_of_experience IS NOT NULL
                ORDER BY u.years_of_experience DESC , u.id ASC
                LIMIT 1;
                """,(row1[0],)
            )
    
            fallback_tech = cur.fetchone()

            if fallback_tech is None:
                return None

            return fallback_tech[0]
    

    cur.execute(
        """
        SELECT u.id, COUNT(i.id) AS workload
        FROM users u
        LEFT JOIN incidents i
            ON u.id = i.assigned_technician_id
            AND i.status IN ('ASSIGNED', 'ACKNOWLEDGED', 'IN_PROGRESS')
        WHERE u.id = ANY(%s)
        GROUP BY u.id
        ORDER BY workload ASC, u.id ASC
        LIMIT 1;
        """,
        (eligible_techs,)
    )

    assigned_tech = cur.fetchone()

    if assigned_tech is None:
        return None
    
    return assigned_tech[0]






    
