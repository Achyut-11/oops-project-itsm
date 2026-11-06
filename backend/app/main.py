from fastapi import FastAPI, HTTPException, Query, Depends
from contextlib import asynccontextmanager
from pydantic import BaseModel, Field, model_validator
from app.config import getConnection
from typing import Literal, Annotated
from datetime import datetime, timezone
from app.services.priority_calc import priority_calc
from app.services.load_based_assignment import load_based_assignment
from app.services.int_tech_assignment import int_tech_assignment
from app.services.audit_service import log_audit, getlogs
from app.services.sla_service import calc_sla
from app.services.sla_scheduler import stop_scheduler, start_scheduler
from app.services.notification_service import create_notification
from datetime import date, timedelta
from app.auth.security import hash_password, verify_password, create_access_token
from app.auth.dependencies import get_current_user, require_employee, require_technician, require_admin

@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(lifespan=lifespan)

class IncidentCreate(BaseModel):
    title:str
    description:str
    category:str

    estimated_complexity: Literal["LOW", "MEDIUM", "HIGH"]
    business_criticality: Literal["LOW", "MEDIUM", "HIGH"]
    affected_percentage: float = Field(ge=0, le=100)

class IncidentStatusUpdate(BaseModel):
    status: Literal[
         "NEW",
         "CLASSIFIED",
         "ASSIGNED",
         "ACKNOWLEDGED",
         "IN_PROGRESS",
         "RESOLVED",
         "VERIFIED",
         "CLOSED"
        ]
class UserCreate(BaseModel):
    name:str
    email:str
    role: Literal["TECHNICIAN", "ADMIN"]
    years_of_experience: int
    skills: list[str] = Field(default_factory=list)
    password: str = Field(min_length=8)

class IncidentAssignmentUpdate(BaseModel):
    technician_id: int

class IncidentQuery(BaseModel):
    status : Literal["NEW", "ASSIGNED", "ACKNOWLEDGED","IN_PROGRESS", "RESOLVED", "VERIFIED", "CLOSED"]|None =None
    priority : Literal["P1","P2","P3","P4"]|None =None
    category : str|None =None
    assigned_technician_id : int|None =None
    start_date : date|None =None
    end_date: date | None = None
    response_sla_breached: bool | None = None
    resolution_sla_breached: bool | None = None

    @model_validator(mode="after")
    def validate_dates(self):
        if self.start_date is not None and self.end_date is not None:
            if self.start_date > self.end_date:
                raise ValueError("start_date cannot be after end_date")

        return self

class UserRegister(BaseModel):
    name: str
    email: str
    password: str = Field(min_length=8)


class UserLogin(BaseModel):
    email: str
    password: str

class AdminSetup(BaseModel):
    name: str
    email: str
    password: str = Field(min_length=8)

class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)

allowed_transitions = {
    "NEW": ["ASSIGNED"],
    "ASSIGNED": ["ACKNOWLEDGED"],
    "ACKNOWLEDGED": ["IN_PROGRESS"],
    "IN_PROGRESS": ["RESOLVED"],
    "RESOLVED": ["VERIFIED"],
    "VERIFIED": ["CLOSED"],
    "CLOSED": []
}



@app.get("/")
def home():
     return{"message" : "backen is running"}


