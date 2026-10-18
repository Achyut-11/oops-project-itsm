from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import psycopg
from config import dbpassword, getConnection
from typing import Literal

app = FastAPI(title="ITSM SYSTEM")

class incidentCreate(BaseModel):
    title:str
    description:str
    category:str

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


incidents = []
next_id = 1



@app.get("/")
def home():
     return{"message" : "backen is running"}


@app.get("/incidents")
def get_inci():
    with getConnection() as con:  
            with con.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, title, description, category, status
                    FROM incidents 
  
                    """
                )
                rows = cur.fetchall()

            incidents=[]

            for row in rows:
                incident = {
                    "id" : row[0],
                    "title" : row[1],
                    "description" : row[2],
                    "category" :  row[3],
                    "status" :  row[4]
                }
                incidents.append(incident)

    return{"incidents" : incidents}

@app.get("/incidents/{incident_id}")
def get_incident_byid(incident_id: int):

    with getConnection() as con:  
                with con.cursor() as cur:
                    cur.execute(
                        """
                        SELECT id, title, description, category, status
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
                    "id" : row[0],
                    "title" : row[1],
                    "description" : row[2],
                    "category" :  row[3],
                    "status" :  row[4]
                }
    return incident
        

@app.post("/incidents")
def create_incident(incident_data:incidentCreate):
    with getConnection() as con:
        with con.cursor() as cur:
            cur.execute(
                """
                INSERT INTO incidents (title, description, category)
                VALUES (%s, %s, %s)
                RETURNING id, title, description, category, status

                """,
                (
                    incident_data.title,
                    incident_data.description,
                    incident_data.category
                )
            )

            row = cur.fetchone()

            incident = {
                "id" : row[0],
                "title" : row[1],
                "description" : row[2],
                "category" :  row[3],
                "status" :  row[4]
                }

    return incident




@app.patch("/incidents/{incident_id}")
def update_incident_status(incident_id: int, status_data: IncidentStatusUpdate):
    with getConnection() as con:
        with con.cursor() as cur:
            cur.execute(
                """
                UPDATE incidents
                SET status = %s
                WHERE id = %s
                RETURNING id, title, description, category, status;
                """,
                (status_data.status, incident_id)
            )

            row = cur.fetchone()

            if row is None:
                raise HTTPException(
                    status_code=404,
                    detail="Incident not found"
                )

            incident = {
                "id": row[0],
                "title": row[1],
                "description": row[2],
                "category": row[3],
                "status": row[4]
            }

    return incident