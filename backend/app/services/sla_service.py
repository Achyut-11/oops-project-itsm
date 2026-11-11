from app.repositories.sla_repo import SLARepository
from datetime import timedelta

def calc_sla(cur, priority: str, created_at):
    repo = SLARepository(cur)
    policy = repo.get_by_priority(priority)

    if policy is None:
        raise ValueError(f"No SLA policy configured for {priority}")

    response_minutes = policy[1]
    resolution_minutes = policy[2]

    response_deadline = created_at + timedelta(minutes=response_minutes)
    resolution_deadline = created_at + timedelta(minutes=resolution_minutes)

    return response_deadline, resolution_deadline