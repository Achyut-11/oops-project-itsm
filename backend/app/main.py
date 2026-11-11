from fastapi import FastAPI, HTTPException, Query, Depends
from contextlib import asynccontextmanager
from pydantic import BaseModel, Field, model_validator
from app.config import getConnection
from typing import Literal, Annotated
from datetime import datetime, timezone
from app.services.priority_calc import priority_calc
from app.services.load_based_assignment import load_based_assignment
from app.services.int_tech_assignment import int_tech_assignment
from app.services.audit_service import log_audit, getlogs, getlogsnonincident
from app.services.sla_service import calc_sla
from app.services.sla_scheduler import stop_scheduler, start_scheduler
from app.services.notification_service import create_notification
from datetime import date, timedelta
from app.auth.security import hash_password, verify_password, create_access_token
from app.auth.dependencies import get_current_user, require_employee, require_technician, require_admin
from fastapi.responses import JSONResponse
from app.repositories.incident_repo import IncidentRepository
from app.repositories.user_repo import UserRepository
from app.repositories.sla_repo import SLARepository
from app.exceptions import (
    ITSMError, Conflict, ValidationError, NoTechnicianAvailable,
    Forbidden, Unauthorized
)
from app.repositories.notification_repo import NotificationRepository
from app.repositories.report_repo import ReportRepository

@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(lifespan=lifespan)

@app.exception_handler(ITSMError)
async def itsm_error_handler(request, exc: ITSMError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})

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
         "ASSIGNED",
         "IN_PROGRESS",
         "RESOLVED",
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
    status : Literal["NEW", "ASSIGNED","IN_PROGRESS", "RESOLVED", "CLOSED"]|None =None
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

class SLAPolicyUpdate(BaseModel):
    response_minutes: int = Field(gt=0)
    resolution_minutes: int = Field(gt=0)

@app.get("/")
def home():
     return{"message" : "backen is running"}


@app.get("/incidents")
def get_incidents(incident_query:Annotated[IncidentQuery, Query()],  current_user: dict = Depends(get_current_user)):
    with getConnection() as con:
        with con.cursor() as cur:
            incidents = IncidentRepository(cur).search(current_user, incident_query)
    return {"incidents": [i.to_dict() for i in incidents]}


@app.get("/incidents/{incident_id}")
def get_incident_byid(incident_id: int, current_user: dict = Depends(get_current_user)):
    with getConnection() as con:
        with con.cursor() as cur:
            incident = IncidentRepository(cur).get_visible_to(incident_id, current_user)
    return incident.to_dict()

@app.post("/incidents")
def create_incident(incident_data: IncidentCreate,
                    current_user: dict = Depends(require_employee)):
    priority = priority_calc(
        incident_data.affected_percentage,
        incident_data.business_criticality,
        incident_data.estimated_complexity,
    )
    

    with getConnection() as con:
        with con.cursor() as cur:
            created_at = datetime.now(timezone.utc)
            response_deadline, resolution_deadline = calc_sla(cur, priority, created_at)
            repo = IncidentRepository(cur)

            incident = repo.create(incident_data, current_user["id"], priority,
                                   response_deadline, resolution_deadline)
            log_audit(cur, incident.id, current_user["id"],
                      "INCIDENT_CREATED", None, "NEW")

            technician_id = int_tech_assignment(cur, incident.id)
            if technician_id is None:
                raise NoTechnicianAvailable()

            assigned = repo.assign_new(incident.id, technician_id)

            log_audit(cur, incident.id, None, "TECHNICIAN_ASSIGNED",
                      None, str(technician_id))
            create_notification(cur, technician_id, incident.id, "INCIDENT_ASSIGNED",
                                f"You have been assigned incident #{incident.id}: {assigned.title}")

            return assigned.to_dict()

