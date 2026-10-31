from app.config import getConnection

def check_sla_breaches():
    with getConnection() as con:
        with con.cursor() as cur:
            cur.execute(
                """
                UPDATE incidents
                SET 
                response_sla_breached  = CASE
                    WHEN response_deadline<CURRENT_TIMESTAMP
                        AND (
                            acknowledged_at IS NULL
                            OR acknowledged_at > response_deadline
                            )
                    THEN TRUE
                    ELSE response_sla_breached
                    END,
                resolution_sla_breached = CASE
                    WHEN resolution_deadline < CURRENT_TIMESTAMP
                        AND (
                            resolved_at IS NULL
                            OR resolved_at > resolution_deadline
                        )
                    THEN TRUE
                    ELSE resolution_sla_breached
                END

                WHERE
                    (
                        response_sla_breached IS NOT TRUE
                        AND response_deadline < CURRENT_TIMESTAMP
                        AND (
                            acknowledged_at IS NULL
                            OR acknowledged_at > response_deadline
                        )
                    )
                    OR
                    (
                        resolution_sla_breached IS NOT TRUE
                        AND resolution_deadline < CURRENT_TIMESTAMP
                        AND (
                            resolved_at IS NULL
                            OR resolved_at > resolution_deadline
                        )
                    );
                """
            )