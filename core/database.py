import yaml, json, sqlite3
from pathlib import Path
from sqlmodel import SQLModel, Session, create_engine, select
from core.models import Category, Task, SubTask
from datetime import datetime, timedelta

_cfg_path = Path(__file__).parent.parent / "config.yaml"
with open(_cfg_path, "r", encoding="utf-8") as f:
    _cfg = yaml.safe_load(f)

DB_PATH = Path(_cfg["database"]["path"])
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
engine  = create_engine(f"sqlite:///{DB_PATH}", echo=False)


def _migrate_db():
    conn   = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(task)")
    existing_cols = {row[1] for row in cursor.fetchall()}
    for col, col_type in [
        ("attachments",     "TEXT"),
        ("recurrence",      "TEXT"),
        ("recurrence_days", "TEXT"),
        ("recurrence_end",  "DATETIME"),
    ]:
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


def get_categories():
    with Session(engine) as s:
        return s.exec(select(Category)).all()

def add_category(name, color="#1E90FF"):
    with Session(engine) as s:
        cat = Category(name=name, color=color)
        s.add(cat); s.commit(); s.refresh(cat)
        return cat

def delete_category(cat_id):
    with Session(engine) as s:
        cat = s.get(Category, cat_id)
        if cat: s.delete(cat); s.commit()


def get_tasks(category_id=None, status=None):
    with Session(engine) as s:
        q = select(Task)
        if category_id is not None: q = q.where(Task.category_id == category_id)
        if status:                  q = q.where(Task.status == status)
        return s.exec(q.order_by(Task.created_at.desc())).all()

def add_task(title, description="", category_id=None, priority="normal",
             reminder_at=None, attachment_path=None,
             recurrence=None, recurrence_days=None, recurrence_end=None):
    with Session(engine) as s:
        t = Task(title=title, description=description,
                 category_id=category_id, priority=priority,
                 reminder_at=reminder_at, attachment_path=attachment_path,
                 recurrence=recurrence, recurrence_days=recurrence_days,
                 recurrence_end=recurrence_end)
        s.add(t); s.commit(); s.refresh(t)
        return t

def update_task(task_id, **kwargs):
    with Session(engine) as s:
        t = s.get(Task, task_id)
        if not t: return None
        for k, v in kwargs.items(): setattr(t, k, v)
        t.updated_at = datetime.now()
        s.add(t); s.commit(); s.refresh(t)
        return t

def delete_task(task_id):
    with Session(engine) as s:
        subs = s.exec(select(SubTask).where(SubTask.task_id == task_id)).all()
        for sub in subs: s.delete(sub)
        t = s.get(Task, task_id)
        if t: s.delete(t)
        s.commit()

def get_pending_reminders():
    now = datetime.now()
    with Session(engine) as s:
        return s.exec(select(Task)
            .where(Task.reminder_at <= now)
            .where(Task.reminder_fired == False)
            .where(Task.reminder_at != None)).all()

def mark_reminder_fired(task_id):
    with Session(engine) as s:
        t = s.get(Task, task_id)
        if t: t.reminder_fired = True; s.add(t); s.commit()


DAYS_MAP = {"mon":0,"tue":1,"wed":2,"thu":3,"fri":4,"sat":5,"sun":6}

def _next_recurrence_date(task):
    if not task.recurrence or task.recurrence == "none":
        return None
    base = task.reminder_at or datetime.now()
    now  = datetime.now()

    if task.recurrence == "daily":
        next_dt = base + timedelta(days=1)
        while next_dt <= now: next_dt += timedelta(days=1)

    elif task.recurrence == "weekly":
        next_dt = base + timedelta(weeks=1)
        while next_dt <= now: next_dt += timedelta(weeks=1)

    elif task.recurrence == "monthly":
        import calendar
        next_dt = base
        for _ in range(24):
            m = next_dt.month + 1
            y = next_dt.year + (1 if m > 12 else 0)
            m = 1 if m > 12 else m
            last = calendar.monthrange(y, m)[1]
            next_dt = next_dt.replace(year=y, month=m,
                                      day=min(base.day, last))
            if next_dt > now: break

    elif task.recurrence == "yearly":
        next_dt = base
        for _ in range(10):
            try: next_dt = next_dt.replace(year=next_dt.year + 1)
            except ValueError: next_dt = next_dt.replace(year=next_dt.year+1, day=28)
            if next_dt > now: break

    elif task.recurrence == "custom" and task.recurrence_days:
        try:
            days     = json.loads(task.recurrence_days)
            day_nums = sorted([DAYS_MAP[d] for d in days if d in DAYS_MAP])
        except Exception:
            return None
        if not day_nums: return None
        next_dt = base + timedelta(days=1)
        for _ in range(365):
            if next_dt > now and next_dt.weekday() in day_nums: break
            next_dt += timedelta(days=1)
    else:
        return None

    if task.recurrence_end and next_dt > task.recurrence_end:
        return None
    return next_dt


def create_next_recurrence(task_id):
    with Session(engine) as s:
        task = s.get(Task, task_id)
        if not task or not task.recurrence or task.recurrence == "none":
            return None
    next_dt = _next_recurrence_date(task)
    if not next_dt: return None
    new_task = add_task(
        title=task.title, description=task.description,
        category_id=task.category_id, priority=task.priority,
        reminder_at=next_dt, recurrence=task.recurrence,
        recurrence_days=task.recurrence_days, recurrence_end=task.recurrence_end)
    print(f"[Recurrence] #{new_task.id} cree pour {next_dt.strftime('%d/%m/%Y')}")
    return new_task


MAX_SUBTASKS = 10

def get_subtasks(task_id):
    with Session(engine) as s:
        return s.exec(select(SubTask).where(SubTask.task_id == task_id)
                      .order_by(SubTask.position)).all()

def add_subtask(task_id, title):
    with Session(engine) as s:
        count = len(s.exec(select(SubTask).where(SubTask.task_id == task_id)).all())
        if count >= MAX_SUBTASKS: return None
        sub = SubTask(task_id=task_id, title=title, position=count)
        s.add(sub); s.commit(); s.refresh(sub)
        return sub

def toggle_subtask(subtask_id):
    with Session(engine) as s:
        sub = s.get(SubTask, subtask_id)
        if not sub: return None
        sub.done = not sub.done
        s.add(sub); s.commit(); s.refresh(sub)
        return sub

def delete_subtask(subtask_id):
    with Session(engine) as s:
        sub = s.get(SubTask, subtask_id)
        if sub: s.delete(sub); s.commit()

def get_subtask_progress(task_id):
    subs  = get_subtasks(task_id)
    total = len(subs)
    done  = sum(1 for s in subs if s.done)
    return done, total

def check_auto_complete(task_id):
    done, total = get_subtask_progress(task_id)
    if total > 0 and done == total:
        update_task(task_id, status="done")
        create_next_recurrence(task_id)

def get_task_attachments(task):
    paths = []
    if task.attachments:
        try: paths = json.loads(task.attachments)
        except Exception: paths = []
    if task.attachment_path and task.attachment_path not in paths:
        paths.insert(0, task.attachment_path)
    return [p for p in paths if p]

def set_task_attachments(task_id, paths):
    clean = [p for p in paths if p]
    with Session(engine) as s:
        t = s.get(Task, task_id)
        if t:
            t.attachments     = json.dumps(clean)
            t.attachment_path = clean[0] if clean else None
            t.updated_at      = datetime.now()
            s.add(t); s.commit()
