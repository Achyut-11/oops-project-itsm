from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from app.config import getConnection
from typing import Literal
from datetime import datetime
from app.services.priority_calc import priority_calc
from app.services.load_based_assignment import load_based_assignment
from app.services.int_tech_assignment import int_tech_assignment
from app.services.audit_service import log_audit, getlogs
from app.services.sla_service import calc_sla

app = FastAPI(title="ITSM SYSTEM")

class IncidentCreate(BaseModel):
    title:str
    description:str
    category:str

    estimated_complexity: Literal["LOW", "MEDIUM", "HIGH"]
    business_criticality: Literal["LOW", "MEDIUM", "HIGH"]
    affected_percentage: float = Field(ge=0, le=100)

    reported_by_user_id : int

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
    role: Literal["EMPLOYEE", "TECHNICIAN", "ADMIN"]
    years_of_experience: int
    skills: list[str] = []

class IncidentAssignmentUpdate(BaseModel):
    technician_id: int
    admin_id: int


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
def get_inci():
    with getConnection() as con:  
            with con.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, title, description, category, status, estimated_complexity,business_criticality,affected_percentage, priority, reported_by_user_id, assigned_technician_id,response_deadline, resolution_deadline
                    FROM incidents 
  
                    """
                )
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
                    "resolution_deadline": row[12]
                    
                }
                incidents.append(incident)

    return{"incidents" : incidents}

@app.get("/incidents/{incident_id}")
def get_incident_byid(incident_id: int):

    with getConnection() as con:  
                with con.cursor() as cur:
                    cur.execute(
                        """
                        SELECT id, title, description, category, status, estimated_complexity,business_criticality,affected_percentage, priority,reported_by_user_id, assigned_technician_id, response_deadline, resolution_deadline
                        FROM incidents 
                        WHERE id = %s;
      
                        """,
                        (incident_id,)
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
                    "resolution_deadline":row[12]
                }
    return incident
        

@app.post("/incidents")
def create_incident(incident_data:IncidentCreate):

    priority = priority_calc(
    incident_data.affected_percentage,
    incident_data.business_criticality,
    incident_data.estimated_complexity
    )

    created_at = datetime.now()

    response_deadline, resolution_deadline = calc_sla(
        priority,
        created_at
    )

    

    with getConnection() as con:
        with con.cursor() as cur:
            
            cur.execute(
                """
                SELECT id, role 
                FROM users
                WHERE id =%s
                """,
                (incident_data.reported_by_user_id,)
            )
            row = cur.fetchone()
            print("1. User fetched")
            if row is None:
                raise HTTPException(
                    status_code=404,
                    detail="User not found"
                )

            if row[1] != "EMPLOYEE":
                raise HTTPException(
                    status_code=400,
                    detail="Only employees can report incidents"
                )





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
                    incident_data.reported_by_user_id,
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
            incident_data.reported_by_user_id,
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
                RETURNING id, title, description, category, status,estimated_complexity, business_criticality,affected_percentage, priority,reported_by_user_id, assigned_technician_id,response_deadline, resolution_deadline;
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
            "resolution_deadline":row[12]
        }

    return incident




@app.patch("/incidents/{incident_id}")
def update_incident_status(incident_id: int, status_data: IncidentStatusUpdate):
    with getConnection() as con:
        with con.cursor() as cur:

            cur.execute(
                """
                SELECT id, title, description, category, status, estimated_complexity,business_criticality,affected_percentage
                FROM incidents
                WHERE id = %s
                """,
                (incident_id, )
            )


            row = cur.fetchone()
            
            if row is None:
                raise HTTPException(
                    status_code=404,
                    detail="Incident not found"
                )

            current_status = row[4]

            if(status_data.status not in allowed_transitions[current_status]):
                raise HTTPException(
                    status_code=400,
                    detail=f"cant change status from {current_status} to {status_data.status}"
                )
            
            cur.execute(
                """
                UPDATE incidents
                SET status = %s
                WHERE id = %s
                RETURNING id, title, description, category, status, estimated_complexity, business_criticality, affected_percentage, priority,reported_by_user_id,assigned_technician_id, response_deadline, resolution_deadline;
                """,
                (status_data.status, incident_id)
            )

            row = cur.fetchone()
 
            

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
                "resolution_deadline":row[12]
            }

    return incident



@app.get("/users")
def getallusers():
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
def getoneuser(user_id):
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

@app.post("/users")
def adduser(userinfo: UserCreate):
    with getConnection() as con:
        with con.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (name, email, role, years_of_experience)
                VALUES (%s,%s,%s, %s)
                RETURNING id, name, email, role, is_active, created_at, years_of_experience;
                """,(

                    userinfo.name,
                    userinfo.email,
                    userinfo.role,
                    userinfo.years_of_experience

                ) 
            )
            row = cur.fetchone()

            user_id = row[0]

            if(userinfo.role == "TECHNICIAN"):
                for skill in userinfo.skills:
                    cur.execute(
                        """
                        INSERT INTO technician_skills (technician_id, skill)
                        VALUES (%s, %s)
                        """,(
                            user_id, skill
                        )
                    )

            cur.execute(
                            """
                            SELECT skill
                            FROM technician_skills
                            WHERE technician_id = %s
                            """,(user_id,)
                        )
            skills = [row[0] for row in cur.fetchall()]

    person = {
        "id" : row[0],
        "name" : row[1],
        "email" : row[2],
        "role" : row[3],
        "is_active" : row[4],
        "created_at" : row[5],
        "years_of_experience" : row[6],
        "skills": skills
    }
        

    return person

@app.get("/incidents/{incident_id}/audit")
def gelog(incident_id : int):
    with getConnection() as con:
        with con.cursor() as cur:
            return getlogs(cur, incident_id)
        
@app.patch("/incidents/{incident_id}/assign")
def admin_assign(incident_id:int, assignment_data:IncidentAssignmentUpdate):
    with getConnection() as con:
        with con.cursor() as cur:

            cur.execute(
                """
                SELECT id
                FROM users
                WHERE id = %s
                    AND role = 'ADMIN'
                    AND is_active = TRUE;
                """,
                (assignment_data.admin_id,)
            )

            admin = cur.fetchone()

            if admin is None:
                raise HTTPException(
                    status_code=403,
                    detail="Only active admins can reassign incidents"
                )





            cur.execute("""
            SELECT assigned_technician_id, category
            FROM incidents
            WHERE id = %s
            """,(incident_id,)
            )
            row = cur.fetchone()

            if row is None:
                raise HTTPException(
                    status_code=404,
                    detail="incident nont found"
                )

            old_tech_id = row[0]
            cat = row[1]

            cur.execute("""
            SELECT u.id
            FROM users u
            JOIN technician_skills ts ON
            u.id = ts.technician_id
            WHERE u.id = %s
            AND u.role = 'TECHNICIAN'
            AND u.is_active = 'TRUE'
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
                SET assigned_technician_id = %s
                WHERE id = %s
                RETURNING id, title, category, status, assigned_technician_id,
                        response_deadline, resolution_deadline;
                """,
                (assignment_data.technician_id, incident_id)
            )

            updated_incident = cur.fetchone()

            if updated_incident is None:
                raise HTTPException(status_code=404, detail="Incident not found")

            log_audit(
                cur,
                incident_id,
                assignment_data.admin_id,
                "TECHNICIAN_REASSIGNED",
                str(old_tech_id) if old_tech_id is not None else None,
                str(assignment_data.technician_id)
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
                    "resolution_deadline": updated_incident[6]
                }
            }

