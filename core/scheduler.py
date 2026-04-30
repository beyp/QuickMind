import threading
import time
import schedule as sch
from plyer import notification
from core.database import get_pending_reminders, mark_reminder_fired


def _check_reminders():
    tasks = get_pending_reminders()
    for t in tasks:
        notification.notify(
            title=f"⏰ QuickMind — Rappel",
            message=t.title,
            app_name="QuickMind",
            timeout=8,
        )
        mark_reminder_fired(t.id)


def start_scheduler():
    """Lance le scheduler dans un thread daemon."""
    sch.every(30).seconds.do(_check_reminders)

    def _run():
        while True:
            sch.run_pending()
            time.sleep(1)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
