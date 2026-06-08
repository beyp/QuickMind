"""
Scheduler de rappels QuickMind.
+ Auto-archive des taches terminees apres N jours.
"""
import threading
import time
import ctypes
import schedule as sch
import yaml
from pathlib import Path


_cfg_path = Path(__file__).parent.parent / "config.yaml"
with open(_cfg_path, "r", encoding="utf-8") as f:
    _cfg = yaml.safe_load(f)

AUTO_ARCHIVE_DAYS = _cfg.get("scheduler", {}).get("auto_archive_done_days", 7)


def _notify_windows(title: str, message: str):
    """Notification Windows native via ctypes."""
    try:
        from win10toast import ToastNotifier
        ToastNotifier().show_toast(title, message, duration=6, threaded=True)
    except Exception:
        try:
            ctypes.windll.user32.MessageBoxW(
                0, message, f"QuickMind — {title}", 0x00000040)
        except Exception:
            print(f"[Rappel] {title} : {message}")


def _check_reminders():
    """Verifie les rappels et envoie les notifications."""
    try:
        from core.database import get_pending_reminders, mark_reminder_fired
        for t in get_pending_reminders():
            try:
                _notify_windows("Rappel", t.title)
            except Exception as e:
                print(f"[Scheduler] Notif erreur : {e}")
            finally:
                try:
                    mark_reminder_fired(t.id)
                except Exception:
                    pass
    except Exception as e:
        print(f"[Scheduler] Erreur check rappels : {e}")


def _auto_archive_done():
    """Archive automatiquement les taches terminees apres N jours."""
    if AUTO_ARCHIVE_DAYS <= 0:
        return
    try:
        from datetime import datetime, timedelta
        from core.database import get_tasks, archive_task
        from sqlmodel import Session, select
        from core.database import engine
        from core.models import Task

        cutoff = datetime.now() - timedelta(days=AUTO_ARCHIVE_DAYS)
        with Session(engine) as s:
            tasks = s.exec(
                select(Task)
                .where(Task.status == "done")
                .where(Task.archived == False)
                .where(Task.updated_at <= cutoff)
            ).all()
            count = 0
            for t in tasks:
                t.archived   = True
                t.updated_at = datetime.now()
                s.add(t)
                count += 1
            if count:
                s.commit()
                print(f"[Scheduler] Auto-archive : {count} tache(s) terminees archivees")
    except Exception as e:
        print(f"[Scheduler] Erreur auto-archive : {e}")


def start_scheduler():
    """Lance le scheduler dans un thread daemon."""
    sch.every(30).seconds.do(_check_reminders)
    # Auto-archive une fois par heure
    if AUTO_ARCHIVE_DAYS > 0:
        sch.every(1).hours.do(_auto_archive_done)
        print(f"[Scheduler] Auto-archive active : {AUTO_ARCHIVE_DAYS} jours")

    def _run():
        while True:
            try:
                sch.run_pending()
            except Exception as e:
                print(f"[Scheduler] Erreur run : {e}")
            time.sleep(1)

    threading.Thread(target=_run, daemon=True, name="QM-Scheduler").start()
    print("[Scheduler] Demarre.")