@app.get("/incidents")
def get_incidents(incident_query:Annotated[IncidentQuery, Query()],  current_user: dict = Depends(get_current_user)):
    with getConnection() as con:  
            with con.cursor() as cur:
                query = """
                        SELECT id, title, description, category, status, estimated_complexity,business_criticality,affected_percentage, priority, reported_by_user_id, assigned_technician_id,response_deadline, resolution_deadline, acknowledged_at,resolved_at,response_sla_breached,resolution_sla_breached
                        FROM incidents
                        WHERE TRUE
    
                        """
                
                params = []
                if current_user["role"] == "EMPLOYEE":
                    query += " AND reported_by_user_id = %s"
                    params.append(current_user["id"])

                elif current_user["role"] == "TECHNICIAN":
                    query += " AND assigned_technician_id = %s"
                    params.append(current_user["id"])


                if incident_query.status is not None:
                    query += " AND status = %s"
                    params.append(incident_query.status)

                if incident_query.priority is not None:
                    query += " AND priority = %s"
                    params.append(incident_query.priority)

                if incident_query.category is not None:
                    query += " AND category = %s"
                    params.append(incident_query.category)

                if incident_query.assigned_technician_id is not None:
                    query += " AND assigned_technician_id = %s"
                    params.append(incident_query.assigned_technician_id)

                if incident_query.start_date is not None:
                    query += " AND created_at >= %s"
                    params.append(incident_query.start_date)

                if incident_query.end_date is not None:
                    query += " AND created_at < %s"
                    params.append(incident_query.end_date + timedelta(days=1))

                if incident_query.response_sla_breached is not None:
                    query += " AND response_sla_breached = %s"
                    params.append(incident_query.response_sla_breached)

                if incident_query.resolution_sla_breached is not None:
                    query += " AND resolution_sla_breached = %s"
                    params.append(incident_query.resolution_sla_breached)

                query += " ORDER BY id ASC"
                cur.execute(query, params)
                
                rows = cur.fetchall()

            incidents=[]

            for row in rows:
                incident = {
                    "id": row[0],
                    "title": row[1],
                    "description": row[2],
                    "category": row[3],
                    "status": row[4],
                    "estimated_complexity": row[5],
                    "business_criticality": row[6],
                    "affected_percentage": float(row[7]),
                    "priority":row[8],
                    "reported_by_user_id":row[9],
                    "assigned_technician_id":row[10],
                    "response_deadline":row[11],
                    "resolution_deadline": row[12],
                    "acknowledged_at" : row[13],
                    "resolved_at": row[14],
                    "response_sla_breached" :row[15],
                    "resolution_sla_breached" : row[16]
                    
                }
                incidents.append(incident)

    return{"incidents" : incidents}

@app.get("/incidents/{incident_id}")
def get_incident_byid(incident_id: int, current_user: dict = Depends(get_current_user)):

    with getConnection() as con:  
                with con.cursor() as cur:
                    if current_user["role"] == "ADMIN":
                        cur.execute(
                            """
                            SELECT id, title, description, category, status, estimated_complexity,business_criticality,affected_percentage, priority,reported_by_user_id, assigned_technician_id, response_deadline, resolution_deadline, acknowledged_at,resolved_at
                            FROM incidents 
                            WHERE id = %s;
        
                            """,
                            (incident_id,)
                        )
                    elif current_user["role"] == "TECHNICIAN":
                        cur.execute(
                            """
                            SELECT id, title, description, category, status,
                                estimated_complexity, business_criticality,
                                affected_percentage, priority, reported_by_user_id,
                                assigned_technician_id, response_deadline,
                                resolution_deadline, acknowledged_at, resolved_at
                            FROM incidents
                            WHERE id = %s AND assigned_technician_id = %s
                            """,
                            (incident_id, current_user["id"])
                        )

                    else:  # EMPLOYEE
                        cur.execute(
                            """
                            SELECT id, title, description, category, status,
                                estimated_complexity, business_criticality,
                                affected_percentage, priority, reported_by_user_id,
                                assigned_technician_id, response_deadline,
                                resolution_deadline, acknowledged_at, resolved_at
                            FROM incidents
                            WHERE id = %s AND reported_by_user_id = %s
                            """,
                            (incident_id, current_user["id"])
                        )
                    row = cur.fetchone()


                if row is None:
                    raise HTTPException(
                            status_code = 404,
                            detail="incident not found"
                        )
    
                
                incident = {
                    "id": row[0],
                    "title": row[1],
                    "description": row[2],
                    "category": row[3],
                    "status": row[4],
                    "estimated_complexity": row[5],
                    "business_criticality": row[6],
                    "affected_percentage": float(row[7]),
                    "priority":row[8],
                    "reported_by_user_id":row[9],
                    "assigned_technician_id":row[10],
                    "response_deadline":row[11],
                    "resolution_deadline":row[12],
                    "acknowledged_at" : row[13],
                    "resolved_at": row[14]
                }
    return incident
        

