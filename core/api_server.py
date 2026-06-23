"""
QuickMind API Server — FastAPI sur localhost:8765
"""
import threading
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
# ✅ Imports globaux — disponibles partout
from core.database import (
    init_db, get_tasks, get_categories, add_task,
    update_task as db_update_task, delete_task,
    get_subtasks, add_subtask, toggle_subtask,
    delete_subtask, get_subtask_progress,
    check_auto_complete, create_next_recurrence,
    get_task_attachments,
)


class TaskCreate(BaseModel):
    title:       str
    description: Optional[str] = ""
    category:    Optional[str] = None
    priority:    Optional[str] = "normal"
    reminder:    Optional[str] = None

class TaskAI(BaseModel):
    text: str


app = FastAPI(
    title="QuickMind API",
    description="API locale QuickMind",
    version="1.0.0",
    docs_url="/docs",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Reference vers l app Tkinter (pour scheduler le refresh dans le bon thread)
_tk_app = None
_ui_refresh_callback = None


def set_tk_app(tk_app):
    """Stocke la reference vers l app Tkinter principale."""
    global _tk_app
    _tk_app = tk_app


def set_ui_callback(fn):
    global _ui_refresh_callback
    _ui_refresh_callback = fn


def _refresh_ui():
    """
    Rafraichit l UI de facon thread-safe.
    Utilise app.after(0, ...) pour executer dans le thread Tkinter.
    """
    if _tk_app and _ui_refresh_callback:
        try:
            # after(0) = executer dans le thread principal Tkinter
            _tk_app.after(0, _ui_refresh_callback)
        except Exception as e:
            print(f"[API] Erreur refresh UI : {e}")


@app.get("/health")
def health():
    from core.database import get_tasks
    tasks = get_tasks()
    return {
        "status": "ok",
        "app":    "QuickMind",
        "tasks":  len(tasks),
        "time":   datetime.now().isoformat(),
    }


@app.get("/tasks")
def list_tasks(
    category:         Optional[str]  = None,
    status:           Optional[str]  = None,
    priority:         Optional[str]  = None,
    category_id:      Optional[int]  = None,
    include_archived: Optional[bool] = False,
):
    """Liste les taches avec filtres. Supporte category_id et include_archived."""
    init_db()
    cats_by_id = {c.id: c.name for c in get_categories()}
    cat_id = category_id
    if category and not cat_id:
        cats_low = {c.name.lower(): c.id for c in get_categories()}
        cat_id   = cats_low.get(category.lower())
    tasks = get_tasks(category_id=cat_id, status=status,
                      include_archived=include_archived)
    if priority:
        tasks = [t for t in tasks if t.priority == priority]
    result_list = []
    for t in tasks:
        done_c, total_c = get_subtask_progress(t.id)
        result_list.append({
            "id":              t.id,
            "title":           t.title,
            "description":     t.description,
            "category":        cats_by_id.get(t.category_id, ""),
            "category_id":     t.category_id,
            "priority":        t.priority,
            "status":          t.status,
            "reminder":        t.reminder_at.isoformat() if t.reminder_at else None,
            "created_at":      t.created_at.isoformat(),
            "recurrence":      t.recurrence or "",
            "recurrence_days": t.recurrence_days,
            "archived":        bool(t.archived) if hasattr(t,'archived') else False,
            "subtask_done":    done_c,
            "subtask_count":   total_c,
        })
    return result_list


@app.post("/task", status_code=201)
def create_task(data: TaskCreate):
    from core.database import add_task, get_categories, init_db
    init_db()
    cats   = {c.name.lower(): c.id for c in get_categories()}
    cat_id = cats.get((data.category or "").lower())
    remind_dt = None
    if data.reminder:
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M",
                    "%d/%m/%Y %H:%M", "%d/%m/%Y"):
            try:
                remind_dt = datetime.strptime(data.reminder, fmt)
                break
            except ValueError:
                continue
    task = add_task(
        title=data.title,
        description=data.description or "",
        category_id=cat_id,
        priority=data.priority or "normal",
        reminder_at=remind_dt,
    )
    _refresh_ui()
    return {"id": task.id, "title": task.title,
            "priority": task.priority, "status": "created"}


