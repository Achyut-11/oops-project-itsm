from datetime import datetime, timedelta

sla_rules = {
    "P1": {
        "response": timedelta(minutes=15),
        "resolution": timedelta(hours=4)
    },
    "P2": {
        "response": timedelta(minutes=30),
        "resolution": timedelta(hours=8)
    },
    "P3": {
        "response": timedelta(hours=2),
        "resolution": timedelta(hours=24)
    },
    "P4": {
        "response": timedelta(hours=4),
        "resolution": timedelta(hours=48)
    }
}

def calc_sla(priority: str, craeted_at: datetime):
    rules = sla_rules[priority]
    response_deadline = craeted_at + rules["response"]
    resolution_deadline = craeted_at + rules["resolution"]

    return response_deadline, resolution_deadline