@app.post("/incidents")
def create_incident(incident_data:IncidentCreate, current_user:dict = Depends(require_employee)):

    priority = priority_calc(
    incident_data.affected_percentage,
    incident_data.business_criticality,
    incident_data.estimated_complexity
    )

    created_at = datetime.now(timezone.utc)

    response_deadline, resolution_deadline = calc_sla(
        priority,
        created_at
    )

    

    with getConnection() as con:
        with con.cursor() as cur:
               
            cur.execute(
                """
                INSERT INTO incidents (title, description, category, estimated_complexity, business_criticality, affected_percentage, priority,reported_by_user_id, response_deadline, resolution_deadline)
                VALUES (%s, %s, %s,%s, %s, %s, %s, %s, %s, %s)
                RETURNING id, title, description, category, status,estimated_complexity, business_criticality,affected_percentage, priority,reported_by_user_id,response_deadline, resolution_deadline;
                """,
                (
                    incident_data.title,
                    incident_data.description,
                    incident_data.category,
                    incident_data.estimated_complexity,
                    incident_data.business_criticality,
                    incident_data.affected_percentage,
                    priority,
                    current_user["id"],
                    response_deadline, 
                    resolution_deadline
                    
                )
            )
            

            row = cur.fetchone()
            
            print("2. Incident fetched:", row)
            incident_id = row[0]

            log_audit(
            cur,
            incident_id,
            current_user["id"],
            "INCIDENT_CREATED",
            None,
            "NEW"
        )
            
            print("3. Creation audit logged")

            assigned_technician_id = int_tech_assignment(cur, incident_id)

            if assigned_technician_id is None:
                raise HTTPException(
                    status_code=503,
                    detail="No suitable technician is currently available"
                )

            print("4. Technician assigned:", assigned_technician_id)

           
    
            cur.execute("""
                UPDATE incidents
                SET status = %s, assigned_technician_id = %s
                WHERE id = %s
                RETURNING id, title, description, category, status,estimated_complexity, business_criticality,affected_percentage, priority,reported_by_user_id, assigned_technician_id,response_deadline, resolution_deadline, acknowledged_at,resolved_at;
                """, ("ASSIGNED", assigned_technician_id, row[0]))
           

            row = cur.fetchone()
            print("5. Updated incident fetched:", row)


            log_audit(
                    cur,
                    incident_id,
                    None, 
                    "TECHNICIAN_ASSIGNED",
                    None,
                    str(assigned_technician_id)
                )
            create_notification(
                cur,
                assigned_technician_id,
                incident_id,
                "INCIDENT_ASSIGNED",
                f"You have been assigned incident #{incident_id}: {row[1]}"
            )


            

            incident = {
            "id": row[0],
            "title": row[1],
            "description": row[2],
            "category": row[3],
            "status": row[4],
            "estimated_complexity": row[5],
            "business_criticality": row[6],
            "affected_percentage": float(row[7]),
            "priority":row[8],
            "reported_by_user_id":row[9],
            "assigned_technician_id":row[10],
            "response_deadline":row[11],
            "resolution_deadline":row[12],
            "acknowledged_at" : row[13],
            "resolved_at": row[14]
        }

    return incident