@app.patch("/incidents/{incident_id}/acknowledge")
def acknowledge(incident_id: int, current_user: dict = Depends(require_technician)):
    with getConnection() as con:
        with con.cursor() as cur:
            repo = IncidentRepository(cur)

            incident = repo.get_by_id(incident_id)
            incident.ensure_can_be_acknowledged_by(current_user)

            updated = repo.mark_acknowledged(incident_id)
            if updated is None:
                raise Conflict(
                    "Incident was reassigned or already acknowledged. Please refresh and try again."
                )

            log_audit(cur, incident_id, current_user["id"],
                      "INCIDENT_ACKNOWLEDGED", "ASSIGNED", "ACKNOWLEDGED")
            create_notification(cur, updated.reported_by_user_id, incident_id,
                                "INCIDENT_ACKNOWLEDGED",
                                f"Your incident #{incident_id} has been acknowledged")

            return {
                "id": updated.id,
                "status": updated.status,
                "acknowledged_at": updated.acknowledged_at,
            }

@app.patch("/incidents/{incident_id}/close")
def close(incident_id: int, current_user: dict = Depends(require_admin)):
    with getConnection() as con:
        with con.cursor() as cur:
            repo = IncidentRepository(cur)

            incident = repo.get_by_id(incident_id)
            incident.ensure_can_be_closed_by(current_user)

            updated = repo.mark_closed(incident_id)
            if updated is None:
                raise Conflict(
                    "Incident was already closed"
                )

            log_audit(cur, incident_id, current_user["id"],
                      "INCIDENT_CLOSED", "RESOLVED", "CLOSED")
            create_notification(cur, updated.reported_by_user_id, incident_id,
                                "INCIDENT_CLOSED",
                                f"Your incident #{incident_id} has been closed")

            create_notification(cur, updated.assigned_technician_id, incident_id,
                                "INCIDENT_CLOSED",
                                f"Your incident #{incident_id} has been closed")

            return {
                "id": updated.id,
                "status": updated.status,
                "closed_at": updated.closed_at,
            }

@app.patch("/incidents/{incident_id}/resolve")
def resolve(incident_id: int, current_user: dict = Depends(require_technician)):
    with getConnection() as con:
        with con.cursor() as cur:
            repo = IncidentRepository(cur)

            incident = repo.get_by_id(incident_id)
            incident.ensure_can_be_resolved_by(current_user)

            updated = repo.mark_resolved(incident_id)
            if updated is None:
                raise Conflict(
                    "Incident was already resolved"
                )

            log_audit(cur, incident_id, current_user["id"],
                      "INCIDENT_RESOLVED", "IN_PROGRESS", "RESOLVED")
            create_notification(cur, updated.reported_by_user_id, incident_id,
                                "INCIDENT_RESOLVED",
                                f"Your incident #{incident_id} has been resolved")

            return {
                "id": updated.id,
                "status": updated.status,
                "resolved_at": updated.resolved_at,
            }


@app.post("/users")
def adduser(userinfo: UserCreate, current_user: dict = Depends(require_admin)):
    with getConnection() as con:
        with con.cursor() as cur:
            users = UserRepository(cur)
            if users.email_exists(userinfo.email):
                raise Conflict("Email already registered")
            user = users.create(
                userinfo.name, userinfo.email, userinfo.role,
                userinfo.years_of_experience, hash_password(userinfo.password),
                skills=userinfo.skills if userinfo.role == "TECHNICIAN" else [],
            )
    return user.to_dict()


@app.post("/auth/setup_admin")
def setup_admin(admin_data: AdminSetup):
    with getConnection() as con:
        with con.cursor() as cur:
            users = UserRepository(cur)
            if users.admin_exists_locked():
                raise Forbidden("Admin setup has already been completed")
            admin = users.create_admin(
                admin_data.name, admin_data.email, hash_password(admin_data.password)
            )
    return {
        "message": "Initial admin created successfully",
        "user": {"id": admin.id, "name": admin.name,
                 "email": admin.email, "role": admin.role},
    }


