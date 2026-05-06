import yaml
import json
import sqlite3
from pathlib import Path
from sqlmodel import SQLModel, Session, create_engine, select
from core.models import Category, Task, SubTask
from datetime import datetime

_cfg_path = Path(__file__).parent.parent / "config.yaml"
with open(_cfg_path, "r", encoding="utf-8") as f:
    _cfg = yaml.safe_load(f)

DB_PATH = Path(_cfg["database"]["path"])
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
engine  = create_engine(f"sqlite:///{DB_PATH}", echo=False)


def _migrate_db():
    """Ajoute les colonnes et tables manquantes sans toucher aux donnees."""
    conn   = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    # Colonnes manquantes dans task
    cursor.execute("PRAGMA table_info(task)")
    existing_cols = {row[1] for row in cursor.fetchall()}
    for col, col_type in [("attachments", "TEXT")]:
        if col not in existing_cols:
            cursor.execute(f"ALTER TABLE task ADD COLUMN {col} {col_type}")
            print(f"[Migration] Colonne ajoutee : task.{col}")

    conn.commit()
    conn.close()


def init_db():
    SQLModel.metadata.create_all(engine)
    _migrate_db()
    with Session(engine) as s:
        if not s.exec(select(Category)).first():
            s.add_all([
                Category(name="Travail",  color="#1E90FF"),
                Category(name="Perso",    color="#32CD32"),
                Category(name="Projets",  color="#FF8C00"),
                Category(name="IA / Dev", color="#9370DB"),
            ])
            s.commit()


# ── CATEGORIES ────────────────────────────────────────────────────────────────
def get_categories() -> list[Category]:
    with Session(engine) as s:
        return s.exec(select(Category)).all()

def add_category(name: str, color: str = "#1E90FF") -> Category:
    with Session(engine) as s:
        cat = Category(name=name, color=color)
        s.add(cat); s.commit(); s.refresh(cat)
        return cat

def delete_category(cat_id: int):
    with Session(engine) as s:
        cat = s.get(Category, cat_id)
        if cat: s.delete(cat); s.commit()


# ── TASKS ─────────────────────────────────────────────────────────────────────
def get_tasks(category_id=None, status=None) -> list[Task]:
    with Session(engine) as s:
        q = select(Task)
        if category_id is not None: q = q.where(Task.category_id == category_id)
        if status:                  q = q.where(Task.status == status)
        return s.exec(q.order_by(Task.created_at.desc())).all()

def add_task(title, description="", category_id=None, priority="normal",
             reminder_at=None, attachment_path=None) -> Task:
    with Session(engine) as s:
        t = Task(title=title, description=description, category_id=category_id,
                 priority=priority, reminder_at=reminder_at,
                 attachment_path=attachment_path)
        s.add(t); s.commit(); s.refresh(t)
        return t

def update_task(task_id: int, **kwargs) -> Task | None:
    with Session(engine) as s:
        t = s.get(Task, task_id)
        if not t: return None
        for k, v in kwargs.items(): setattr(t, k, v)
        t.updated_at = datetime.now()
        s.add(t); s.commit(); s.refresh(t)
        return t

def delete_task(task_id: int):
    with Session(engine) as s:
        # Supprimer les sous-taches d abord
        subs = s.exec(select(SubTask).where(SubTask.task_id == task_id)).all()
        for sub in subs: s.delete(sub)
        t = s.get(Task, task_id)
        if t: s.delete(t)
        s.commit()

def get_pending_reminders() -> list[Task]:
    now = datetime.now()
    with Session(engine) as s:
        return s.exec(
            select(Task)
            .where(Task.reminder_at <= now)
            .where(Task.reminder_fired == False)
            .where(Task.reminder_at != None)
        ).all()

def mark_reminder_fired(task_id: int):
    with Session(engine) as s:
        t = s.get(Task, task_id)
        if t: t.reminder_fired = True; s.add(t); s.commit()


# ── SOUS-TACHES ───────────────────────────────────────────────────────────────
MAX_SUBTASKS = 10

def get_subtasks(task_id: int) -> list[SubTask]:
    with Session(engine) as s:
        return s.exec(
            select(SubTask)
            .where(SubTask.task_id == task_id)
            .order_by(SubTask.position)
        ).all()

def add_subtask(task_id: int, title: str) -> SubTask | None:
    """Ajoute une sous-tache. Retourne None si la limite est atteinte."""
    with Session(engine) as s:
        count = len(s.exec(
            select(SubTask).where(SubTask.task_id == task_id)
        ).all())
        if count >= MAX_SUBTASKS:
            return None
        sub = SubTask(task_id=task_id, title=title, position=count)
        s.add(sub); s.commit(); s.refresh(sub)
        return sub

def toggle_subtask(subtask_id: int) -> SubTask | None:
    """Bascule done/not done."""
    with Session(engine) as s:
        sub = s.get(SubTask, subtask_id)
        if not sub: return None
        sub.done = not sub.done
        s.add(sub); s.commit(); s.refresh(sub)
        return sub

def delete_subtask(subtask_id: int):
    with Session(engine) as s:
        sub = s.get(SubTask, subtask_id)
        if sub: s.delete(sub); s.commit()

def update_subtask_title(subtask_id: int, title: str) -> SubTask | None:
    with Session(engine) as s:
        sub = s.get(SubTask, subtask_id)
        if not sub: return None
        sub.title = title
        s.add(sub); s.commit(); s.refresh(sub)
        return sub

def get_subtask_progress(task_id: int) -> tuple[int, int]:
    """Retourne (done, total) pour la barre de progression."""
    subs  = get_subtasks(task_id)
    total = len(subs)
    done  = sum(1 for s in subs if s.done)
    return done, total

def check_auto_complete(task_id: int):
    """Si toutes les sous-taches sont done → passe la tache en done."""
    done, total = get_subtask_progress(task_id)
    if total > 0 and done == total:
        update_task(task_id, status="done")


# ── PIECES JOINTES MULTIPLES ──────────────────────────────────────────────────
def get_task_attachments(task: Task) -> list[str]:
    paths = []
    if task.attachments:
        try: paths = json.loads(task.attachments)
        except Exception: paths = []
    if task.attachment_path and task.attachment_path not in paths:
        paths.insert(0, task.attachment_path)
    return [p for p in paths if p]

def set_task_attachments(task_id: int, paths: list[str]):
    clean = [p for p in paths if p]
    with Session(engine) as s:
        t = s.get(Task, task_id)
        if t:
            t.attachments     = json.dumps(clean)
            t.attachment_path = clean[0] if clean else None
            t.updated_at      = datetime.now()
            s.add(t); s.commit()