@app.patch("/incidents/{incident_id}")
def update_incident_status(incident_id: int, status_data: IncidentStatusUpdate, current_user: dict = Depends(get_current_user)):
    with getConnection() as con:
        with con.cursor() as cur:
            

            cur.execute(
                """
                SELECT id, title, description, category, status, estimated_complexity,business_criticality,affected_percentage, assigned_technician_id
                FROM incidents
                WHERE id = %s
                """,
                (incident_id, )
            )

            row = cur.fetchone()

            if current_user["role"] == "TECHNICIAN":
                if current_user["id"] != row[8]:
                    raise HTTPException(
                        status_code=403,
                        detail="You can only update incidents assigned to you"
                    )
            if current_user["role"] == "EMPLOYEE":
            
                raise HTTPException(
                    status_code=403,
                    detail="Only technicians and admins can update incidents"
                )
            
            if row is None:
                raise HTTPException(
                    status_code=404,
                    detail="Incident not found"
                )

            current_status = row[4]

            if status_data.status == "ACKNOWLEDGED":
                raise HTTPException(
                    status_code=400,
                    detail="Use the acknowledgement endpoint to acknowledge incidents"
                )

            if(status_data.status not in allowed_transitions[current_status]):
                raise HTTPException(
                    status_code=400,
                    detail=f"cant change status from {current_status} to {status_data.status}"
                )
            
            cur.execute(
                """
                UPDATE incidents
                SET status = %s,

                 acknowledged_at = CASE
                    WHEN %s = 'ACKNOWLEDGED' AND acknowledged_at IS NULL
                    THEN CURRENT_TIMESTAMP
                    ELSE acknowledged_at
                END,

                resolved_at = CASE
                    WHEN %s = 'RESOLVED' AND resolved_at IS NULL
                    THEN CURRENT_TIMESTAMP
                    ELSE resolved_at
                END

                WHERE id = %s

                RETURNING id, title, description, category, status, estimated_complexity, business_criticality, affected_percentage, priority,reported_by_user_id,assigned_technician_id, response_deadline, resolution_deadline, acknowledged_at, resolved_at;
                """,
                (status_data.status, status_data.status, status_data.status, incident_id)
            )

            row = cur.fetchone()

            log_audit(
                cur,
                incident_id,
                current_user["id"],
                "STATUS_CHANGED",
                current_status,
                status_data.status
            )

            create_notification(
                cur,
                row[9],  
                incident_id,
                "INCIDENT_STATUS_CHANGED",
                f"Your incident #{incident_id} status has changed "
                f"from {current_status} to {status_data.status}."
            )
 
            

            incident = {
                "id": row[0],
                "title": row[1],
                "description": row[2],
                "category": row[3],
                "status": row[4],
                "estimated_complexity": row[5],
                "business_criticality": row[6],
                "affected_percentage": float(row[7]),
                "priority":row[8],
                "reported_by_user_id":row[9],
                "assigned_technician_id":row[10],
                "response_deadline":row[11],
                "resolution_deadline":row[12],
                "acknowledged_at" : row[13],
                "resolved_at": row[14]
            }

    return incident

@app.patch("/incidents/{incident_id}/acknowledge")
def acknowledge(incident_id : int,  current_user: dict = Depends(require_technician)):
    with getConnection() as con:
        with con.cursor() as cur:
            cur.execute(
                """
                SELECT status, assigned_technician_id, acknowledged_at
                FROM incidents
                WHERE id = %s
                """,(incident_id,)
            )

            row = cur.fetchone()

            if row is None:
                raise HTTPException(
                    status_code=404,
                    detail="Incident not found"
                )

            if row[1] !=current_user["id"]:
                raise HTTPException(
                    status_code=403,
                    detail="Unauthorized user"
                )

            if row[2] is not None:
                raise HTTPException(
                    status_code=400,
                    detail="incident has already been acknowledged"
                )

            if row[0] != "ASSIGNED":
                raise HTTPException(
                    status_code=400,
                    detail="Only incidents with ASSIGNED status can be acknowledged"
                )

            cur.execute(
                """
                UPDATE incidents
                SET status = 'ACKNOWLEDGED',
                    acknowledged_at = CURRENT_TIMESTAMP
                WHERE id = %s
                AND status = 'ASSIGNED'
                AND  acknowledged_at IS NULL
                RETURNING id, status, acknowledged_at, reported_by_user_id
                """,(incident_id,)
            )
            updated_row = cur.fetchone()

            if updated_row is None:
                raise HTTPException(
                    status_code= 409,
                    detail="Incident could not be acknowledged because it was reassigned or already acknowledged. Please refresh and try again."
                )
            log_audit(
                cur,
                incident_id,
                current_user["id"],
                "INCIDENT_ACKNOWLEDGED",
                "ASSIGNED",
                "ACKNOWLEDGED"
            )
            create_notification(cur, updated_row[3], incident_id, "INCIDENT_ACKNOWLEDGED", f"Your incident #{incident_id} has been acknowledged")
            

            return{
                "id":updated_row[0],
                "status":updated_row[1],
                "acknowledged_at":updated_row[2]
            }

