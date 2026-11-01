from app.config import getConnection
from datetime import timedelta
from app.services.notification_service import create_notification
from app.services.audit_service import log_audit
from app.services.escalation_service import escalation_delays
from app.services.int_tech_assignment import int_tech_assignment

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
                        log_audit(
                            cur,
                            incident_id,
                            assigned_tech,
                            "RESPONSE_SLA_BREACH_TECHNICIAN_NOTIFIED",
                            None,
                            None
                        )
                if response_breached:
                    log_audit(
                        cur,
                        incident_id,
                        None,
                        "RESPONSE_SLA_BREACH_ADMIN_NOTIFIED",
                        None,
                        None
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

                        log_audit(
                            cur,
                            incident_id,
                            assigned_tech,
                            "RESOLUTION_SLA_BREACH_TECHNICIAN_NOTIFIED",
                            None,
                            None
                        )
                if resolution_breached:
                    log_audit(
                        cur,
                        incident_id,
                        None,
                        "RESOLUTION_SLA_BREACH_ADMIN_NOTIFIED",
                        None,
                        None
                    )
                    

def escalation_technician_reassignment():

    with getConnection() as con:
        with con.cursor() as cur:

            cur.execute("""
                SELECT id, title, priority, assigned_technician_id
                FROM incidents
                WHERE response_sla_breached = TRUE
                AND auto_reassigned IS NOT TRUE
                AND acknowledged_at IS NULL
                AND assigned_technician_id IS NOT NULL
                AND escalation_admin_notified IS NOT TRUE;
            """)

            incidents_to_escalate = cur.fetchall()

            for incident_id, title, priority, old_technician_id in incidents_to_escalate:
                cur.execute("""
                    SELECT response_deadline
                    FROM incidents
                    WHERE id = %s;
                """, (incident_id,))

                response_deadline = cur.fetchone()[0]

                cur.execute("SELECT CURRENT_TIMESTAMP;")
                current_time = cur.fetchone()[0]

                if current_time < response_deadline + escalation_delays[priority]:
                    continue

                new_technician_id = int_tech_assignment(
                    cur,
                    incident_id,
                    old_technician_id
                )
                cur.execute("""
                    SELECT id
                    FROM users
                    WHERE role = 'ADMIN'
                    AND is_active = TRUE;
                """)
    
                admin_ids = [row[0] for row in cur.fetchall()]

                if new_technician_id is None:
                    for admin_id in admin_ids:
                        create_notification(
                            cur,
                            admin_id,
                            incident_id,
                            "AUTO_REASSIGNMENT_FAILED",
                            f"Automatic reassignment failed for incident #{incident_id}: {title}. No alternative technician is available."
                        )

                    cur.execute("""
                        UPDATE incidents
                        SET escalation_admin_notified = TRUE
                        WHERE id = %s;
                    """, (incident_id,))

                    log_audit(
                        cur,
                        incident_id,
                        None,
                        "AUTO_REASSIGNMENT_FAILED",
                        old_technician_id,
                        None
                    )

                    continue

                cur.execute("""
                    UPDATE incidents
                    SET assigned_technician_id = %s,
                        acknowledged_at = NULL,
                        auto_reassigned = TRUE,
                        reassigned_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                        AND acknowledged_at IS NULL
                    RETURNING id;
                """, (new_technician_id, incident_id))

                create_notification(
                    cur,
                    old_technician_id,
                    incident_id,
                    "INCIDENT_AUTO_REASSIGNED",
                    f"Incident #{incident_id}: {title} has been automatically reassigned to another technician."
                )

                create_notification(
                    cur,
                    new_technician_id,
                    incident_id,
                    "INCIDENT_AUTO_ASSIGNED",
                    f"Incident #{incident_id}: {title} has been assigned to you following an SLA escalation."
                )

                for admin_id in admin_ids:
                    create_notification(
                        cur,
                        admin_id,
                        incident_id,
                        "INCIDENT_AUTO_REASSIGNED",
                        f"Incident #{incident_id}: {title} was automatically reassigned     from technician {old_technician_id} to technician {new_technician_id} reassigned due to a response SLA breach."
                    )

                log_audit(
                    cur,
                    incident_id,
                    None,
                    "INCIDENT_AUTO_REASSIGNED",
                    old_technician_id,
                    new_technician_id
                )




def send_response_reminder():
    with getConnection() as con:
        with con.cursor() as cur:
            cur.execute("""
                UPDATE incidents
                SET response_reminder_sent = TRUE
                WHERE response_reminder_sent IS NOT TRUE
                AND acknowledged_at IS NULL
                AND response_deadline > CURRENT_TIMESTAMP
                AND CURRENT_TIMESTAMP >=
                    created_at + (response_deadline - created_at) / 2
                RETURNING id, title, assigned_technician_id;
            """)

            reminder_incidents = cur.fetchall()

            for incident_id, title, assigned_technician_id in reminder_incidents:
                if assigned_technician_id is not None:
                    create_notification(
                        cur,
                        assigned_technician_id,
                        incident_id,
                        "RESPONSE_SLA_REMINDER",
                        f"Reminder: Please acknowledge incident #{incident_id}: {title}"
                    )

                    log_audit(
                        cur,
                        incident_id,
                        assigned_technician_id,
                        "RESPONSE_SLA_REMINDER_SENT",
                        None,
                        None
                    )

def send_resolution_reminder():
    with getConnection() as con:
        with con.cursor() as cur:
            cur.execute("""
                UPDATE incidents
                SET resolution_reminder_sent = TRUE
                WHERE resolution_reminder_sent IS NOT TRUE
                AND resolved_at IS NULL
                AND resolution_deadline > CURRENT_TIMESTAMP
                AND CURRENT_TIMESTAMP >=
                    created_at + (resolution_deadline - created_at) / 2
                RETURNING id, title, assigned_technician_id;
            """)

            reminder_incidents = cur.fetchall()
    
            for incident_id, title, assigned_technician_id in reminder_incidents:
                if assigned_technician_id is not None:
                    create_notification(
                        cur,
                        assigned_technician_id,
                        incident_id,
                        "RESOLUTION_SLA_REMINDER",
                        f"Reminder: Incident: #{incident_id}: {title} is approaching its deadline"
                    )

                log_audit(
                    cur,
                    incident_id,
                    assigned_technician_id,
                    "RESOLUTION_SLA_REMINDER_SENT",
                    None,
                    None
                )


def check_post_reassignment_acknowledgement():
    with getConnection() as con:
        with con.cursor() as cur:

            cur.execute("""
                SELECT id
                FROM users
                WHERE role = 'ADMIN'
                AND is_active = TRUE;
            """)

            admin_ids = [row[0] for row in cur.fetchall()]

            cur.execute("""
                SELECT id, title, priority, assigned_technician_id, reassigned_at
                FROM incidents
                WHERE auto_reassigned = TRUE
                AND acknowledged_at IS NULL
                AND escalation_admin_notified IS NOT TRUE;
            """)
            incidents_to_check = cur.fetchall()

            cur.execute("SELECT CURRENT_TIMESTAMP;")
            current_time = cur.fetchone()[0]
            
            

            for incident_id, title, priority, assigned_tech, reassigned_at in incidents_to_check:

               
                if current_time < reassigned_at + escalation_delays[priority]:
                    continue

               
                for admin_id in admin_ids:
                    create_notification(
                        cur,
                        admin_id,
                        incident_id,
                        "REPLACEMENT_TECHNICIAN_UNACKNOWLEDGED",
                        f"Replacement technician {assigned_tech} has not acknowledged incident #{incident_id}: {title}. Manual intervention required."
                    )

                cur.execute("""
                    UPDATE incidents
                    SET escalation_admin_notified = TRUE
                    WHERE id = %s;
                """, (incident_id,))

                log_audit(
                    cur,
                    incident_id,
                    None,
                    "REPLACEMENT_TECHNICIAN_FAILED_TO_ACKNOWLEDGE",
                    None,
                    None
                )

def check_all_sla_events():
    send_response_reminder()
    send_resolution_reminder()
    check_sla_breaches()
    escalation_technician_reassignment()
    check_post_reassignment_acknowledgement()