@app.get("/users")
def getallusers(current_user: dict = Depends(require_admin)):
    with getConnection() as con:
        with con.cursor() as cur:
            users = UserRepository(cur).list_all()
    return [u.to_dict() for u in users]


@app.get("/users/{user_id}")
def getoneuser(user_id: int, current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "ADMIN" and current_user["id"] != user_id:
        raise Forbidden("User information can only be viewed by admins and the user themselves")
    with getConnection() as con:
        with con.cursor() as cur:
            user = UserRepository(cur).get_by_id(user_id)
    return user.to_dict()
@app.get("/incidents/{incident_id}/audit")

def gelog(incident_id : int, current_user : dict = Depends(require_admin)):
    with getConnection() as con:
        with con.cursor() as cur:
            return getlogs(cur, incident_id)

@app.get("/incidents/audit/non_incident")
def gelognonincident(current_user : dict = Depends(require_admin)):
    with getConnection() as con:
        with con.cursor() as cur:
            return getlogsnonincident(cur)

        
        
@app.patch("/incidents/{incident_id}/assign")
def admin_assign(incident_id: int, assignment_data: IncidentAssignmentUpdate,
                 current_user: dict = Depends(require_admin)):
    with getConnection() as con:
        with con.cursor() as cur:
            repo = IncidentRepository(cur)
            users = UserRepository(cur)

            incident = repo.get_by_id(incident_id)
            incident.ensure_can_be_reassigned_to(assignment_data.technician_id)

            if not users.is_active_technician_with_skill(
                assignment_data.technician_id, incident.category
            ):
                raise ValidationError(
                    "Invalid technician: must be active and have the skill matching the incident category"
                )

            old_tech_id = incident.assigned_technician_id
            old_status = incident.status

            updated = repo.reassign(incident_id, assignment_data.technician_id)
            if updated is None:
                raise Conflict("Incident status changed while reassigning. Please refresh and try again.")

            if old_status == "ACKNOWLEDGED":
                log_audit(cur, incident_id, current_user["id"],
                          "STATUS_CHANGED", "ACKNOWLEDGED", "ASSIGNED")

            log_audit(cur, incident_id, current_user["id"], "TECHNICIAN_REASSIGNED",
                      str(old_tech_id) if old_tech_id is not None else None,
                      str(assignment_data.technician_id))

            create_notification(cur, assignment_data.technician_id, incident_id,
                                "INCIDENT_REASSIGNED_BY_ADMIN",
                                f"You have been assigned incident #{incident_id}: {updated.title}")
            create_notification(cur, updated.reported_by_user_id, incident_id,
                                "INCIDENT_TECHNICIAN_CHANGED",
                                f"The technician handling your incident #{incident_id} has changed.")
            if old_tech_id is not None:
                create_notification(cur, old_tech_id, incident_id,
                                    "INCIDENT_REASSIGNED_BY_ADMIN",
                                    f"Incident #{incident_id}: {updated.title} has been reassigned to another technician.")

            return {"message": "Technician reassigned successfully",
                    "incident": updated.to_dict()}
@app.get("/notifications")
def getallnotifications(current_user: dict = Depends(require_admin)):
    with getConnection() as con:
        with con.cursor() as cur:
            items = NotificationRepository(cur).list_all()
    return [n.to_dict() for n in items]


@app.get("/notifications/me")
def getusernotifications(unread: bool = False,
                         current_user: dict = Depends(get_current_user)):
    with getConnection() as con:
        with con.cursor() as cur:
            items = NotificationRepository(cur).list_for_user(current_user["id"], unread)
    return [n.to_dict() for n in items]


@app.patch("/notifications/{notification_id}/read")
def readnotification(notification_id: int,
                     current_user: dict = Depends(get_current_user)):
    with getConnection() as con:
        with con.cursor() as cur:
            n = NotificationRepository(cur).mark_read(notification_id, current_user)
    return {"message": "Notification marked as read", "id": n.id, "is_read": n.is_read}

@app.get("/reports/overview")
def report_overview(current_user: dict = Depends(require_admin)):
    with getConnection() as con:
        with con.cursor() as cur:
            return ReportRepository(cur).overview()


@app.get("/reports/technician-workload")
def report_technician_workload(current_user: dict = Depends(require_admin)):
    with getConnection() as con:
        with con.cursor() as cur:
            return ReportRepository(cur).technician_workload()


@app.get("/reports/service-analysis")
def report_service_analysis(current_user: dict = Depends(require_admin)):
    with getConnection() as con:
        with con.cursor() as cur:
            return ReportRepository(cur).service_analysis()

@app.post("/auth/register")
def register_user(user: UserRegister):
    with getConnection() as con:
        with con.cursor() as cur:
            users = UserRepository(cur)
            if users.email_exists(user.email):
                raise Conflict("Email already registered")
            created = users.create(
                user.name, user.email, "EMPLOYEE", 0,
                hash_password(user.password),
            )
    return {"id": created.id, "name": created.name, "email": created.email,
            "role": created.role, "message": "Registration successful"}


@app.post("/auth/login")
def login(user: UserLogin):
    with getConnection() as con:
        with con.cursor() as cur:
            auth = UserRepository(cur).get_auth_by_email(user.email)

    if (auth is None or auth["password_hash"] is None
            or not verify_password(user.password, auth["password_hash"])):
        raise Unauthorized("Invalid email or password")

    if not auth["is_active"]:
        raise Forbidden("Account is deactivated")

    access_token = create_access_token({
        "token_version": auth["token_version"],
        "user_id": auth["id"],
        "role": auth["role"],
    })
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {"id": auth["id"], "name": auth["name"],
                 "email": auth["email"], "role": auth["role"]},
    }