@app.post("/users")
def adduser(
    userinfo: UserCreate,
    current_user: dict = Depends(require_admin)
):
    hashed_password = hash_password(userinfo.password)

    with getConnection() as con:
        with con.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users
                    (name, email, role, years_of_experience, password_hash)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, name, email, role, is_active,
                          created_at, years_of_experience;
                """,
                (
                    userinfo.name,
                    userinfo.email,
                    userinfo.role,
                    userinfo.years_of_experience,
                    hashed_password
                )
            )

            row = cur.fetchone()
            user_id = row[0]

            if userinfo.role == "TECHNICIAN":
                for skill in userinfo.skills:
                    cur.execute(
                        """
                        INSERT INTO technician_skills (technician_id, skill)
                        VALUES (%s, %s)
                        """,
                        (user_id, skill)
                    )

            cur.execute(
                """
                SELECT skill
                FROM technician_skills
                WHERE technician_id = %s
                """,
                (user_id,)
            )
            skills = [skill_row[0] for skill_row in cur.fetchall()]

    return {
        "id": row[0],
        "name": row[1],
        "email": row[2],
        "role": row[3],
        "is_active": row[4],
        "created_at": row[5],
        "years_of_experience": row[6],
        "skills": skills
    }
@app.post("/auth/setup_admin")
def setup_admin(admin_data: AdminSetup):
    with getConnection() as con:
        with con.cursor() as cur:

            cur.execute("SELECT pg_advisory_xact_lock(123456789)")

            cur.execute(
                """
                SELECT EXISTS (
                    SELECT 1 FROM users
                    WHERE role = 'ADMIN'
                )
                """
            )

            admin_exists = cur.fetchone()[0]

            if admin_exists:
                raise HTTPException(
                    status_code=403,
                    detail="Admin setup has already been completed"
                )

            hashed_password = hash_password(admin_data.password)

            cur.execute(
                """
                INSERT INTO users
                    (name, email, role, years_of_experience,
                     password_hash, is_active)
                VALUES (%s, %s, 'ADMIN', 0, %s, TRUE)
                RETURNING id, name, email, role
                """,
                (
                    admin_data.name,
                    admin_data.email,
                    hashed_password
                )
            )

            row = cur.fetchone()

    return {
        "message": "Initial admin created successfully",
        "user": {
            "id": row[0],
            "name": row[1],
            "email": row[2],
            "role": row[3]
        }
    }


@app.get("/users")
def getallusers(current_user : dict = Depends(require_admin)):
    with getConnection() as con:
        with con.cursor() as cur:
            cur.execute(
                """
                SELECT u.id, u.name, u.email, u.role, u.is_active, u.created_at, u.years_of_experience,
                COALESCE(
                    ARRAY_AGG(ts.skill) FILTER (WHERE ts.skill IS NOT NULL),
                    ARRAY[]::VARCHAR[]
                ) AS skills
                FROM users u
                LEFT JOIN technician_skills ts
                    on u.id = ts.technician_id
                GROUP BY u.id
                ORDER BY u.id
                """
            )
            rows = cur.fetchall()
    people =[]

    for row in rows:
        person = {
            "id" : row[0],
            "name" : row[1],
            "email" : row[2],
            "role" : row[3],
            "is_active" : row[4],
            "created_at" : row[5],
            "years_of_experience": row[6],
            "skills":row[7]
        }
        people.append(person)

    return people

@app.get("/users/{user_id}")
def getoneuser(user_id:int, current_user : dict = Depends(get_current_user)):

    if current_user["role"]!="ADMIN" and current_user["id"]!=user_id:
        raise HTTPException(
            status_code=403,
            detail="User Information can only be viewed by admins and the user themselves"
        )
    
    with getConnection() as con:
        with con.cursor() as cur:
            cur.execute(
                """
                SELECT u.id, u.name, u.email, u.role, u.is_active, u.created_at, u.years_of_experience,
                COALESCE(
                    ARRAY_AGG(ts.skill) FILTER (WHERE ts.skill IS NOT NULL),
                    ARRAY[]::VARCHAR[]
                ) AS skills
                FROM users u
                LEFT JOIN technician_skills ts
                    on u.id = ts.technician_id
                WHERE u.id = %s
                GROUP BY u.id
                ORDER BY u.id;
                
                """,
                (user_id,)
            )
            row = cur.fetchone()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail="user not found"
        )

    person = {
        "id" : row[0],
        "name" : row[1],
        "email" : row[2],
        "role" : row[3],
        "is_active" : row[4],
        "created_at" : row[5],
        "years_of_experience": row[6],
        "skills" : row[7]
    }
    

    return person

@app.get("/incidents/{incident_id}/audit")
def gelog(incident_id : int, current_user : dict = Depends(require_admin)):
    with getConnection() as con:
        with con.cursor() as cur:
            return getlogs(cur, incident_id)
        
@app.patch("/incidents/{incident_id}/assign")
def admin_assign(incident_id:int, assignment_data:IncidentAssignmentUpdate, current_user : dict = Depends(require_admin)):
    with getConnection() as con:
        with con.cursor() as cur:

            cur.execute("""
            SELECT assigned_technician_id, category, status, reported_by_user_id
            FROM incidents
            WHERE id = %s
            """,(incident_id,)
            )
            row = cur.fetchone()

            if row is None:
                raise HTTPException(
                    status_code=404,
                    detail="incident not found"
                )
            
            if old_status not in ("ASSIGNED", "ACKNOWLEDGED"):
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot reassign an incident in {old_status} status"
                )

            if assignment_data.technician_id == old_tech_id:
                raise HTTPException(
                    status_code=400,
                    detail="Incident is already assigned to this technician"
                )

            old_tech_id = row[0]
            cat = row[1]
            old_status = row[2]
            reported_by_user_id = row[3]

            cur.execute("""
            SELECT u.id
            FROM users u
            JOIN technician_skills ts ON
            u.id = ts.technician_id
            WHERE u.id = %s
            AND u.role = 'TECHNICIAN'
            AND u.is_active = TRUE
            AND ts.skill = %s           
            """,(assignment_data.technician_id, cat)
            )

            row = cur.fetchone()

            if row is None:
                raise HTTPException(
                    status_code=400,
                    detail="invalid tech, tech must be active and from the same specialization as the cat" 
                )

            cur.execute(
                """
                UPDATE incidents
                SET assigned_technician_id = %s,
                status = 'ASSIGNED'
                acknowledged_at = NULL,
                auto_reassigned = TRUE,
                reassigned_at = CURRENT_TIMESTAMP,
                escalation_admin_notified = FALSE

                WHERE id = %s
                RETURNING id, title, category, status, assigned_technician_id,
                        response_deadline, resolution_deadline, acknowledged_at,resolved_at
                """,
                (assignment_data.technician_id, incident_id)
            )

            updated_incident = cur.fetchone()

            if updated_incident is None:
                raise HTTPException(status_code=404, detail="Incident not found")

            if old_status == "ACKNOWLEDGED":
                log_audit(
                    cur,
                    incident_id,
                    current_user["id"],
                    "STATUS_CHANGED",
                    "ACKNOWLEDGED",
                    "ASSIGNED"
                )
            

            log_audit(
                cur,
                incident_id,
                current_user["id"],
                "TECHNICIAN_REASSIGNED",
                str(old_tech_id) if old_tech_id is not None else None,
                str(assignment_data.technician_id)
            )

            create_notification(
                cur,
                assignment_data.technician_id,
                incident_id,
                "INCIDENT_REASSIGNED_BY_ADMIN",
                f"You have been assigned incident #{incident_id}: {updated_incident[1]}"
            )
            create_notification(
                cur,
                reported_by_user_id,
                incident_id,
                "INCIDENT_TECHNICIAN_CHANGED",
                f"The technician handling your incident #{incident_id} has changed."
            )
            if old_tech_id is not None:
                create_notification(
                    cur,
                    old_tech_id,
                    incident_id,
                    "INCIDENT_REASSIGNED_BY_ADMIN",
                    f"Your incident with the following details has been reassigned #{incident_id}: {updated_incident[1]}"
                )

            return {
                "message": "Technician reassigned successfully",
                "incident": {
                    "id": updated_incident[0],
                    "title": updated_incident[1],
                    "category": updated_incident[2],
                    "status": updated_incident[3],
                    "assigned_technician_id": updated_incident[4],
                    "response_deadline": updated_incident[5],
                    "resolution_deadline": updated_incident[6],
                    "acknowledged_at" : updated_incident[7],
                    "resolved_at": updated_incident[8]
                }
            }

@app.get("/notifications")
def getallnotifications(current_user : dict = Depends(require_admin)):
    with getConnection() as con:
        with con.cursor() as cur:
            cur.execute(
                """
                SELECT id, user_id, incident_id, type, message, is_read, created_at
                FROM notifications
                """
            )

            rows = cur.fetchall()

        notifications = []

        for row in rows:
            notif = {
                "id": row[0],
                "user_id": row[1],
                "incident_id": row[2],
                "type": row[3],
                "message": row[4],
                "is_read": row[5],
                "created_at": row[6]
            }

            notifications.append(notif)

        return notifications


@app.get("/notifications/me")
def getusernotifications(current_user : dict = Depends(get_current_user)):

    with getConnection() as con:
        with con.cursor() as cur:
            cur.execute(
                """
                SELECT id, user_id, incident_id, type, message, is_read, created_at
                FROM notifications
                WHERE user_id = %s
                """,(current_user["id"],)
            )

            rows = cur.fetchall()

        notifications = []

        for row in rows:
            notif = {
                "id": row[0],
                "user_id": row[1],
                "incident_id": row[2],
                "type": row[3],
                "message": row[4],
                "is_read": row[5],
                "created_at": row[6]
            }

            notifications.append(notif)

        return notifications

@app.patch("/notifications/{notification_id}/read")
def readnotification(notification_id: int, current_user : dict = Depends(get_current_user)):
    with getConnection() as con:
        with con.cursor() as cur:
            if current_user["role"] == "ADMIN":
                cur.execute(
                    """
                    SELECT user_id FROM notifications
                    WHERE id = %s AND is_read IS FALSE
                    """,
                    (notification_id,)
                )
            else:
                cur.execute(
                    """
                    SELECT user_id FROM notifications
                    WHERE id = %s
                    AND user_id = %s
                    AND is_read IS FALSE
                    """,
                    (notification_id, current_user["id"])
                )
            row = cur.fetchone()

            if row is None:
                raise HTTPException(
                    status_code=404,
                    detail="notification not found"
                )
            
            if current_user["role"] == "ADMIN":
                cur.execute(
                    """
                    UPDATE notifications
                    SET is_read = TRUE
                    WHERE id = %s AND is_read IS FALSE
                    RETURNING id, is_read, user_id
                    """,
                    (notification_id,)
                )
            else:
                cur.execute(
                    """
                    UPDATE notifications
                    SET is_read = TRUE
                    WHERE id = %s
                    AND user_id = %s
                    AND is_read IS FALSE
                    RETURNING id, is_read, user_id
                    """,
                    (notification_id, current_user["id"])
                )

            row = cur.fetchone()

            
        return {
            "message": "Notification marked as read",
            "id": row[0],
            "is_read": row[1]
        }


@app.get("/reports/overview")
def report_overview(current_user : dict = Depends(require_admin)):
    with getConnection() as con:
        with con.cursor() as cur:
            cur.execute("""
                SELECT
                    COUNT(*),
                    COUNT(*) FILTER (WHERE status NOT IN ('RESOLVED','VERIFIED','CLOSED')),
                    COUNT(*) FILTER (WHERE priority = 'P1'),
                    COUNT(*) FILTER (WHERE status IN ('RESOLVED','VERIFIED','CLOSED')),
                    COUNT(*) FILTER (WHERE response_sla_breached OR resolution_sla_breached)
                FROM incidents;
            """)
            r = cur.fetchone()
    return {
        "total": r[0],
        "open": r[1],
        "critical": r[2],
        "resolved": r[3],
        "sla_violations": r[4],
    }

@app.get("/reports/technician-workload")
def report_technician_workload(current_user : dict = Depends(require_admin)):
    with getConnection() as con:
        with con.cursor() as cur:
            cur.execute("""
                SELECT u.id, u.name, COUNT(i.id) AS active_incidents
                FROM users u
                LEFT JOIN incidents i
                    ON u.id = i.assigned_technician_id
                    AND i.status IN ('ASSIGNED', 'ACKNOWLEDGED', 'IN_PROGRESS')
                WHERE u.role = 'TECHNICIAN'
                    AND u.is_active = TRUE
                GROUP BY u.id, u.name
                ORDER BY active_incidents DESC, u.id ASC;
            """)
            rows = cur.fetchall()

    return [
        {
            "technician_id": row[0],
            "name": row[1],
            "active_incidents": row[2]
        }
        for row in rows
    ]


@app.get("/reports/service-analysis")
def report_service_analysis(current_user : dict = Depends(require_admin)):
    with getConnection() as con:
        with con.cursor() as cur:
            cur.execute("""
                SELECT category, COUNT(*) AS incident_count
                FROM incidents
                GROUP BY category
                ORDER BY incident_count DESC, category ASC;
            """)
            rows = cur.fetchall()

    return [
        {
            "category": row[0],
            "incident_count": row[1]
        }
        for row in rows
    ]

@app.post("/auth/register")
def register_user(user: UserRegister):
    with getConnection() as con:
        with con.cursor() as cur:
            cur.execute(
                """
                SELECT email FROM users
                WHERE email = %s
                """,(user.email,)
            )

            row = cur.fetchone()

            if row is not None:
                raise HTTPException(
                    status_code=409,
                    detail="email already registered"
                )
            
            hashed_password = hash_password(user.password)
            cur.execute(
                            """
                            INSERT INTO users (name, email, role, password_hash)
                            VALUES (%s, %s, 'EMPLOYEE', %s)
                            RETURNING id, name, email, role
                            """,
                            (user.name, user.email, hashed_password)
                        )

            row = cur.fetchone()

        return {
            "id": row[0],
            "name": row[1],
            "email": row[2],
            "role": row[3],
            "message": "Registration successful"
        }


@app.post("/auth/login")
def login(user: UserLogin):
    with getConnection() as con:
        with con.cursor() as cur:

            cur.execute(
                """
                SELECT id, name, email, role, password_hash, token_version
                FROM users
                WHERE email = %s
                """,
                (user.email,)
            )

            row = cur.fetchone()

            if row is None:
                raise HTTPException(
                    status_code=401,
                    detail="Invalid email or password"
                )

            if not verify_password(user.password, row[4]):
                raise HTTPException(
                    status_code=401,
                    detail="Invalid email or password"
                )

            access_token = create_access_token({
                "token_version": row[5],
                "user_id": row[0],
                "role": row[3]
            })

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": row[0],
            "name": row[1],
            "email": row[2],
            "role": row[3]
        }
    }

@app.patch("/auth/change-password")
def change_password(
    password_data: PasswordChange,
    current_user: dict = Depends(get_current_user)
):
    with getConnection() as con:
        with con.cursor() as cur:
            cur.execute(
                """
                SELECT password_hash
                FROM users
                WHERE id = %s
                """,
                (current_user["id"],)
            )

            row = cur.fetchone()

            if row is None or not verify_password(password_data.current_password, row[0]):
                raise HTTPException(
                    status_code=400,
                    detail="Current password is incorrect"
                )

            new_hash = hash_password(password_data.new_password)

            cur.execute(
                """
                UPDATE users
                SET password_hash = %s,
                token_version = token_version+1
                WHERE id = %s
                """,
                (new_hash, current_user["id"])
            )

    return {"message": "Password changed successfully"}