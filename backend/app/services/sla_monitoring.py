from app.config import getConnection
from app.services.notification_service import create_notification

def check_sla_breaches():
    with getConnection() as con:
        with con.cursor() as cur:
            cur.execute("""
                SELECT id
                FROM users
                WHERE role = 'ADMIN'
                AND is_active = TRUE;
            """)

            admin_ids = [row[0] for row in cur.fetchall()]


            cur.execute(
                """
                UPDATE incidents
                SET 
                response_sla_breached  = TRUE

                WHERE
                    (
                        response_sla_breached IS NOT TRUE
                        AND response_deadline < CURRENT_TIMESTAMP
                        AND (
                            acknowledged_at IS NULL
                            OR acknowledged_at > response_deadline
                        )
                    )
                    RETURNING id, title, response_sla_breached, resolution_sla_breached, assigned_technician_id;
                """
            )

            breached_incidents = cur.fetchall()

            for incident in breached_incidents:
                incident_id, title, response_breached, resolution_breached, assigned_tech = incident

                for admin_id in admin_ids:
                    if response_breached:
                        create_notification(
                            cur,
                            admin_id,
                            incident_id,
                            "RESPONSE_SLA_BREACH",
                            f"Response SLA breached for incident #{incident_id}: {title}"
                        )
                if assigned_tech is not None:
                    if response_breached:
                        create_notification(
                            cur,
                            assigned_tech,
                            incident_id,
                            "RESPONSE_SLA_BREACH",
                            f"Response SLA breached for incident #{incident_id}: {title}"
                        )


            cur.execute(
                """
                UPDATE incidents
                SET 
                resolution_sla_breached  = TRUE

                WHERE
                    (
                        resolution_sla_breached IS NOT TRUE
                        AND resolution_deadline < CURRENT_TIMESTAMP
                        AND (
                            resolved_at IS NULL
                            OR resolved_at > resolution_deadline
                        )
                    )
                    RETURNING id, title, response_sla_breached, resolution_sla_breached, assigned_technician_id;
                """
            )
        
            breached_incidents = cur.fetchall()
        
            for incident in breached_incidents:
                incident_id, title, response_breached, resolution_breached, assigned_tech = incident

                for admin_id in admin_ids:
                    if resolution_breached:
                        create_notification(
                            cur,
                            admin_id,
                            incident_id,
                            "RESOLUTION_SLA_BREACH",
                            f"Resolution SLA breached for incident #{incident_id}: {title}"
                        )
                if assigned_tech is not None:
                    if resolution_breached:
                        create_notification(
                            cur,
                            assigned_tech,
                            incident_id,
                            "RESOLUTION_SLA_BREACH",
                            f"Resolution SLA breached for incident #{incident_id}: {title}"
                        )