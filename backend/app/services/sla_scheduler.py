from apscheduler.schedulers.background import BackgroundScheduler
from app.services.sla_monitoring import check_sla_breaches

scheduler = BackgroundScheduler()

def start_scheduler():
    scheduler.add_job(
        check_sla_breaches,
        trigger="interval",
        seconds=60,
        id="sla_monitor",
        replace_existing=True
    )

    scheduler.start()


def stop_scheduler():
    scheduler.shutdown()