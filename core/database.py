import yaml
import json
import sqlite3
from pathlib import Path
from sqlmodel import SQLModel, Session, create_engine, select
from core.models import Category, Task
from datetime import datetime

_cfg_path = Path(__file__).parent.parent / "config.yaml"
with open(_cfg_path, "r", encoding="utf-8") as f:
    _cfg = yaml.safe_load(f)

DB_PATH = Path(_cfg["database"]["path"])
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)


def _migrate_db():
    """
    Migration manuelle : ajoute les colonnes manquantes sur la DB existante.
    SQLite ne supporte pas ALTER TABLE ADD COLUMN si la colonne existe deja,
    donc on verifie d abord.
    """
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    # Recuperer les colonnes existantes de la table task
    cursor.execute("PRAGMA table_info(task)")
    existing_cols = {row[1] for row in cursor.fetchall()}

    migrations = [
        ("attachments", "TEXT"),
    ]

    for col_name, col_type in migrations:
        if col_name not in existing_cols:
            try:
                cursor.execute(f"ALTER TABLE task ADD COLUMN {col_name} {col_type}")
                print(f"[Migration] Colonne ajoutee : task.{col_name}")
            except Exception as e:
                print(f"[Migration] Erreur sur {col_name} : {e}")

    conn.commit()
    conn.close()


def init_db():
    """Cree les tables, migre la DB existante, injecte les categories par defaut."""
    SQLModel.metadata.create_all(engine)
    _migrate_db()  # migration des colonnes manquantes
    with Session(engine) as s:
        if not s.exec(select(Category)).first():
            defaults = [
                Category(name="Travail",  color="#1E90FF"),
                Category(name="Perso",    color="#32CD32"),
                Category(name="Projets",  color="#FF8C00"),
                Category(name="IA / Dev", color="#9370DB"),
            ]
            s.add_all(defaults)
            s.commit()


# ── CATEGORIES ────────────────────────────────────────────────────────────────
def get_categories() -> list[Category]:
    with Session(engine) as s:
        return s.exec(select(Category)).all()

def add_category(name: str, color: str = "#1E90FF") -> Category:
    with Session(engine) as s:
        cat = Category(name=name, color=color)
        s.add(cat)
        s.commit()
        s.refresh(cat)
        return cat

def delete_category(cat_id: int):
    with Session(engine) as s:
        cat = s.get(Category, cat_id)
        if cat:
            s.delete(cat)
            s.commit()


# ── TASKS ─────────────────────────────────────────────────────────────────────
def get_tasks(category_id: int | None = None,
              status: str | None = None) -> list[Task]:
    with Session(engine) as s:
        q = select(Task)
        if category_id is not None:
            q = q.where(Task.category_id == category_id)
        if status:
            q = q.where(Task.status == status)
        return s.exec(q.order_by(Task.created_at.desc())).all()

def add_task(title: str,
             description: str = "",
             category_id: int | None = None,
             priority: str = "normal",
             reminder_at: datetime | None = None,
             attachment_path: str | None = None) -> Task:
    with Session(engine) as s:
        t = Task(
            title=title,
            description=description,
            category_id=category_id,
            priority=priority,
            reminder_at=reminder_at,
            attachment_path=attachment_path,
        )
        s.add(t)
        s.commit()
        s.refresh(t)
        return t

def update_task(task_id: int, **kwargs) -> Task | None:
    with Session(engine) as s:
        t = s.get(Task, task_id)
        if not t:
            return None
        for k, v in kwargs.items():
            setattr(t, k, v)
        t.updated_at = datetime.now()
        s.add(t)
        s.commit()
        s.refresh(t)
        return t

def delete_task(task_id: int):
    with Session(engine) as s:
        t = s.get(Task, task_id)
        if t:
            s.delete(t)
            s.commit()

def get_pending_reminders() -> list[Task]:
    now = datetime.now()
    with Session(engine) as s:
        q = (select(Task)
             .where(Task.reminder_at <= now)
             .where(Task.reminder_fired == False)
             .where(Task.reminder_at != None))
        return s.exec(q).all()

def mark_reminder_fired(task_id: int):
    with Session(engine) as s:
        t = s.get(Task, task_id)
        if t:
            t.reminder_fired = True
            s.add(t)
            s.commit()


# ── HELPERS PIÈCES JOINTES MULTIPLES ─────────────────────────────────────────
def get_task_attachments(task: Task) -> list[str]:
    """
    Retourne la liste complete des fichiers joints a une tache.
    Combine attachment_path (legacy) et attachments (JSON).
    """
    paths = []
    if task.attachments:
        try:
            paths = json.loads(task.attachments)
        except Exception:
            paths = []
    # Compat legacy : attachment_path pas encore dans la liste JSON
    if task.attachment_path and task.attachment_path not in paths:
        paths.insert(0, task.attachment_path)
    return [p for p in paths if p]


def set_task_attachments(task_id: int, paths: list[str]):
    """
    Enregistre la liste complete des PJ.
    Met aussi a jour attachment_path (compat).
    """
    clean = [p for p in paths if p]
    with Session(engine) as s:
        t = s.get(Task, task_id)
        if t:
            t.attachments     = json.dumps(clean)
            t.attachment_path = clean[0] if clean else None
            t.updated_at      = datetime.now()
            s.add(t)
            s.commit()
