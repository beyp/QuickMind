"""
Agent Outlook via COM (win32com).
Aucune config Azure requise.
"""
import win32com.client
import os
import re
import yaml
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

_cfg_path = Path(__file__).parent.parent / "config.yaml"
with open(_cfg_path, "r", encoding="utf-8") as f:
    _cfg = yaml.safe_load(f)
ATT_DIR = Path(_cfg["attachments"]["path"])
ATT_DIR.mkdir(parents=True, exist_ok=True)


def _get_outlook():
    try:
        return win32com.client.Dispatch("Outlook.Application")
    except Exception as e:
        raise RuntimeError("Impossible de se connecter a Outlook.\n" + str(e))


def _get_namespace():
    ol = _get_outlook()
    ns = ol.GetNamespace("MAPI")
    ns.Logon()
    return ns


def _safe_filename(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "_", name)


# MAILS

def get_unread_mails(max_count: int = 10) -> list[dict]:
    ns = _get_namespace()
    inbox = ns.GetDefaultFolder(6)
    messages = inbox.Items
    messages.Sort("[ReceivedTime]", True)
    results = []
    count = 0
    for msg in messages:
        if count >= max_count:
            break
        try:
            if msg.UnRead:
                results.append({
                    "id":           msg.EntryID,
                    "entry_id":     msg.EntryID,
                    "subject":      msg.Subject or "(sans objet)",
                    "sender":       msg.SenderName or "?",
                    "sender_email": msg.SenderEmailAddress or "",
                    "received":     msg.ReceivedTime.strftime("%d/%m/%Y %H:%M"),
                    "body_preview": (msg.Body or "")[:200].replace("\n", " "),
                    "body_full":    msg.Body or "",
                    "unread":       True,
                    "att_count":    msg.Attachments.Count,
                })
                count += 1
        except Exception:
            continue
    return results


def get_recent_mails(max_count: int = 10) -> list[dict]:
    ns = _get_namespace()
    inbox = ns.GetDefaultFolder(6)
    messages = inbox.Items
    messages.Sort("[ReceivedTime]", True)
    results = []
    count = 0
    for msg in messages:
        if count >= max_count:
            break
        try:
            results.append({
                "id":           msg.EntryID,
                "entry_id":     msg.EntryID,
                "subject":      msg.Subject or "(sans objet)",
                "sender":       msg.SenderName or "?",
                "sender_email": msg.SenderEmailAddress or "",
                "received":     msg.ReceivedTime.strftime("%d/%m/%Y %H:%M"),
                "body_preview": (msg.Body or "")[:200].replace("\n", " "),
                "body_full":    msg.Body or "",
                "unread":       msg.UnRead,
                "att_count":    msg.Attachments.Count,
            })
            count += 1
        except Exception:
            continue
    return results


def get_mail_info(entry_id: str) -> dict:
    """Retourne les infos completes d un mail (avec liste des noms de PJ)."""
    ns = _get_namespace()
    msg = ns.GetItemFromID(entry_id)
    att_names = []
    for i in range(1, msg.Attachments.Count + 1):
        try:
            att_names.append(msg.Attachments.Item(i).FileName)
        except Exception:
            continue
    return {
        "entry_id":     entry_id,
        "subject":      msg.Subject or "(sans objet)",
        "sender":       msg.SenderName or "?",
        "sender_email": msg.SenderEmailAddress or "",
        "received":     msg.ReceivedTime.strftime("%d/%m/%Y %H:%M"),
        "body_full":    msg.Body or "",
        "att_names":    att_names,
        "att_count":    msg.Attachments.Count,
    }


def save_mail_attachments(entry_id: str, task_id: int) -> list[str]:
    """Sauvegarde les PJ d un mail dans data/attachments/task_<id>/."""
    ns = _get_namespace()
    msg = ns.GetItemFromID(entry_id)
    task_att_dir = ATT_DIR / f"task_{task_id}"
    task_att_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    for i in range(1, msg.Attachments.Count + 1):
        att = msg.Attachments.Item(i)
        filename = _safe_filename(att.FileName)
        dest = task_att_dir / filename
        try:
            att.SaveAsFile(str(dest))
            saved.append(str(dest))
        except Exception:
            continue
    return saved