@app.post("/task/ai", status_code=201)
def create_task_ai(data: TaskAI):
    try:
        from agents.local_ai import ask_ai
        result = ask_ai(data.text)
        _refresh_ui()
        return {"result": result, "status": "created"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/task/{task_id}/done")
def mark_done(task_id: int):
    from core.database import update_task, create_next_recurrence, init_db
    init_db()
    t = update_task(task_id, status="done")
    if not t:
        raise HTTPException(status_code=404, detail="Tache introuvable")
    create_next_recurrence(task_id)
    _refresh_ui()
    return {"id": task_id, "status": "done"}


@app.delete("/task/{task_id}")
def delete_task_endpoint(task_id: int):
    from core.database import delete_task, init_db
    init_db()
    delete_task(task_id)
    _refresh_ui()
    return {"id": task_id, "status": "deleted"}



# ── Endpoints sous-taches ────────────────────────────────────────────────────

class SubTaskCreate(BaseModel):
    title: str

class TaskUpdate(BaseModel):
    title:       Optional[str] = None
    description: Optional[str] = None
    category:    Optional[str] = None
    priority:    Optional[str] = None
    status:      Optional[str] = None


@app.get("/task/{task_id}")
def get_task(task_id: int):
    """Retourne une tache avec ses sous-taches."""
    from core.database import get_tasks, get_subtasks, get_task_attachments
    from core.database import get_categories
    init_db()
    cats = {c.id: c.name for c in get_categories()}
    tasks = get_tasks()
    task  = next((t for t in tasks if t.id == task_id), None)
    if not task:
        raise HTTPException(status_code=404, detail="Tache introuvable")
    subs = get_subtasks(task_id)
    return {
        "id":          task.id,
        "title":       task.title,
        "description": task.description or "",
        "category":    cats.get(task.category_id, ""),
        "priority":    task.priority,
        "status":      task.status,
        "reminder":    task.reminder_at.isoformat() if task.reminder_at else None,
        "recurrence":  task.recurrence,
        "subtasks": [
            {"id": s.id, "title": s.title, "done": s.done, "position": s.position}
            for s in subs
        ],
    }


@app.put("/task/{task_id}", status_code=200)
def update_task_endpoint(task_id: int, data: TaskUpdate):
    """Met a jour une tache."""
    from core.database import update_task, get_categories, init_db
    init_db()
    kwargs = {}
    if data.title       is not None: kwargs["title"]       = data.title
    if data.description is not None: kwargs["description"] = data.description
    if data.priority    is not None: kwargs["priority"]    = data.priority
    if data.status      is not None: kwargs["status"]      = data.status
    if data.category    is not None:
        cats = {c.name.lower(): c.id for c in get_categories()}
        cat_id = cats.get(data.category.lower())
        if cat_id: kwargs["category_id"] = cat_id
    t = update_task(task_id, **kwargs)
    if not t:
        raise HTTPException(status_code=404, detail="Tache introuvable")
    _refresh_ui()
    return {"id": task_id, "status": "updated"}


@app.get("/task/{task_id}/subtasks")
def get_task_subtasks(task_id: int):
    """Retourne les sous-taches d une tache."""
    from core.database import get_subtasks, init_db
    init_db()
    subs = get_subtasks(task_id)
    return [{"id": s.id, "title": s.title, "done": s.done} for s in subs]


@app.post("/task/{task_id}/subtask", status_code=201)
def add_subtask_endpoint(task_id: int, data: SubTaskCreate):
    """Ajoute une sous-tache."""
    from core.database import add_subtask, init_db
    init_db()
    sub = add_subtask(task_id, data.title)
    if not sub:
        raise HTTPException(status_code=400,
            detail="Limite de sous-taches atteinte (max 10)")
    _refresh_ui()
    return {"id": sub.id, "title": sub.title, "done": sub.done}


@app.post("/task/{task_id}/subtask/{subtask_id}/toggle")
def toggle_subtask_endpoint(task_id: int, subtask_id: int):
    """Coche/decoche une sous-tache."""
    from core.database import toggle_subtask, check_auto_complete, init_db
    init_db()
    sub = toggle_subtask(subtask_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Sous-tache introuvable")
    check_auto_complete(task_id)
    _refresh_ui()
    return {"id": sub.id, "done": sub.done}


@app.delete("/task/{task_id}/subtask/{subtask_id}")
def delete_subtask_endpoint(task_id: int, subtask_id: int):
    """Supprime une sous-tache."""
    from core.database import delete_subtask, init_db
    init_db()
    delete_subtask(subtask_id)
    _refresh_ui()
    return {"status": "deleted"}


@app.get("/categories")
def get_categories_endpoint():
    """Retourne la liste des categories."""
    from core.database import get_categories, init_db
    init_db()
    return [{"id": c.id, "name": c.name, "color": c.color}
            for c in get_categories()]




# ── Endpoints manquants ───────────────────────────────────────────────────────

class ReminderUpdate(BaseModel):
    reminder: Optional[str] = None  # ISO8601 ou null pour supprimer

class RecurrenceUpdate(BaseModel):
    recurrence:      Optional[str] = None
    recurrence_days: Optional[str] = None

class SubtaskAIRequest(BaseModel):
    task_title: str
    task_desc:  Optional[str] = ""


@app.post("/task/{task_id}/archive")
def archive_task_endpoint(task_id: int):
    """Archive une tache."""
    from core.database import archive_task
    init_db()
    archive_task(task_id)
    _refresh_ui()
    return {"id": task_id, "status": "archived"}


@app.post("/task/{task_id}/unarchive")
def unarchive_task_endpoint(task_id: int):
    """Desarchive une tache."""
    from core.database import unarchive_task
    init_db()
    unarchive_task(task_id)
    _refresh_ui()
    return {"id": task_id, "status": "unarchived"}


@app.post("/tasks/archive-done")
def archive_all_done_endpoint():
    """Archive toutes les taches terminees."""
    from core.database import archive_all_done
    init_db()
    count = archive_all_done()
    _refresh_ui()
    return {"archived": count}


@app.delete("/tasks/delete-done")
def delete_all_done_endpoint():
    """Supprime toutes les taches terminees."""
    from core.database import delete_all_done
    init_db()
    count = delete_all_done()
    _refresh_ui()
    return {"deleted": count}


@app.get("/tasks/archived")
def get_archived_tasks_endpoint():
    """Retourne les taches archivees."""
    from core.database import get_archived_tasks, get_categories
    init_db()
    cats  = {c.id: c.name for c in get_categories()}
    tasks = get_archived_tasks()
    return [
        {
            "id":       t.id,
            "title":    t.title,
            "category": cats.get(t.category_id, ""),
            "priority": t.priority,
            "status":   t.status,
            "updated":  t.updated_at.isoformat() if t.updated_at else None,
        }
        for t in tasks
    ]


@app.put("/task/{task_id}/reminder")
def update_reminder(task_id: int, data: ReminderUpdate):
    """Met a jour le rappel d une tache."""
    init_db()
    remind_dt = None
    if data.reminder:
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M",
                    "%d/%m/%Y %H:%M", "%d/%m/%Y"):
            try:
                remind_dt = datetime.strptime(data.reminder, fmt)
                break
            except ValueError:
                continue
    t = db_update_task(task_id, reminder_at=remind_dt,
                       reminder_fired=False if remind_dt else True)
    if not t:
        raise HTTPException(status_code=404, detail="Tache introuvable")
    _refresh_ui()
    return {"id": task_id,
            "reminder": remind_dt.isoformat() if remind_dt else None}


@app.put("/task/{task_id}/recurrence")
def update_recurrence(task_id: int, data: RecurrenceUpdate):
    """Met a jour la recurrence d une tache."""
    init_db()
    kwargs = {}
    if data.recurrence      is not None: kwargs["recurrence"]      = data.recurrence
    if data.recurrence_days is not None: kwargs["recurrence_days"] = data.recurrence_days
    t = db_update_task(task_id, **kwargs)
    if not t:
        raise HTTPException(status_code=404, detail="Tache introuvable")
    _refresh_ui()
    return {"id": task_id, "recurrence": data.recurrence}


@app.post("/task/{task_id}/subtasks/ai")
def generate_subtasks_ai(task_id: int, data: SubtaskAIRequest):
    """Genere des sous-taches via Mistral."""
    try:
        from agents.subtask_ai import generate_subtasks
        from core.database import get_subtask_progress
        _, current = get_subtask_progress(task_id)
        remaining  = 10 - current
        if remaining <= 0:
            raise HTTPException(status_code=400,
                detail="Limite de 10 sous-taches atteinte")
        suggestions = generate_subtasks(
            data.task_title, data.task_desc or "", max_subtasks=remaining)
        return {"suggestions": suggestions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


WEB_UI = """
<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
<title>QuickMind</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#1a1a2e;color:#e0e0e0;min-height:100vh}
.app{display:flex;height:100vh;overflow:hidden}
/* Sidebar */
.sidebar{width:200px;background:#16213e;border-right:1px solid #0f3460;display:flex;flex-direction:column;flex-shrink:0}
.sidebar-header{padding:14px 12px 8px;border-bottom:1px solid #0f3460}
.sidebar-title{color:#1E90FF;font-size:1.1em;font-weight:bold}
.sidebar-sub{color:#555;font-size:0.75em;margin-top:2px}
.sidebar-nav{flex:1;overflow-y:auto;padding:8px 0}
.nav-item{padding:8px 12px;cursor:pointer;font-size:0.88em;display:flex;align-items:center;gap:8px;border-radius:0;transition:background 0.1s;color:#aaa}
.nav-item:hover{background:#0f3460;color:#e0e0e0}
.nav-item.active{background:#1E90FF22;color:#1E90FF;font-weight:bold;border-left:3px solid #1E90FF}
.nav-dot{width:10px;height:10px;border-radius:50%;flex-shrink:0}
.nav-count{margin-left:auto;font-size:0.75em;background:#0f3460;padding:1px 6px;border-radius:10px}
/* Main */
.main{flex:1;display:flex;flex-direction:column;overflow:hidden}
.topbar{padding:10px 14px;background:#16213e;border-bottom:1px solid #0f3460;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.topbar-title{color:#1E90FF;font-weight:bold;font-size:1em;margin-right:4px}
.health-dot{width:8px;height:8px;border-radius:50%;background:#555;flex-shrink:0}
.health-dot.online{background:#32CD32}
/* Tabs */
.tabs{display:flex;gap:0;border-bottom:1px solid #0f3460;background:#16213e;flex-shrink:0}
.tab{padding:8px 14px;cursor:pointer;font-size:0.85em;color:#888;border-bottom:2px solid transparent;transition:all 0.1s;white-space:nowrap}
.tab:hover{color:#e0e0e0}
.tab.active{color:#1E90FF;border-bottom-color:#1E90FF}
/* Content */
.content{flex:1;overflow-y:auto;padding:12px}
/* Filters */
.filters{display:flex;gap:6px;margin-bottom:10px;flex-wrap:wrap;align-items:center}
.filter-btn{padding:4px 10px;border-radius:20px;border:1px solid #0f3460;cursor:pointer;font-size:0.8em;background:#0f3460;color:#888;white-space:nowrap;transition:all 0.1s}
.filter-btn.active{background:#1E90FF;color:white;border-color:#1E90FF}
.filter-btn:hover{border-color:#1E90FF;color:#1E90FF}
.search-row{display:flex;gap:6px;margin-bottom:10px}
.search-row input{flex:1;padding:6px 10px;border-radius:6px;border:1px solid #0f3460;background:#0f3460;color:#e0e0e0;font-size:0.85em}
/* Actions bar */
.actions-bar{display:flex;gap:6px;margin-bottom:10px;flex-wrap:wrap}
/* Task groups */
.group-header{display:flex;align-items:center;gap:8px;margin:12px 0 6px;font-size:0.8em;font-weight:bold}
.group-line{flex:1;height:1px}
/* Task cards */
.task-card{background:#16213e;border-radius:8px;padding:10px 12px;margin-bottom:8px;border-left:3px solid #0f3460;cursor:pointer;transition:border-color 0.1s,background 0.1s}
.task-card:hover{background:#1a2a4a;border-left-color:#1E90FF}
.task-card.prio-urgent{border-left-color:#FF4444}
.task-card.prio-high{border-left-color:#FF8C00}
.task-card.prio-normal{border-left-color:#1E90FF}
.task-card.prio-low{border-left-color:#555}
.task-header{display:flex;justify-content:space-between;align-items:flex-start;gap:8px}
.task-title{font-weight:bold;font-size:0.92em;flex:1}
.task-badges{display:flex;gap:4px;flex-wrap:wrap;align-items:center}
.badge{padding:2px 7px;border-radius:12px;font-size:0.7em;font-weight:bold;white-space:nowrap}
.badge-todo{background:#333;color:#aaa}
.badge-wip{background:#3a2a00;color:#FF8C00}
.badge-done{background:#1a3a1a;color:#32CD32}
.badge-overdue{background:#3a0000;color:#FF4444}
.badge-today{background:#3a2000;color:#FF8C00}
.badge-tomorrow{background:#3a3a00;color:#FFD700}
.badge-soon{background:#1a2a1a;color:#32CD32}
.badge-recur{background:#2a1a3a;color:#9370DB}
.task-meta{font-size:0.75em;color:#666;margin-top:4px;display:flex;gap:8px;flex-wrap:wrap}
.task-desc{font-size:0.8em;color:#777;margin-top:4px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
/* Progress */
.progress-bar{height:4px;background:#0f3460;border-radius:2px;margin-top:5px;overflow:hidden}
.progress-fill{height:100%;border-radius:2px;transition:width 0.3s}
/* Kanban */
.kanban{display:flex;gap:12px;height:100%;overflow-x:auto}
.kanban-col{min-width:280px;flex:1;background:#16213e;border-radius:8px;display:flex;flex-direction:column;max-height:100%}
.kanban-col-header{padding:10px 12px;font-weight:bold;font-size:0.9em;border-bottom:1px solid #0f3460;display:flex;justify-content:space-between}
.kanban-col-body{flex:1;overflow-y:auto;padding:8px}
/* Buttons */
.btn{padding:7px 14px;border-radius:6px;border:none;cursor:pointer;font-size:0.85em;font-weight:bold;transition:opacity 0.1s;white-space:nowrap}
.btn:hover{opacity:0.85}
.btn:active{opacity:0.7}
.btn-primary{background:#1E90FF;color:white}
.btn-success{background:#2a5a2a;color:#32CD32}
.btn-danger{background:#5a1a1a;color:#FF4444}
.btn-orange{background:#3a2a00;color:#FF8C00}
.btn-purple{background:#2a1a3a;color:#9370DB}
.btn-gray{background:#333;color:#aaa}
.btn-sm{padding:4px 8px;font-size:0.78em;border-radius:4px}
/* Modal */
.overlay{position:fixed;inset:0;background:rgba(0,0,0,0.75);z-index:200;display:none;overflow-y:auto}
.overlay.open{display:block}
.modal{background:#16213e;border-radius:12px;margin:20px auto;max-width:620px;border:1px solid #1E90FF;overflow:hidden}
.modal-header{padding:14px 18px;background:#1a2a4a;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #0f3460}
.modal-title{color:#1E90FF;font-weight:bold;font-size:1em}
.modal-close{background:none;border:none;color:#888;font-size:1.3em;cursor:pointer;padding:0 4px;line-height:1}
.modal-body{padding:16px 18px;max-height:65vh;overflow-y:auto}
.modal-footer{padding:12px 18px;background:#1a2a4a;border-top:1px solid #0f3460;display:flex;gap:8px;justify-content:flex-end}
/* Accordion */
.accordion{border:1px solid #0f3460;border-radius:6px;margin-bottom:8px;overflow:hidden}
.accordion-header{padding:8px 12px;background:#0f3460;cursor:pointer;display:flex;align-items:center;gap:8px;font-size:0.88em;font-weight:bold;user-select:none}
.accordion-header:hover{background:#1a3460}
.accordion-arrow{transition:transform 0.2s;font-size:0.8em}
.accordion-body{padding:12px;display:none}
.accordion-body.open{display:block}
/* Form */
.form-group{margin-bottom:10px}
.form-label{display:block;font-size:0.82em;color:#aaa;margin-bottom:4px}
.form-row{display:flex;gap:10px}
.form-row .form-group{flex:1}
input[type=text],input[type=datetime-local],textarea,select{width:100%;padding:8px 10px;border-radius:6px;border:1px solid #0f3460;background:#0f3460;color:#e0e0e0;font-size:0.9em;outline:none;-webkit-appearance:none}
input:focus,textarea:focus,select:focus{border-color:#1E90FF}
textarea{resize:vertical;min-height:60px}
/* Segment buttons */
.seg-btns{display:flex;gap:0;border-radius:6px;overflow:hidden;border:1px solid #0f3460}
.seg-btn{flex:1;padding:7px 4px;border:none;background:#0f3460;color:#888;cursor:pointer;font-size:0.8em;font-weight:bold;transition:all 0.1s;text-align:center}
.seg-btn.active{background:#1E90FF;color:white}
/* Subtasks */
.subtask-item{display:flex;align-items:center;gap:8px;padding:5px 0;border-bottom:1px solid #0f3460}
.subtask-item:last-child{border-bottom:none}
.sub-check{width:16px;height:16px;cursor:pointer;accent-color:#1E90FF;flex-shrink:0}
.sub-title{flex:1;font-size:0.88em}
.sub-title.done{text-decoration:line-through;color:#666}
.sub-del{background:none;border:none;color:#555;cursor:pointer;font-size:0.9em;padding:0 2px}
.sub-del:hover{color:#FF4444}
.add-sub-row{display:flex;gap:6px;margin-top:8px}
.add-sub-row input{flex:1;margin-bottom:0}
/* Attachments */
.att-item{display:flex;align-items:center;gap:8px;padding:4px 0;font-size:0.85em;color:#88BBFF}
.att-item a{color:#88BBFF;text-decoration:none}
.att-item a:hover{text-decoration:underline}
/* Recurrence */
.recur-select{margin-bottom:8px}
.recur-days{display:flex;gap:4px;flex-wrap:wrap}
.day-btn{padding:4px 8px;border-radius:4px;border:1px solid #0f3460;background:#0f3460;color:#888;cursor:pointer;font-size:0.78em}
.day-btn.active{background:#1E90FF;color:white;border-color:#1E90FF}
/* Status/toast */
.toast{position:fixed;bottom:20px;right:20px;padding:10px 16px;border-radius:8px;font-size:0.88em;z-index:999;opacity:0;transition:opacity 0.3s;pointer-events:none}
.toast.show{opacity:1}
.toast.ok{background:#1a3a1a;color:#32CD32;border:1px solid #32CD32}
.toast.err{background:#3a1a1a;color:#FF4444;border:1px solid #FF4444}
/* Mobile */
@media(max-width:640px){
  .sidebar{width:100%;height:auto;border-right:none;border-bottom:1px solid #0f3460}
  .app{flex-direction:column}
  .sidebar-nav{display:flex;flex-direction:row;overflow-x:auto;padding:4px 0}
  .nav-item{flex-shrink:0;padding:6px 10px;white-space:nowrap}
  .kanban{flex-direction:column}
  .kanban-col{min-width:auto}
}
</style>
</head>
<body>
<div class="app">
<!-- Sidebar -->
<div class="sidebar">
  <div class="sidebar-header">
    <div class="sidebar-title">⚡ QuickMind</div>
    <div class="sidebar-sub" id="health-sub">Connexion...</div>
  </div>
  <div class="sidebar-nav" id="sidebar-nav">
    <div class="nav-item active" onclick="selectCategory(null,this)">
      <span>🗂</span><span>Toutes</span>
      <span class="nav-count" id="count-all">0</span>
    </div>
  </div>
</div>

<!-- Main -->
<div class="main">
  <!-- Topbar -->
  <div class="topbar">
    <span class="health-dot" id="health-dot"></span>
    <span class="topbar-title" id="view-title">Toutes les tâches</span>
    <button class="btn btn-primary btn-sm" onclick="openNewTask()">+ Nouvelle</button>
    <button class="btn btn-purple btn-sm" onclick="openAI()">🤖 IA</button>
    <button class="btn btn-orange btn-sm" onclick="archiveDone()">📦 Archiver ✅</button>
    <button class="btn btn-danger btn-sm" onclick="deleteDone()">🗑 Suppr ✅</button>
    <button class="btn btn-gray btn-sm" onclick="openArchives()">🗂 Archives</button>
  </div>

  <!-- Tabs -->
  <div class="tabs">
    <div class="tab active" onclick="switchView('list',this)">📋 Liste</div>
    <div class="tab" onclick="switchView('kanban',this)">📊 Kanban</div>
    <div class="tab" onclick="switchView('add',this)">➕ Ajouter</div>
  </div>

  <!-- Content -->
  <div class="content" id="content">
    <!-- Vue liste -->
    <div id="view-list">
      <div class="filters" id="filters">
        <button class="filter-btn active" onclick="setStatus('',this)">Toutes</button>
        <button class="filter-btn" onclick="setStatus('todo',this)">📋 À faire</button>
        <button class="filter-btn" onclick="setStatus('in_progress',this)">⚙️ En cours</button>
        <button class="filter-btn" onclick="setStatus('done',this)">✅ Terminées</button>
      </div>
      <div class="search-row">
        <input id="search-input" placeholder="Rechercher..." oninput="debounceSearch()">
      </div>
      <div id="tasks-container">Chargement...</div>
    </div>

    <!-- Vue Kanban -->
    <div id="view-kanban" style="display:none;height:calc(100vh - 140px)">
      <div class="kanban" id="kanban-board"></div>
    </div>

    <!-- Vue Ajouter -->
    <div id="view-add" style="display:none">
      <div style="max-width:520px">
        <div class="form-group">
          <label class="form-label">Titre *</label>
          <input id="add-title" placeholder="Titre de la tâche...">
        </div>
        <div class="form-row">
          <div class="form-group">
            <label class="form-label">Catégorie</label>
            <select id="add-cat"></select>
          </div>
          <div class="form-group">
            <label class="form-label">Priorité</label>
            <div class="seg-btns" id="add-prio-btns">
              <button class="seg-btn" onclick="setPrio('add','low',this)">Basse</button>
              <button class="seg-btn active" onclick="setPrio('add','normal',this)">Normal</button>
              <button class="seg-btn" onclick="setPrio('add','high',this)">Haute</button>
              <button class="seg-btn" onclick="setPrio('add','urgent',this)">Urgent</button>
            </div>
          </div>
        </div>
        <div class="form-group">
          <label class="form-label">Description</label>
          <textarea id="add-desc" placeholder="Description (optionnel)..." rows="3"></textarea>
        </div>
        <div class="form-row">
          <div class="form-group">
            <label class="form-label">Rappel</label>
            <input type="datetime-local" id="add-reminder">
          </div>
          <div class="form-group">
            <label class="form-label">Récurrence</label>
            <select id="add-recur">
              <option value="">Aucune</option>
              <option value="daily">Quotidienne</option>
              <option value="weekly">Hebdomadaire</option>
              <option value="monthly">Mensuelle</option>
              <option value="yearly">Annuelle</option>
              <option value="custom">Jours spécifiques</option>
            </select>
          </div>
        </div>
        <div id="add-days-row" style="display:none;margin-bottom:10px">
          <label class="form-label">Jours</label>
          <div class="recur-days" id="add-days"></div>
        </div>
        <div style="display:flex;gap:8px;margin-top:12px">
          <button class="btn btn-primary" onclick="createTask()">✅ Créer</button>
          <button class="btn btn-gray" onclick="switchView('list')">Annuler</button>
        </div>
        <div id="add-status" style="margin-top:8px;font-size:0.85em"></div>
      </div>
    </div>
  </div>
</div>
</div>

<!-- Modal Edition -->
<div class="overlay" id="edit-overlay" onclick="maybeCloseEdit(event)">
<div class="modal" onclick="event.stopPropagation()">
  <div class="modal-header">
    <span class="modal-title" id="edit-modal-title">✏️ Éditer la tâche</span>
    <button class="modal-close" onclick="closeEdit()">✕</button>
  </div>
  <div class="modal-body">
    <!-- Section Titre & Description -->
    <div class="accordion" id="acc-main">
      <div class="accordion-header" onclick="toggleAcc('acc-main')">
        <span class="accordion-arrow">▼</span>
        <span style="color:#1E90FF">📝 Titre & Description</span>
      </div>
      <div class="accordion-body open">
        <div class="form-group">
          <label class="form-label">Titre *</label>
          <input id="edit-title" placeholder="Titre...">
        </div>
        <div class="form-group">
          <label class="form-label">Description</label>
          <textarea id="edit-desc" rows="3"></textarea>
        </div>
      </div>
    </div>

    <!-- Section Classification -->
    <div class="accordion" id="acc-class">
      <div class="accordion-header" onclick="toggleAcc('acc-class')">
        <span class="accordion-arrow">▼</span>
        <span style="color:#FF8C00">🏷️ Classification</span>
      </div>
      <div class="accordion-body open">
        <div class="form-row">
          <div class="form-group">
            <label class="form-label">Catégorie</label>
            <select id="edit-cat"></select>
          </div>
          <div class="form-group">
            <label class="form-label">Priorité</label>
            <div class="seg-btns" id="edit-prio-btns">
              <button class="seg-btn" onclick="setPrio('edit','low',this)">Basse</button>
              <button class="seg-btn" onclick="setPrio('edit','normal',this)">Normal</button>
              <button class="seg-btn" onclick="setPrio('edit','high',this)">Haute</button>
              <button class="seg-btn" onclick="setPrio('edit','urgent',this)">Urgent</button>
            </div>
          </div>
        </div>
        <div class="form-group">
          <label class="form-label">Statut</label>
          <div class="seg-btns" id="edit-status-btns">
            <button class="seg-btn" onclick="setStatus2('todo',this)">📋 À faire</button>
            <button class="seg-btn" onclick="setStatus2('in_progress',this)">⚙️ En cours</button>
            <button class="seg-btn" onclick="setStatus2('done',this)">✅ Terminé</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Section Rappel & Récurrence -->
    <div class="accordion" id="acc-remind">
      <div class="accordion-header" onclick="toggleAcc('acc-remind')">
        <span class="accordion-arrow">▶</span>
        <span style="color:#FFD700">⏰ Rappel & Récurrence</span>
      </div>
      <div class="accordion-body">
        <div class="form-row">
          <div class="form-group">
            <label class="form-label">Rappel</label>
            <input type="datetime-local" id="edit-reminder">
          </div>
          <div class="form-group">
            <label class="form-label">Récurrence</label>
            <select id="edit-recur" onchange="toggleRecurDays('edit')">
              <option value="">Aucune</option>
              <option value="daily">Quotidienne</option>
              <option value="weekly">Hebdomadaire</option>
              <option value="monthly">Mensuelle</option>
              <option value="yearly">Annuelle</option>
              <option value="custom">Jours spécifiques</option>
            </select>
          </div>
        </div>
        <div id="edit-days-row" style="display:none">
          <label class="form-label">Jours</label>
          <div class="recur-days" id="edit-days"></div>
        </div>
      </div>
    </div>

    <!-- Section Sous-tâches -->
    <div class="accordion" id="acc-sub">
      <div class="accordion-header" onclick="toggleAcc('acc-sub')">
        <span class="accordion-arrow">▶</span>
        <span style="color:#32CD32">✅ Sous-tâches</span>
        <span id="sub-progress-badge" style="margin-left:auto;font-size:0.78em;color:#888"></span>
      </div>
      <div class="accordion-body">
        <div id="sub-progress-bar" style="display:none;margin-bottom:8px">
          <div class="progress-bar"><div class="progress-fill" id="sub-fill"></div></div>
        </div>
        <div id="subtasks-list"></div>
        <div class="add-sub-row">
          <input id="new-sub" placeholder="Nouvelle sous-tâche..." onkeydown="if(event.key==='Enter')addSub()">
          <button class="btn btn-success btn-sm" onclick="addSub()">＋</button>
          <button class="btn btn-purple btn-sm" onclick="genSubsAI()">🤖 IA</button>
        </div>
        <div id="sub-ai-status" style="font-size:0.8em;color:#9370DB;margin-top:4px"></div>
        <!-- Dialog suggestions IA -->
        <div id="ai-suggestions" style="display:none;margin-top:8px;border:1px solid #9370DB;border-radius:6px;padding:10px">
          <div style="font-size:0.85em;color:#9370DB;margin-bottom:6px;font-weight:bold">🤖 Suggestions Mistral :</div>
          <div id="ai-sug-list"></div>
          <div style="display:flex;gap:6px;margin-top:8px">
            <button class="btn btn-success btn-sm" onclick="addSelectedSubs()">✅ Ajouter sélection</button>
            <button class="btn btn-gray btn-sm" onclick="document.getElementById('ai-suggestions').style.display='none'">Annuler</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Section PJ -->
    <div class="accordion" id="acc-pj">
      <div class="accordion-header" onclick="toggleAcc('acc-pj')">
        <span class="accordion-arrow">▶</span>
        <span style="color:#9370DB">📎 Pièces jointes</span>
      </div>
      <div class="accordion-body">
        <div id="att-list"></div>
        <div style="margin-top:6px;font-size:0.8em;color:#555">
          Les pièces jointes sont gérées depuis l'application de bureau.
        </div>
      </div>
    </div>
  </div>
  <div class="modal-footer">
    <button class="btn btn-danger btn-sm" onclick="deleteCurrentTask()">🗑 Supprimer</button>
    <button class="btn btn-orange btn-sm" onclick="archiveCurrentTask()">📦 Archiver</button>
    <button class="btn btn-gray" onclick="closeEdit()">Annuler</button>
    <button class="btn btn-primary" onclick="saveEdit()">💾 Enregistrer</button>
  </div>
</div>
</div>

<!-- Modal Archives -->
<div class="overlay" id="arch-overlay" onclick="if(event.target===this)closeArchives()">
<div class="modal" onclick="event.stopPropagation()">
  <div class="modal-header">
    <span class="modal-title">🗂 Archives</span>
    <button class="modal-close" onclick="closeArchives()">✕</button>
  </div>
  <div class="modal-body" id="arch-body">Chargement...</div>
  <div class="modal-footer">
    <button class="btn btn-gray" onclick="closeArchives()">Fermer</button>
  </div>
</div>
</div>

<!-- Modal IA -->
<div class="overlay" id="ai-overlay" onclick="if(event.target===this)closeAI()">
<div class="modal" onclick="event.stopPropagation()">
  <div class="modal-header">
    <span class="modal-title">🤖 Assistant IA — Mistral</span>
    <button class="modal-close" onclick="closeAI()">✕</button>
  </div>
  <div class="modal-body">
    <div class="form-group">
      <label class="form-label">Commande en langage naturel</label>
      <textarea id="ai-prompt" rows="3" placeholder="Ex: Crée une tâche urgente pour préparer la démo client vendredi 14h..."></textarea>
    </div>
    <div id="ai-result" style="font-size:0.85em;color:#9370DB;min-height:40px;padding:8px;background:#0f3460;border-radius:6px;display:none"></div>
  </div>
  <div class="modal-footer">
    <button class="btn btn-gray" onclick="closeAI()">Fermer</button>
    <button class="btn btn-purple" onclick="sendAI()">🤖 Envoyer à Mistral</button>
  </div>
</div>
</div>

<div class="toast" id="toast"></div>

<script>
const API = window.location.origin;
let currentCatId   = null;
let currentStatus  = '';
let currentSearch  = '';
let currentView    = 'list';
let currentTaskId  = null;
let editPrio       = 'normal';
let editStatus     = 'todo';
let addPrio        = 'normal';
let addRecurDays   = [];
let editRecurDays  = [];
let categories     = [];
let searchTimer    = null;
let aiSuggestions  = [];

const DAYS_FR = ['Lun','Mar','Mer','Jeu','Ven','Sam','Dim'];
const DAYS_EN = ['mon','tue','wed','thu','fri','sat','sun'];
const RECUR_FR = {'':'Aucune','daily':'Quotidienne','weekly':'Hebdo','monthly':'Mensuelle','yearly':'Annuelle','custom':'Perso'};

// ── Init ─────────────────────────────────────────────────────────────────────
async function init() {
  await Promise.all([checkHealth(), loadCategories()]);
  buildDayButtons('add');
  buildDayButtons('edit');
  document.getElementById('add-recur').onchange = () => toggleRecurDays('add');
  loadTasks();
  setInterval(checkHealth, 30000);
}

async function checkHealth() {
  try {
    const d = await apiFetch('/health');
    document.getElementById('health-dot').classList.add('online');
    document.getElementById('health-sub').textContent = d.tasks + ' tâche(s)';
  } catch(e) {
    document.getElementById('health-dot').classList.remove('online');
    document.getElementById('health-sub').textContent = 'Hors ligne';
  }
}

async function loadCategories() {
  try {
    categories = await apiFetch('/categories');
    buildSidebar();
    buildCatSelects();
  } catch(e) {}
}

function buildSidebar() {
  const nav = document.getElementById('sidebar-nav');
  const existing = nav.querySelector('.nav-item.active');
  nav.innerHTML = '';
  const all = document.createElement('div');
  all.className = 'nav-item' + (currentCatId === null ? ' active' : '');
  all.innerHTML = '<span>🗂</span><span>Toutes</span><span class="nav-count" id="count-all">?</span>';
  all.onclick = () => selectCategory(null, all);
  nav.appendChild(all);
  categories.forEach(c => {
    const item = document.createElement('div');
    item.className = 'nav-item' + (currentCatId === c.id ? ' active' : '');
    item.innerHTML = `<span class="nav-dot" style="background:${c.color}"></span><span>${c.name}</span>`;
    item.onclick = () => selectCategory(c.id, item);
    nav.appendChild(item);
  });
}

function buildCatSelects() {
  const opts = '<option value="">Aucune</option>' +
    categories.map(c => `<option value="${c.name}">${c.name}</option>`).join('');
  document.getElementById('add-cat').innerHTML = opts;
  document.getElementById('edit-cat').innerHTML = opts;
}

function buildDayButtons(prefix) {
  const container = document.getElementById(prefix+'-days');
  container.innerHTML = '';
  DAYS_FR.forEach((label, i) => {
    const btn = document.createElement('button');
    btn.className = 'day-btn';
    btn.textContent = label;
    btn.dataset.day = DAYS_EN[i];
    btn.onclick = () => {
      btn.classList.toggle('active');
      const days = prefix==='add' ? addRecurDays : editRecurDays;
      const day  = DAYS_EN[i];
      const idx  = days.indexOf(day);
      if (idx >= 0) days.splice(idx,1); else days.push(day);
    };
    container.appendChild(btn);
  });
}

function toggleRecurDays(prefix) {
  const sel = document.getElementById(prefix+'-recur');
  const row = document.getElementById(prefix+'-days-row');
  row.style.display = sel.value === 'custom' ? 'block' : 'none';
}

// ── Navigation ────────────────────────────────────────────────────────────────
function selectCategory(catId, el) {
  currentCatId = catId;
  document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
  el.classList.add('active');
  const cat = categories.find(c => c.id === catId);
  document.getElementById('view-title').textContent =
    cat ? cat.name : 'Toutes les tâches';
  loadTasks();
}

function switchView(view, el) {
  currentView = view;
  document.getElementById('view-list').style.display = view==='list' ? 'block' : 'none';
  document.getElementById('view-kanban').style.display = view==='kanban' ? 'block' : 'none';
  document.getElementById('view-add').style.display = view==='add' ? 'block' : 'none';
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  if (el) el.classList.add('active');
  if (view === 'list') loadTasks();
  if (view === 'kanban') loadKanban();
}

function setStatus(s, el) {
  currentStatus = s;
  document.querySelectorAll('.filters .filter-btn').forEach(b => b.classList.remove('active'));
  if (el) el.classList.add('active');
  loadTasks();
}

function debounceSearch() {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    currentSearch = document.getElementById('search-input').value;
    loadTasks();
  }, 300);
}

// ── Priorité & Statut helpers ─────────────────────────────────────────────────
function setPrio(prefix, val, el) {
  if (prefix === 'add') addPrio = val;
  else editPrio = val;
  const btns = document.getElementById(prefix+'-prio-btns');
  btns.querySelectorAll('.seg-btn').forEach(b => b.classList.remove('active'));
  el.classList.add('active');
}

function setStatus2(val, el) {
  editStatus = val;
  document.getElementById('edit-status-btns').querySelectorAll('.seg-btn')
    .forEach(b => b.classList.remove('active'));
  el.classList.add('active');
}

function activateSeg(container, value, map) {
  container.querySelectorAll('.seg-btn').forEach(b => {
    if (map ? map(b) === value : b.textContent === value)
      b.classList.add('active');
    else b.classList.remove('active');
  });
}

// ── Chargement tâches ─────────────────────────────────────────────────────────
const PRIO_COLOR = {urgent:'#FF4444',high:'#FF8C00',normal:'#1E90FF',low:'#555'};
const PRIO_LBL   = {urgent:'🔴 Urgent',high:'🟠 Haute',normal:'🔵 Normal',low:'⚪ Basse'};
const STATUS_LBL = {todo:'📋 À faire',in_progress:'⚙️ En cours',done:'✅ Terminé'};
const STATUS_BADGE = {todo:'badge-todo',in_progress:'badge-wip',done:'badge-done'};

function getDeadlineBadge(task) {
  if (!task.reminder) return '';
  const now  = new Date();
  const rem  = new Date(task.reminder);
  const diff = Math.floor((rem - now) / 86400000);
  if (rem < now && task.status !== 'done')
    return '<span class="badge badge-overdue">⚠ EN RETARD</span>';
  if (diff === 0) return '<span class="badge badge-today">🔔 AUJOURD'HUI</span>';
  if (diff === 1) return '<span class="badge badge-tomorrow">📅 DEMAIN</span>';
  if (diff <= 7)  return `<span class="badge badge-soon">📅 J-${diff}</span>`;
  return '';
}

function getSmartSortKey(t) {
  if (t.status === 'done') return [99,0];
  const now = new Date();
  const rem = t.reminder ? new Date(t.reminder) : null;
  const pc  = {urgent:4,high:3,normal:2,low:1};
  const p   = 5 - (pc[t.priority]||2);
  if (rem) {
    if (rem < now) return [0, p];
    const diff = (rem - now) / 86400000;
    if (diff < 1)  return [1, p];
    if (diff < 7)  return [2, p];
    return [3, p, diff];
  }
  return [4, p];
}

async function loadTasks() {
  if (currentView !== 'list') return;
  const el = document.getElementById('tasks-container');
  el.innerHTML = '<div style="color:#555;padding:20px">Chargement...</div>';
  try {
    let url = '/tasks?include_archived=false';
    if (currentCatId)    url += '&category_id=' + currentCatId;
    if (currentStatus)   url += '&status=' + currentStatus;
    let tasks = await apiFetch(url);

    if (currentSearch) {
      const kw = currentSearch.toLowerCase();
      tasks = tasks.filter(t =>
        (t.title||'').toLowerCase().includes(kw) ||
        (t.description||'').toLowerCase().includes(kw));
    }

    tasks.sort((a,b) => {
      const ka = getSmartSortKey(a), kb = getSmartSortKey(b);
      for (let i=0; i<Math.max(ka.length,kb.length); i++) {
        const d = (ka[i]||0) - (kb[i]||0);
        if (d !== 0) return d;
      }
      return 0;
    });

    // Mettre à jour sidebar count
    document.getElementById('count-all').textContent = tasks.length;

    if (!tasks.length) {
      el.innerHTML = '<div style="color:#555;padding:30px;text-align:center">' +
        (currentCatId
          ? 'Aucune tâche dans cette catégorie.<br><small>Les tâches sans catégorie sont dans "Toutes".</small>'
          : 'Aucune tâche. Cliquez + Nouvelle pour commencer !') +
        '</div>';
      return;
    }

    // Groupement
    const groups = {0:[],1:[],2:[],3:[],4:[],99:[]};
    tasks.forEach(t => {
      const key = getSmartSortKey(t)[0];
      groups[key] = groups[key]||[];
      groups[key].push(t);
    });

    const GROUP_INFO = {
      0: ['⚠️ En retard','#FF4444'],
      1: ['🔔 Aujourd'hui','#FF8C00'],
      2: ['📅 Cette semaine','#FFD700'],
      3: ['🗓️ Prochainement','#1E90FF'],
      4: ['📋 Sans échéance','#888888'],
      99:['✅ Terminées','#32CD32']
    };

    let html = '';
    Object.keys(groups).forEach(g => {
      const group = groups[g];
      if (!group||!group.length) return;
      const [label, color] = GROUP_INFO[g]||['','#888'];
      html += `<div class="group-header">
        <div class="group-line" style="background:${color};opacity:0.4"></div>
        <span style="color:${color};white-space:nowrap;padding:0 8px;font-size:0.8em">${label}</span>
        <div class="group-line" style="background:${color};opacity:0.4"></div>
      </div>`;
      group.forEach(t => { html += renderTaskCard(t); });
    });

    el.innerHTML = html;
  } catch(e) {
    el.innerHTML = '<div style="color:#FF4444;padding:20px">Erreur : ' + e.message + '</div>';
  }
}

function renderTaskCard(t) {
  const pcolor  = PRIO_COLOR[t.priority]||'#888';
  const sbadge  = STATUS_BADGE[t.status]||'badge-todo';
  const dlbadge = getDeadlineBadge(t);
  const recurBadge = t.recurrence && t.recurrence!=='' ?
    `<span class="badge badge-recur">🔁 ${RECUR_FR[t.recurrence]||''}</span>` : '';
  const catInfo = t.category ?
    `<span style="color:${getCatColor(t.category)}">● ${t.category}</span>` : '';
  const remInfo = t.reminder ?
    `<span>⏰ ${new Date(t.reminder).toLocaleString('fr-FR',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'})}</span>` : '';
  let prog = '';
  if (t.subtask_count > 0) {
    const pct = Math.round(t.subtask_done/t.subtask_count*100);
    const fill = t.subtask_done===t.subtask_count ? '#32CD32' : '#1E90FF';
    prog = `<div style="font-size:0.75em;color:#888;margin-top:3px">${t.subtask_done}/${t.subtask_count} sous-tâches</div>
    <div class="progress-bar"><div class="progress-fill" style="width:${pct}%;background:${fill}"></div></div>`;
  }
  const desc = t.description ?
    `<div class="task-desc">${escHtml(t.description.substring(0,100))}</div>` : '';

  return `<div class="task-card prio-${t.priority}" onclick="openEditTask(${t.id})" style="border-left-color:${pcolor}">
    <div class="task-header">
      <div class="task-title">${escHtml(t.title)}</div>
      <div class="task-badges">
        ${dlbadge}
        ${recurBadge}
        <span class="badge ${sbadge}">${STATUS_LBL[t.status]||t.status}</span>
      </div>
    </div>
    ${desc}
    <div class="task-meta">${catInfo}${remInfo}</div>
    ${prog}
  </div>`;
}

function getCatColor(catName) {
  const cat = categories.find(c => c.name === catName);
  return cat ? cat.color : '#888';
}

// ── Kanban ────────────────────────────────────────────────────────────────────
async function loadKanban() {
  const board = document.getElementById('kanban-board');
  board.innerHTML = '<div style="color:#555;padding:20px">Chargement...</div>';
  try {
    const cols = [
      ['todo',        '📋 À faire',  '#888'],
      ['in_progress', '⚙️ En cours',  '#FF8C00'],
      ['done',        '✅ Terminé',   '#32CD32'],
    ];
    let allTasks = await apiFetch('/tasks');
    if (currentCatId)
      allTasks = allTasks.filter(t => {
        const cat = categories.find(c => c.id === currentCatId);
        return cat && t.category === cat.name;
      });

    board.innerHTML = '';
    cols.forEach(([status, label, color]) => {
      const tasks = allTasks.filter(t => t.status === status);
      const col   = document.createElement('div');
      col.className = 'kanban-col';
      col.innerHTML = `<div class="kanban-col-header">
        <span style="color:${color}">${label}</span>
        <span style="color:#555;font-size:0.85em">${tasks.length}</span>
      </div>
      <div class="kanban-col-body" id="kb-${status}"></div>`;
      board.appendChild(col);
      const body = col.querySelector('.kanban-col-body');
      tasks.forEach(t => {
        const card = document.createElement('div');
        card.className = `task-card prio-${t.priority}`;
        card.style.borderLeftColor = PRIO_COLOR[t.priority]||'#888';
        card.style.marginBottom = '6px';
        const prog = t.subtask_count > 0 ?
          `<div class="progress-bar" style="margin-top:4px">
            <div class="progress-fill" style="width:${Math.round(t.subtask_done/t.subtask_count*100)}%;background:${t.subtask_done===t.subtask_count?'#32CD32':'#1E90FF'}"></div>
          </div>` : '';
        card.innerHTML = `<div style="font-weight:bold;font-size:0.88em;margin-bottom:4px">${escHtml(t.title)}</div>
          <div style="font-size:0.75em;color:#666">${t.category||''} ${t.reminder?'⏰':''}${getDeadlineBadge(t)}</div>
          ${prog}
          <div style="display:flex;gap:4px;margin-top:6px">
            ${status!=='todo' ? `<button class="btn btn-gray btn-sm" onclick="event.stopPropagation();moveTask(${t.id},'${prevStatus(status)}')">←</button>` : ''}
            ${status!=='done' ? `<button class="btn btn-primary btn-sm" onclick="event.stopPropagation();moveTask(${t.id},'${nextStatus(status)}')">→</button>` : ''}
            <button class="btn btn-gray btn-sm" style="margin-left:auto" onclick="event.stopPropagation();openEditTask(${t.id})">✏</button>
          </div>`;
        card.onclick = () => openEditTask(t.id);
        body.appendChild(card);
      });
    });
  } catch(e) {
    board.innerHTML = '<div style="color:#FF4444;padding:20px">Erreur : ' + e.message + '</div>';
  }
}

function prevStatus(s){return s==='in_progress'?'todo':'in_progress'}
function nextStatus(s){return s==='todo'?'in_progress':'done'}

async function moveTask(id, status) {
  await apiFetch(`/task/${id}`,{method:'PUT',body:{status}});
  loadKanban();
  loadTasks();
}

// ── Modal Edition ─────────────────────────────────────────────────────────────
async function openEditTask(taskId) {
  currentTaskId = taskId;
  try {
    const t = await apiFetch(`/task/${taskId}`);
    document.getElementById('edit-modal-title').textContent = '✏️ ' + t.title;
    document.getElementById('edit-title').value = t.title || '';
    document.getElementById('edit-desc').value  = t.description || '';

    // Catégorie
    const catSel = document.getElementById('edit-cat');
    for (let i=0; i<catSel.options.length; i++)
      if (catSel.options[i].value === t.category) { catSel.selectedIndex=i; break; }

    // Priorité
    editPrio = t.priority || 'normal';
    const prioMap = {low:'Basse',normal:'Normal',high:'Haute',urgent:'Urgent'};
    document.getElementById('edit-prio-btns').querySelectorAll('.seg-btn').forEach(b => {
      b.classList.toggle('active',
        b.textContent === (prioMap[editPrio]||'Normal'));
    });

    // Statut
    editStatus = t.status || 'todo';
    const statusMap = {todo:'📋 À faire',in_progress:'⚙️ En cours',done:'✅ Terminé'};
    document.getElementById('edit-status-btns').querySelectorAll('.seg-btn').forEach(b => {
      b.classList.toggle('active', b.textContent.trim() === statusMap[editStatus]);
    });

    // Rappel
    if (t.reminder) {
      const dt = new Date(t.reminder);
      const local = new Date(dt.getTime() - dt.getTimezoneOffset()*60000)
        .toISOString().slice(0,16);
      document.getElementById('edit-reminder').value = local;
    } else {
      document.getElementById('edit-reminder').value = '';
    }

    // Récurrence
    const recurSel = document.getElementById('edit-recur');
    recurSel.value = t.recurrence || '';
    editRecurDays  = [];
    if (t.recurrence === 'custom' && t.recurrence_days) {
      try {
        editRecurDays = JSON.parse(t.recurrence_days);
      } catch(e) {}
    }
    toggleRecurDays('edit');
    // Activer les jours
    document.getElementById('edit-days').querySelectorAll('.day-btn').forEach(b => {
      b.classList.toggle('active', editRecurDays.includes(b.dataset.day));
    });

    // Ouvrir section rappel si données
    if (t.reminder || t.recurrence) openAcc('acc-remind');

    // Sous-tâches
    renderSubtasks(t.subtasks || []);

    // PJ
    const attList = document.getElementById('att-list');
    if (t.attachments_list && t.attachments_list.length) {
      attList.innerHTML = t.attachments_list.map(a =>
        `<div class="att-item">📎 ${escHtml(a)}</div>`).join('');
      openAcc('acc-pj');
    } else {
      attList.innerHTML = '<div style="color:#555;font-size:0.8em">Aucune pièce jointe.</div>';
    }

    document.getElementById('edit-overlay').classList.add('open');
  } catch(e) {
    toast('Erreur chargement : ' + e.message, false);
  }
}

function openNewTask() {
  switchView('add');
  document.querySelectorAll('.tab').forEach((t,i) => t.classList.toggle('active',i===2));
}

function closeEdit() {
  document.getElementById('edit-overlay').classList.remove('open');
  currentTaskId = null;
  loadTasks();
  if (currentView === 'kanban') loadKanban();
}

function maybeCloseEdit(e) {
  if (e.target === document.getElementById('edit-overlay')) closeEdit();
}

// ── Sous-tâches modal ─────────────────────────────────────────────────────────
function renderSubtasks(subs) {
  const el   = document.getElementById('subtasks-list');
  const prog = document.getElementById('sub-progress-badge');
  const fill = document.getElementById('sub-fill');
  const bar  = document.getElementById('sub-progress-bar');
  const done = subs.filter(s=>s.done).length;
  const total= subs.length;
  if (total > 0) {
    const pct = Math.round(done/total*100);
    prog.textContent = `${done}/${total}`;
    fill.style.width = pct+'%';
    fill.style.background = done===total?'#32CD32':'#1E90FF';
    bar.style.display = 'block';
  } else {
    prog.textContent = '';
    bar.style.display = 'none';
  }
  el.innerHTML = subs.length
    ? subs.map(s => `<div class="subtask-item">
        <input type="checkbox" class="sub-check" ${s.done?'checked':''} onchange="toggleSub(${s.id})">
        <span class="sub-title ${s.done?'done':''}">${escHtml(s.title)}</span>
        <button class="sub-del" onclick="deleteSub(${s.id})">✕</button>
      </div>`).join('')
    : '<div style="color:#555;font-size:0.82em;padding:4px 0">Aucune sous-tâche.</div>';
}

async function toggleSub(subId) {
  if (!currentTaskId) return;
  await apiFetch(`/task/${currentTaskId}/subtask/${subId}/toggle`,{method:'POST'});
  const t = await apiFetch(`/task/${currentTaskId}`);
  renderSubtasks(t.subtasks||[]);
}

async function addSub() {
  if (!currentTaskId) return;
  const inp   = document.getElementById('new-sub');
  const title = inp.value.trim();
  if (!title) return;
  try {
    await apiFetch(`/task/${currentTaskId}/subtask`,{method:'POST',body:{title}});
    inp.value = '';
    const t = await apiFetch(`/task/${currentTaskId}`);
    renderSubtasks(t.subtasks||[]);
  } catch(e) { toast('Limite 10 sous-tâches atteinte',false); }
}

async function deleteSub(subId) {
  if (!currentTaskId) return;
  await apiFetch(`/task/${currentTaskId}/subtask/${subId}`,{method:'DELETE'});
  const t = await apiFetch(`/task/${currentTaskId}`);
  renderSubtasks(t.subtasks||[]);
}

async function genSubsAI() {
  if (!currentTaskId) return;
  const title = document.getElementById('edit-title').value;
  const desc  = document.getElementById('edit-desc').value;
  const st    = document.getElementById('sub-ai-status');
  st.textContent = '🤖 Mistral génère les sous-tâches...';
  document.getElementById('ai-suggestions').style.display = 'none';
  try {
    const d = await apiFetch(`/task/${currentTaskId}/subtasks/ai`,{
      method:'POST', body:{task_title:title, task_desc:desc}});
    aiSuggestions = d.suggestions || [];
    if (!aiSuggestions.length) { st.textContent='Aucune suggestion.'; return; }
    st.textContent = '';
    const slist = document.getElementById('ai-sug-list');
    slist.innerHTML = aiSuggestions.map((s,i) =>
      `<div style="display:flex;align-items:center;gap:6px;padding:3px 0">
        <input type="checkbox" id="sug-${i}" checked style="accent-color:#9370DB">
        <label for="sug-${i}" style="font-size:0.88em">${escHtml(s)}</label>
      </div>`).join('');
    document.getElementById('ai-suggestions').style.display = 'block';
  } catch(e) {
    st.textContent = 'Erreur : ' + e.message;
  }
}

async function addSelectedSubs() {
  if (!currentTaskId) return;
  for (let i=0; i<aiSuggestions.length; i++) {
    const cb = document.getElementById('sug-'+i);
    if (cb && cb.checked) {
      try {
        await apiFetch(`/task/${currentTaskId}/subtask`,
          {method:'POST',body:{title:aiSuggestions[i]}});
      } catch(e) {}
    }
  }
  document.getElementById('ai-suggestions').style.display = 'none';
  document.getElementById('sub-ai-status').textContent = '';
  const t = await apiFetch(`/task/${currentTaskId}`);
  renderSubtasks(t.subtasks||[]);
}

// ── Sauvegarde édition ────────────────────────────────────────────────────────
async function saveEdit() {
  if (!currentTaskId) return;
  const title = document.getElementById('edit-title').value.trim();
  if (!title) { toast('Titre obligatoire !',false); return; }

  const remVal = document.getElementById('edit-reminder').value;
  const recurVal= document.getElementById('edit-recur').value;

  try {
    await apiFetch(`/task/${currentTaskId}`,{method:'PUT',body:{
      title,
      description: document.getElementById('edit-desc').value,
      category:    document.getElementById('edit-cat').value,
      priority:    editPrio,
      status:      editStatus,
    }});

    if (remVal)
      await apiFetch(`/task/${currentTaskId}/reminder`,{method:'PUT',body:{reminder:remVal+':00'}});
    else
      await apiFetch(`/task/${currentTaskId}/reminder`,{method:'PUT',body:{reminder:null}});

    await apiFetch(`/task/${currentTaskId}/recurrence`,{method:'PUT',body:{
      recurrence:      recurVal || 'none',
      recurrence_days: recurVal==='custom' ? JSON.stringify(editRecurDays) : null,
    }});

    toast('Tâche mise à jour !', true);
    closeEdit();
  } catch(e) { toast('Erreur : '+e.message, false); }
}

// ── Créer tâche ───────────────────────────────────────────────────────────────
async function createTask() {
  const title = document.getElementById('add-title').value.trim();
  const st    = document.getElementById('add-status');
  if (!title) { document.getElementById('add-status').textContent='Titre obligatoire !'; return; }
  const remVal   = document.getElementById('add-reminder').value;
  const recurVal = document.getElementById('add-recur').value;
  try {
    const t = await apiFetch('/task',{method:'POST',body:{
      title,
      description: document.getElementById('add-desc').value,
      category:    document.getElementById('add-cat').value,
      priority:    addPrio,
      reminder:    remVal ? remVal+':00' : null,
    }});
    if (recurVal) {
      await apiFetch(`/task/${t.id}/recurrence`,{method:'PUT',body:{
        recurrence:      recurVal,
        recurrence_days: recurVal==='custom' ? JSON.stringify(addRecurDays) : null,
      }});
    }
    toast('Tâche #'+t.id+' créée !', true);
    document.getElementById('add-title').value = '';
    document.getElementById('add-desc').value  = '';
    document.getElementById('add-reminder').value = '';
    document.getElementById('add-recur').value = '';
    addPrio = 'normal';
    document.getElementById('add-prio-btns').querySelectorAll('.seg-btn')
      .forEach((b,i) => b.classList.toggle('active',i===1));
    switchView('list');
  } catch(e) { document.getElementById('add-status').textContent='Erreur : '+e.message; }
}

// ── Actions globales ──────────────────────────────────────────────────────────
async function archiveDone() {
  if (!confirm('Archiver toutes les tâches terminées ?')) return;
  const d = await apiFetch('/tasks/archive-done',{method:'POST'});
  toast(d.archived + ' tâche(s) archivée(s)', true);
  loadTasks();
}

async function deleteDone() {
  if (!confirm('Supprimer définitivement toutes les tâches terminées ?')) return;
  const d = await apiFetch('/tasks/delete-done',{method:'DELETE'});
  toast(d.deleted + ' tâche(s) supprimée(s)', true);
  loadTasks();
}

async function archiveCurrentTask() {
  if (!currentTaskId) return;
  await apiFetch(`/task/${currentTaskId}/archive`,{method:'POST'});
  toast('Tâche archivée', true);
  closeEdit();
}

async function deleteCurrentTask() {
  if (!currentTaskId || !confirm('Supprimer cette tâche ?')) return;
  await apiFetch(`/task/${currentTaskId}`,{method:'DELETE'});
  toast('Tâche supprimée', true);
  closeEdit();
}

// ── Archives ──────────────────────────────────────────────────────────────────
async function openArchives() {
  document.getElementById('arch-overlay').classList.add('open');
  const body = document.getElementById('arch-body');
  body.innerHTML = 'Chargement...';
  try {
    const tasks = await apiFetch('/tasks/archived');
    if (!tasks.length) {
      body.innerHTML = '<div style="color:#555;text-align:center;padding:20px">Aucune tâche archivée.</div>';
      return;
    }
    body.innerHTML = tasks.map(t => `
      <div style="display:flex;align-items:center;gap:8px;padding:8px;background:#0f3460;border-radius:6px;margin-bottom:6px">
        <div style="flex:1">
          <div style="font-weight:bold;font-size:0.9em">${escHtml(t.title)}</div>
          <div style="font-size:0.75em;color:#666">${t.category||''} ${t.updated?'— '+new Date(t.updated).toLocaleDateString('fr-FR'):''}</div>
        </div>
        <button class="btn btn-success btn-sm" onclick="restoreTask(${t.id})">↩ Restaurer</button>
        <button class="btn btn-danger btn-sm" onclick="deleteArchivedTask(${t.id})">✕</button>
      </div>`).join('');
  } catch(e) { body.innerHTML = 'Erreur : '+e.message; }
}

async function restoreTask(id) {
  await apiFetch(`/task/${id}/unarchive`,{method:'POST'});
  toast('Tâche restaurée !', true);
  openArchives();
  loadTasks();
}

async function deleteArchivedTask(id) {
  if (!confirm('Supprimer définitivement ?')) return;
  await apiFetch(`/task/${id}`,{method:'DELETE'});
  toast('Supprimée', true);
  openArchives();
}

function closeArchives() {
  document.getElementById('arch-overlay').classList.remove('open');
}

// ── IA ────────────────────────────────────────────────────────────────────────
function openAI() { document.getElementById('ai-overlay').classList.add('open'); }
function closeAI() { document.getElementById('ai-overlay').classList.remove('open'); }

async function sendAI() {
  const text = document.getElementById('ai-prompt').value.trim();
  const res  = document.getElementById('ai-result');
  if (!text) return;
  res.style.display = 'block';
  res.textContent = '🤖 Mistral analyse...';
  try {
    const d = await apiFetch('/task/ai',{method:'POST',body:{text}});
    res.textContent = d.result;
    loadTasks();
  } catch(e) { res.textContent = 'Erreur : '+e.message; }
}

// ── Accordion ─────────────────────────────────────────────────────────────────
function toggleAcc(id) {
  const body  = document.querySelector('#'+id+' .accordion-body');
  const arrow = document.querySelector('#'+id+' .accordion-arrow');
  const open  = body.classList.toggle('open');
  arrow.textContent = open ? '▼' : '▶';
}

function openAcc(id) {
  const body  = document.querySelector('#'+id+' .accordion-body');
  const arrow = document.querySelector('#'+id+' .accordion-arrow');
  if (!body.classList.contains('open')) {
    body.classList.add('open');
    arrow.textContent = '▼';
  }
}

// ── Utilitaires ───────────────────────────────────────────────────────────────
async function apiFetch(path, opts={}) {
  const options = {method: opts.method||'GET', headers:{'Content-Type':'application/json'}};
  if (opts.body) options.body = JSON.stringify(opts.body);
  const resp = await fetch(API+path, options);
  if (!resp.ok) {
    const err = await resp.json().catch(()=>({}));
    throw new Error(err.detail || resp.statusText);
  }
  return resp.json();
}

function toast(msg, ok) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className   = 'toast show ' + (ok?'ok':'err');
  setTimeout(() => el.classList.remove('show'), 3000);
}

function escHtml(s) {
  return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// Keyboard
document.addEventListener('keydown', e => {
  if (e.key==='Escape') {
    closeEdit();
    closeArchives();
    closeAI();
  }
});

init();
setInterval(() => { if(currentView==='list') loadTasks(); }, 60000);
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def web_ui():
    """Page web mobile pour creer et gerer des taches."""
    return WEB_UI


_server_thread = None
_server        = None


def start_api_server(port: int = 8765, ui_callback=None, tk_app=None):
    global _server_thread, _server

    if ui_callback:
        set_ui_callback(ui_callback)
    if tk_app:
        set_tk_app(tk_app)

    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=port,
        log_level="warning",
        access_log=False,
    )
    _server = uvicorn.Server(config)

    def _run():
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_server.serve())

    _server_thread = threading.Thread(target=_run, daemon=True, name="QuickMind-API")
    _server_thread.start()

    import socket
    try:
        ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        ip = "localhost"

    print(f"[API] Serveur demarre :")
    print(f"[API]   Local  : http://localhost:{port}")
    print(f"[API]   Reseau : http://{ip}:{port}")
    print(f"[API]   Docs   : http://localhost:{port}/docs")
