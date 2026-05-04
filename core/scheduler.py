"""
Scheduler de rappels QuickMind.
Utilise ctypes pour les notifications Windows (pas de conflit GIL).
"""
import threading
import time
import schedule as sch


def _notify_windows(title: str, message: str):
    """Notification Windows native via ctypes — aucun conflit GIL."""
    try:
        from win10toast import ToastNotifier
        ToastNotifier().show_toast(title, message, duration=6, threaded=True)
    except Exception:
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0, message, f"QuickMind — {title}", 0x00000040)
        except Exception:
            print(f"[Rappel] {title} : {message}")


def _check_reminders():
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
        print(f"[Scheduler] Erreur : {e}")


def start_scheduler():
    sch.every(30).seconds.do(_check_reminders)

    def _run():
        while True:
            try:
                sch.run_pending()
            except Exception as e:
                print(f"[Scheduler] Erreur run : {e}")
            time.sleep(1)

    threading.Thread(target=_run, daemon=True, name="QM-Scheduler").start()
    print("[Scheduler] Demarre.")