def save_mail_body_as_file(entry_id: str, task_id: int, subject: str) -> str:
    """Sauvegarde le corps du mail en .txt dans data/attachments/task_<id>/."""
    ns = _get_namespace()
    msg = ns.GetItemFromID(entry_id)
    task_att_dir = ATT_DIR / f"task_{task_id}"
    task_att_dir.mkdir(parents=True, exist_ok=True)
    safe_subject = _safe_filename(subject)[:60]
    dest = task_att_dir / f"mail_{safe_subject}.txt"
    sep = "-" * 60
    content = (
        f"De      : {msg.SenderName or '?'} <{msg.SenderEmailAddress or ''}>\n"
        f"Objet   : {subject}\n"
        f"Recu le : {msg.ReceivedTime.strftime('%d/%m/%Y %H:%M')}\n"
        f"{sep}\n\n"
        f"{msg.Body or ''}"
    )
    with open(dest, "w", encoding="utf-8") as f:
        f.write(content)
    return str(dest)


def send_mail(to: str, subject: str, body: str) -> bool:
    ol = _get_outlook()
    mail = ol.CreateItem(0)
    mail.To = to
    mail.Subject = subject
    mail.Body = body
    mail.Send()
    return True


def reply_to_mail(entry_id: str, body: str) -> bool:
    ns = _get_namespace()
    mail = ns.GetItemFromID(entry_id)
    reply = mail.Reply()
    reply.Body = body + "\n\n" + reply.Body
    reply.Send()
    return True


# CALENDRIER

def get_upcoming_events(days: int = 7) -> list[dict]:
    ns = _get_namespace()
    calendar = ns.GetDefaultFolder(9)
    items = calendar.Items
    items.IncludeRecurrences = True
    items.Sort("[Start]")
    now = datetime.now()
    end = now + timedelta(days=days)
    items = items.Restrict(
        f"[Start] >= '{now.strftime('%d/%m/%Y %H:%M')}' AND "
        f"[Start] <= '{end.strftime('%d/%m/%Y %H:%M')}'"
    )
    results = []
    for item in items:
        try:
            results.append({
                "subject":   item.Subject or "(sans titre)",
                "start":     item.Start.strftime("%d/%m/%Y %H:%M"),
                "end":       item.End.strftime("%d/%m/%Y %H:%M"),
                "location":  item.Location or "",
                "organizer": item.Organizer or "",
            })
        except Exception:
            continue
    return results


def create_calendar_event(
    subject: str,
    start: datetime,
    end: Optional[datetime] = None,
    body: str = "",
    location: str = "",
    reminder_minutes: int = 15,
) -> bool:
    if end is None:
        end = start + timedelta(hours=1)
    ol = _get_outlook()
    appt = ol.CreateItem(1)
    appt.Subject  = subject
    appt.Body     = body
    appt.Location = location
    appt.Start    = start.strftime("%Y-%m-%d %H:%M")
    appt.End      = end.strftime("%Y-%m-%d %H:%M")
    appt.ReminderSet = True
    appt.ReminderMinutesBeforeStart = reminder_minutes
    appt.Save()
    return True


# TACHES OUTLOOK

def get_outlook_tasks() -> list[dict]:
    ns = _get_namespace()
    tasks_folder = ns.GetDefaultFolder(13)
    results = []
    for item in tasks_folder.Items:
        try:
            if item.Complete:
                continue
            results.append({
                "subject":  item.Subject or "(sans titre)",
                "due":      item.DueDate.strftime("%d/%m/%Y") if item.DueDate.year < 4500 else "-",
                "priority": item.Importance,
                "status":   item.Status,
            })
        except Exception:
            continue
    return results


def create_outlook_task(
    subject: str,
    due: Optional[datetime] = None,
    body: str = "",
    importance: int = 1,
) -> bool:
    ol = _get_outlook()
    task = ol.CreateItem(3)
    task.Subject    = subject
    task.Body       = body
    task.Importance = importance
    if due:
        task.DueDate = due.strftime("%Y-%m-%d")
    task.Save()
    return True
