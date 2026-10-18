from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from app.config import getConnection
from typing import Literal
from app.services.priority_calc import priority_calc

app = FastAPI(title="ITSM SYSTEM")

class incidentCreate(BaseModel):
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
    role: Literal["EMPLOYEE", "TECHNICIAN", "ADMIN"]




allowed_transitions = {
    "NEW": ["CLASSIFIED"],
    "CLASSIFIED": ["ASSIGNED"],
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
                    SELECT id, title, description, category, status, estimated_complexity,business_criticality,affected_percentage, priority
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
                    "priority":row[8]
                }
                incidents.append(incident)

    return{"incidents" : incidents}

@app.get("/incidents/{incident_id}")
def get_incident_byid(incident_id: int):

    with getConnection() as con:  
                with con.cursor() as cur:
                    cur.execute(
                        """
                        SELECT id, title, description, category, status, estimated_complexity,business_criticality,affected_percentage, priority
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
                    "priority":row[8]
                }
    return incident
        

@app.post("/incidents")
def create_incident(incident_data:incidentCreate):

    priority = priority_calc(
    incident_data.affected_percentage,
    incident_data.business_criticality,
    incident_data.estimated_complexity
    )

    with getConnection() as con:
        with con.cursor() as cur:
            cur.execute(
                """
                INSERT INTO incidents (title, description, category, estimated_complexity, business_criticality, affected_percentage, priority)
                VALUES (%s, %s, %s,%s, %s, %s, %s)
                RETURNING id, title, description, category, status, estimated_complexity, business_criticality, affected_percentage, priority;

                """,
                (
                    incident_data.title,
                    incident_data.description,
                    incident_data.category,
                    incident_data.estimated_complexity,
                    incident_data.business_criticality,
                    incident_data.affected_percentage,
                    priority
                )
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
            "priority":row[8]
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
                RETURNING id, title, description, category, status, estimated_complexity, business_criticality, affected_percentage, priority;
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
                "priority":row[8]
            }

    return incident



@app.get("/users")
def getallusers():
    with getConnection() as con:
        with con.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, email, role, is_active, created_at
                FROM users
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
            "created_at" : row[5]
        }
        people.append(person)

    return people

@app.get("/users/{user_id}")
def getoneusers(user_id):
    with getConnection() as con:
        with con.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, email, role, is_active, created_at
                FROM users
                WHERE id = %s;
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
        "created_at" : row[5]
    }
    

    return person

@app.post("/users")
def adduser(userinfo: UserCreate):
    with getConnection() as con:
        with con.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (name, email, role)
                VALUES (%s,%s,%s)
                RETURNING id, name, email, role, is_active, created_at;
                """,(

                    userinfo.name,
                    userinfo.email,
                    userinfo.role

                )
            )
            row = cur.fetchone()

    person = {
        "id" : row[0],
        "name" : row[1],
        "email" : row[2],
        "role" : row[3],
        "is_active" : row[4],
        "created_at" : row[5]
    }
        

    return person