@app.patch("/auth/change-password")
def change_password(password_data: PasswordChange,
                    current_user: dict = Depends(get_current_user)):
    with getConnection() as con:
        with con.cursor() as cur:
            users = UserRepository(cur)
            current_hash = users.get_password_hash(current_user["id"])
            if current_hash is None or not verify_password(
                password_data.current_password, current_hash
            ):
                raise ValidationError("Current password is incorrect")
            users.change_password(
                current_user["id"], hash_password(password_data.new_password)
            )
    return {"message": "Password changed successfully"}

@app.get("/admin/sla-policies")
def get_sla_policies(
    current_user: dict = Depends(require_admin)
):
    with getConnection() as conn:
        with conn.cursor() as cur:
            repo = SLARepository(cur)
            policies = repo.get_all()

            return [
                {
                    "priority": row[0],
                    "response_minutes": row[1],
                    "resolution_minutes": row[2],
                    "updated_at": row[3],
                    "updated_by": row[4]
                }
                for row in policies
            ]


@app.put("/admin/sla-policies/{priority}")
def update_sla_policy(
    priority: Literal["P1", "P2", "P3", "P4"],
    data: SLAPolicyUpdate,
    current_user: dict = Depends(require_admin)
):
    with getConnection() as conn:
        with conn.cursor() as cur:
            repo = SLARepository(cur)

            old_policy, new_policy = repo.update(
                priority,
                data.response_minutes,
                data.resolution_minutes,
                current_user["id"]
            )

            if new_policy is None:
                raise HTTPException(
                    status_code=404,
                    detail="SLA policy not found"
                )

            log_audit(cur, None, current_user["id"],
                "SLA_POLICY_CHANGED",
                (f"{old_policy[0]}: response={old_policy[1]} min, resolution={old_policy[2]} min"),
                (f"{new_policy[0]}: response={new_policy[1]} min, resolution={new_policy[2]} min"))

            return {
                "message": f"{priority} SLA policy updated",
                "priority":  new_policy[0],
                "response_minutes":  new_policy[1],
                "resolution_minutes":  new_policy[2],
                "updated_at": new_policy[3],
                "updated_by": new_policy[4]
            }

            

