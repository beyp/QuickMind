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
    # FastAPI peut recevoir "false" comme string depuis l URL
    if isinstance(include_archived, str):
        include_archived = include_archived.lower() not in ('false','0','no')
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
<meta name="viewport" content="width=device-width,initial-scale=1.0,maximum-scale=1.0">
<title>QuickMind</title>
<style>
:root{
  --bg:#0f1117;--bg2:#1a1d27;--bg3:#242838;--bg4:#2e3347;
  --border:#2e3347;--border2:#3d4460;
  --blue:#4f8ef7;--blue2:#3a6fd4;--blue3:#1e3a6e;
  --green:#3ecf6e;--green2:#1a5c35;
  --orange:#f7934f;--orange2:#7a4020;
  --red:#f75f5f;--red2:#7a2020;
  --purple:#a78bfa;--purple2:#3d2a6e;
  --yellow:#f7d04f;--yellow2:#6e5a20;
  --text:#e8eaf6;--text2:#9298b5;--text3:#6b7194;
  --radius:10px;--radius2:6px;
  --shadow:0 4px 20px rgba(0,0,0,.4);
}
*{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:var(--bg);color:var(--text);min-height:100vh;font-size:14px}
::-webkit-scrollbar{width:5px;height:5px}
::-webkit-scrollbar-track{background:var(--bg)}
::-webkit-scrollbar-thumb{background:var(--border2);border-radius:3px}

/* Layout */
.layout{display:flex;height:100vh;overflow:hidden}

/* Sidebar */
.sidebar{
  width:220px;background:var(--bg2);border-right:1px solid var(--border);
  display:flex;flex-direction:column;flex-shrink:0;transition:width .2s
}
.sb-logo{padding:16px 14px 12px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:10px}
.sb-logo-icon{width:32px;height:32px;background:linear-gradient(135deg,var(--blue),var(--purple));border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:16px;flex-shrink:0}
.sb-logo-text{font-weight:700;font-size:1em;color:var(--text)}
.sb-logo-sub{font-size:.7em;color:var(--text3);margin-top:1px}
.sb-status{display:flex;align-items:center;gap:5px;padding:0 14px 10px;font-size:.72em;color:var(--text3)}
.sb-dot{width:6px;height:6px;border-radius:50%;background:#555;flex-shrink:0;transition:background .3s}
.sb-dot.on{background:var(--green)}
.sb-nav{flex:1;overflow-y:auto;padding:8px 8px}
.nav-section{font-size:.68em;font-weight:600;color:var(--text3);padding:8px 8px 4px;text-transform:uppercase;letter-spacing:.08em}
.nav-item{
  display:flex;align-items:center;gap:8px;padding:7px 10px;
  border-radius:var(--radius2);cursor:pointer;font-size:.85em;color:var(--text2);
  transition:all .15s;margin-bottom:2px;border:1px solid transparent
}
.nav-item:hover{background:var(--bg3);color:var(--text)}
.nav-item.active{background:var(--blue3);color:var(--blue);border-color:var(--blue3)}
.nav-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.nav-count{margin-left:auto;font-size:.72em;background:var(--bg4);padding:1px 6px;border-radius:10px;color:var(--text3)}
.nav-item.active .nav-count{background:var(--blue3);color:var(--blue)}

/* Main */
.main{flex:1;display:flex;flex-direction:column;overflow:hidden;min-width:0}

/* Topbar */
.topbar{
  padding:10px 16px;background:var(--bg2);border-bottom:1px solid var(--border);
  display:flex;align-items:center;gap:8px;flex-shrink:0;flex-wrap:wrap
}
.tb-title{font-weight:600;font-size:.95em;color:var(--text);margin-right:4px}
.tb-spacer{flex:1}

/* Tabs */
.tabs{display:flex;background:var(--bg2);border-bottom:1px solid var(--border);padding:0 16px;flex-shrink:0}
.tab{
  padding:9px 14px;cursor:pointer;font-size:.82em;color:var(--text3);
  border-bottom:2px solid transparent;white-space:nowrap;transition:all .15s;
  display:flex;align-items:center;gap:5px
}
.tab:hover{color:var(--text)}
.tab.active{color:var(--blue);border-bottom-color:var(--blue)}

/* Content */
.content{flex:1;overflow-y:auto;padding:14px 16px}

/* Filter bar */
.filter-bar{display:flex;align-items:center;gap:6px;margin-bottom:10px;flex-wrap:wrap}
.filter-chip{
  padding:4px 10px;border-radius:20px;border:1px solid var(--border2);
  cursor:pointer;font-size:.78em;color:var(--text3);background:var(--bg2);
  transition:all .15s;white-space:nowrap
}
.filter-chip:hover{border-color:var(--blue);color:var(--blue)}
.filter-chip.active{background:var(--blue3);color:var(--blue);border-color:var(--blue3)}
.search-wrap{flex:1;min-width:160px;position:relative}
.search-wrap input{
  width:100%;padding:6px 10px 6px 32px;border-radius:20px;
  border:1px solid var(--border2);background:var(--bg3);
  color:var(--text);font-size:.82em;outline:none;transition:border .15s
}
.search-wrap input:focus{border-color:var(--blue)}
.search-icon{position:absolute;left:10px;top:50%;transform:translateY(-50%);color:var(--text3);font-size:12px;pointer-events:none}

/* Action bar */
.action-bar{display:flex;gap:6px;margin-bottom:10px;flex-wrap:wrap}

/* Group header */
.group-hdr{display:flex;align-items:center;gap:8px;margin:14px 0 6px}
.group-hdr:first-child{margin-top:0}
.group-line{flex:1;height:1px;opacity:.3}
.group-label{font-size:.72em;font-weight:600;white-space:nowrap;text-transform:uppercase;letter-spacing:.06em;padding:2px 8px;border-radius:10px}

/* Task cards — VUE CONDENSÉE */
.task-card{
  background:var(--bg2);border-radius:var(--radius);
  border:1px solid var(--border);border-left:3px solid var(--blue);
  margin-bottom:6px;cursor:pointer;transition:all .15s;
  overflow:hidden
}
.task-card:hover{border-color:var(--border2);box-shadow:var(--shadow);transform:translateY(-1px)}
.task-card.purg{border-left-color:var(--red)}
.task-card.phig{border-left-color:var(--orange)}
.task-card.pnor{border-left-color:var(--blue)}
.task-card.plow{border-left-color:var(--text3)}
.task-card.pdone{border-left-color:var(--green);opacity:.75}

.tc-main{display:flex;align-items:flex-start;gap:10px;padding:10px 12px}
.tc-prio{font-size:14px;flex-shrink:0;margin-top:1px}
.tc-body{flex:1;min-width:0}
.tc-row1{display:flex;align-items:flex-start;gap:6px}
.tc-title{font-weight:600;font-size:.9em;flex:1;line-height:1.3}
.tc-badges{display:flex;gap:3px;flex-wrap:wrap;flex-shrink:0}
.badge{display:inline-flex;align-items:center;gap:3px;padding:2px 6px;border-radius:8px;font-size:.68em;font-weight:600;white-space:nowrap}
.b-todo{background:#1e2333;color:var(--text3)}
.b-wip{background:var(--orange2);color:var(--orange)}
.b-done{background:var(--green2);color:var(--green)}
.b-late{background:var(--red2);color:var(--red)}
.b-today{background:var(--orange2);color:var(--orange)}
.b-tmw{background:var(--yellow2);color:var(--yellow)}
.b-soon{background:var(--green2);color:var(--green)}
.b-rec{background:var(--purple2);color:var(--purple)}
.tc-meta{display:flex;gap:8px;margin-top:4px;font-size:.72em;color:var(--text3);flex-wrap:wrap;align-items:center}
.tc-cat{display:flex;align-items:center;gap:3px}
.tc-cat-dot{width:6px;height:6px;border-radius:50%}
.tc-desc{font-size:.78em;color:var(--text3);margin-top:3px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:100%}
.tc-progress{margin-top:5px;display:flex;align-items:center;gap:6px}
.progress-track{flex:1;height:3px;background:var(--bg4);border-radius:2px;overflow:hidden}
.progress-fill{height:100%;border-radius:2px;transition:width .3s}
.progress-text{font-size:.68em;color:var(--text3);white-space:nowrap}

/* Kanban */
.kanban-wrap{display:flex;gap:12px;height:calc(100vh - 140px);overflow-x:auto;padding-bottom:8px}
.k-col{min-width:270px;flex:1;background:var(--bg2);border-radius:var(--radius);display:flex;flex-direction:column;max-height:100%;border:1px solid var(--border)}
.k-col-hdr{padding:10px 12px;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);flex-shrink:0}
.k-col-title{font-weight:600;font-size:.85em;display:flex;align-items:center;gap:6px}
.k-col-count{font-size:.72em;color:var(--text3);background:var(--bg4);padding:1px 6px;border-radius:8px}
.k-col-body{flex:1;overflow-y:auto;padding:8px}

/* Buttons */
.btn{display:inline-flex;align-items:center;gap:5px;padding:6px 12px;border-radius:var(--radius2);border:none;cursor:pointer;font-size:.82em;font-weight:500;transition:all .15s;white-space:nowrap}
.btn:hover{opacity:.88;transform:translateY(-1px)}
.btn:active{transform:translateY(0);opacity:1}
.btn-primary{background:var(--blue);color:#fff}
.btn-success{background:var(--green2);color:var(--green);border:1px solid var(--green2)}
.btn-danger{background:var(--red2);color:var(--red);border:1px solid var(--red2)}
.btn-warning{background:var(--orange2);color:var(--orange);border:1px solid var(--orange2)}
.btn-ghost{background:var(--bg3);color:var(--text2);border:1px solid var(--border2)}
.btn-purple{background:var(--purple2);color:var(--purple);border:1px solid var(--purple2)}
.btn-sm{padding:4px 8px;font-size:.75em}

/* Modal */
.overlay{position:fixed;inset:0;background:rgba(0,0,0,.65);z-index:300;display:none;overflow-y:auto;backdrop-filter:blur(4px)}
.overlay.open{display:flex;align-items:flex-start;justify-content:center;padding:20px}
.modal{background:var(--bg2);border-radius:var(--radius);border:1px solid var(--border2);width:100%;max-width:620px;box-shadow:var(--shadow);overflow:hidden;animation:slideIn .2s ease}
@keyframes slideIn{from{opacity:0;transform:translateY(-20px)}to{opacity:1;transform:translateY(0)}}
.modal-hdr{padding:14px 18px;background:var(--bg3);border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center}
.modal-title{font-weight:600;font-size:.95em;color:var(--text)}
.modal-close{background:none;border:none;color:var(--text3);font-size:1.3em;cursor:pointer;padding:2px 6px;border-radius:4px;line-height:1}
.modal-close:hover{background:var(--bg4);color:var(--text)}
.modal-body{padding:16px 18px;max-height:68vh;overflow-y:auto}
.modal-footer{padding:12px 18px;background:var(--bg3);border-top:1px solid var(--border);display:flex;gap:8px;justify-content:flex-end}

/* Accordion */
.acc{border:1px solid var(--border);border-radius:var(--radius2);margin-bottom:8px;overflow:hidden}
.acc-hdr{
  padding:9px 12px;background:var(--bg3);cursor:pointer;
  display:flex;align-items:center;gap:8px;font-size:.85em;font-weight:600;
  user-select:none;transition:background .15s
}
.acc-hdr:hover{background:var(--bg4)}
.acc-arrow{font-size:.8em;transition:transform .2s;color:var(--text3)}
.acc-arrow.open{transform:rotate(90deg)}
.acc-body{padding:12px;display:none}
.acc-body.open{display:block}

/* Forms */
.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.form-group{display:flex;flex-direction:column;gap:4px}
.form-group.full{grid-column:1/-1}
.form-label{font-size:.75em;color:var(--text3);font-weight:500}
.form-input{
  width:100%;padding:8px 10px;border-radius:var(--radius2);
  border:1px solid var(--border2);background:var(--bg3);
  color:var(--text);font-size:.88em;outline:none;transition:border .15s;
  -webkit-appearance:none
}
.form-input:focus{border-color:var(--blue)}
textarea.form-input{resize:vertical;min-height:60px}
.seg-group{display:flex;border-radius:var(--radius2);overflow:hidden;border:1px solid var(--border2)}
.seg-btn{flex:1;padding:7px 4px;border:none;background:var(--bg3);color:var(--text3);cursor:pointer;font-size:.76em;font-weight:600;text-align:center;transition:all .15s}
.seg-btn:hover{background:var(--bg4)}
.seg-btn.active{background:var(--blue);color:#fff}
.seg-btn.active.stat-wip{background:var(--orange);color:#fff}
.seg-btn.active.stat-done{background:var(--green);color:#fff}

/* Subtasks */
.sub-item{display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--border)}
.sub-item:last-child{border-bottom:none}
.sub-cb{width:15px;height:15px;cursor:pointer;accent-color:var(--blue);flex-shrink:0}
.sub-text{flex:1;font-size:.86em;color:var(--text)}
.sub-text.done{text-decoration:line-through;color:var(--text3)}
.sub-del{background:none;border:none;color:var(--text3);cursor:pointer;font-size:.9em;padding:0 2px;transition:color .15s}
.sub-del:hover{color:var(--red)}
.sub-add{display:flex;gap:6px;margin-top:8px}
.sub-add input{flex:1;margin-bottom:0}

/* Days picker */
.days-picker{display:flex;gap:4px;flex-wrap:wrap;margin-top:4px}
.day-btn{padding:4px 8px;border-radius:4px;border:1px solid var(--border2);background:var(--bg3);color:var(--text3);cursor:pointer;font-size:.74em;font-weight:600;transition:all .15s}
.day-btn.active{background:var(--blue);color:#fff;border-color:var(--blue)}

/* Reminder display in card */
.reminder-badge{display:inline-flex;align-items:center;gap:3px;font-size:.72em;color:var(--text3)}
.reminder-badge.late{color:var(--red)}
.reminder-badge.today{color:var(--orange)}
.reminder-badge.soon{color:var(--yellow)}

/* Toast */
.toast{
  position:fixed;bottom:20px;right:20px;padding:10px 16px;
  border-radius:var(--radius);font-size:.85em;z-index:999;
  opacity:0;transition:all .3s;pointer-events:none;max-width:320px;
  box-shadow:var(--shadow);border:1px solid;
  display:flex;align-items:center;gap:8px
}
.toast.show{opacity:1;transform:translateY(-4px)}
.toast.ok{background:var(--green2);color:var(--green);border-color:var(--green2)}
.toast.err{background:var(--red2);color:var(--red);border-color:var(--red2)}
.toast.info{background:var(--blue3);color:var(--blue);border-color:var(--blue3)}

/* AI suggestions */
.ai-sug-box{border:1px solid var(--purple2);border-radius:var(--radius2);padding:10px;margin-top:8px;background:var(--purple2);background:rgba(167,139,250,.05)}
.ai-sug-item{display:flex;align-items:center;gap:6px;padding:3px 0}
.ai-sug-label{font-size:.85em}

/* Empty state */
.empty{text-align:center;padding:40px 20px;color:var(--text3)}
.empty-icon{font-size:2.5em;margin-bottom:10px;opacity:.5}
.empty-text{font-size:.9em;margin-bottom:4px}
.empty-sub{font-size:.78em;color:var(--text3)}

/* Responsive */
@media(max-width:640px){
  .sidebar{width:100%;height:auto;border-right:none;border-bottom:1px solid var(--border)}
  .layout{flex-direction:column}
  .sb-nav{display:flex;flex-direction:row;overflow-x:auto;padding:4px 8px;gap:4px}
  .nav-section{display:none}
  .nav-item{flex-shrink:0;padding:5px 10px;border-left:none;border-bottom:2px solid transparent}
  .nav-item.active{border-bottom-color:var(--blue);background:transparent}
  .kanban-wrap{flex-direction:column;height:auto}
  .k-col{min-width:auto}
  .form-grid{grid-template-columns:1fr}
  .form-group.full{grid-column:1}
}
</style>
</head>
<body>
<div class="layout">

<!-- Sidebar -->
<div class="sidebar">
  <div class="sb-logo">
    <div class="sb-logo-icon">⚡</div>
    <div>
      <div class="sb-logo-text">QuickMind</div>
      <div class="sb-logo-sub" id="task-count">Chargement...</div>
    </div>
  </div>
  <div class="sb-status">
    <div class="sb-dot" id="sb-dot"></div>
    <span id="sb-status">Connexion...</span>
  </div>
  <div class="sb-nav" id="sb-nav">
    <div class="nav-section">Catégories</div>
    <div class="nav-item active" onclick="selectCat(null,this)" id="nav-all">
      <span>🗂</span><span>Toutes les tâches</span>
      <span class="nav-count" id="nav-count-all">0</span>
    </div>
  </div>
</div>

<!-- Main -->
<div class="main">
  <!-- Topbar -->
  <div class="topbar">
    <span class="tb-title" id="view-title">Toutes les tâches</span>
    <div class="tb-spacer"></div>
    <button class="btn btn-primary btn-sm" onclick="openNew()">+ Nouvelle tâche</button>
    <button class="btn btn-purple btn-sm" onclick="openAI()">🤖 IA</button>
    <button class="btn btn-warning btn-sm" onclick="archDone()">📦 Archiver ✅</button>
    <button class="btn btn-danger btn-sm" onclick="delDone()">🗑 Suppr ✅</button>
    <button class="btn btn-ghost btn-sm" onclick="openArchives()">🗂 Archives</button>
  </div>

  <!-- Tabs -->
  <div class="tabs">
    <div class="tab active" onclick="switchView('list',this)">📋 Liste</div>
    <div class="tab" onclick="switchView('kanban',this)">📊 Kanban</div>
    <div class="tab" onclick="switchView('add',this)">➕ Ajouter</div>
  </div>

  <!-- Content -->
  <div class="content" id="content">

    <!-- Vue Liste -->
    <div id="view-list">
      <div class="filter-bar">
        <button class="filter-chip active" onclick="setStatusFilter('',this)">Toutes</button>
        <button class="filter-chip" onclick="setStatusFilter('todo',this)">À faire</button>
        <button class="filter-chip" onclick="setStatusFilter('in_progress',this)">En cours</button>
        <button class="filter-chip" onclick="setStatusFilter('done',this)">Terminées</button>
        <div class="search-wrap">
          <span class="search-icon">🔍</span>
          <input id="search-input" placeholder="Rechercher..." oninput="doSearch()">
        </div>
      </div>
      <div id="tasks-output">
        <div class="empty"><div class="empty-icon">⏳</div><div class="empty-text">Chargement...</div></div>
      </div>
    </div>

    <!-- Vue Kanban -->
    <div id="view-kanban" style="display:none">
      <div class="kanban-wrap" id="kanban-board"></div>
    </div>

    <!-- Vue Ajouter -->
    <div id="view-add" style="display:none">
      <div style="max-width:520px">
        <div class="form-grid">
          <div class="form-group full">
            <label class="form-label">Titre *</label>
            <input class="form-input" id="add-title" placeholder="Titre de la tâche...">
          </div>
          <div class="form-group">
            <label class="form-label">Catégorie</label>
            <select class="form-input" id="add-cat"></select>
          </div>
          <div class="form-group">
            <label class="form-label">Priorité</label>
            <div class="seg-group" id="add-prio-seg">
              <button class="seg-btn" onclick="setPrio('add','low',this)">🔵 Basse</button>
              <button class="seg-btn active" onclick="setPrio('add','normal',this)">Normal</button>
              <button class="seg-btn" onclick="setPrio('add','high',this)">🟠 Haute</button>
              <button class="seg-btn" onclick="setPrio('add','urgent',this)">🔴 Urgent</button>
            </div>
          </div>
          <div class="form-group full">
            <label class="form-label">Description</label>
            <textarea class="form-input" id="add-desc" rows="3" placeholder="Description (optionnel)..."></textarea>
          </div>
          <div class="form-group">
            <label class="form-label">📅 Rappel</label>
            <input type="datetime-local" class="form-input" id="add-reminder">
          </div>
          <div class="form-group">
            <label class="form-label">🔁 Récurrence</label>
            <select class="form-input" id="add-recur" onchange="toggleDays('add')">
              <option value="">Aucune</option>
              <option value="daily">Quotidienne</option>
              <option value="weekly">Hebdomadaire</option>
              <option value="monthly">Mensuelle</option>
              <option value="yearly">Annuelle</option>
              <option value="custom">Jours spécifiques</option>
            </select>
          </div>
          <div class="form-group full" id="add-days-wrap" style="display:none">
            <label class="form-label">Jours</label>
            <div class="days-picker" id="add-days-picker"></div>
          </div>
        </div>
        <div style="display:flex;gap:8px;margin-top:14px">
          <button class="btn btn-primary" onclick="createTask()">✅ Créer la tâche</button>
          <button class="btn btn-ghost" onclick="switchView('list')">Annuler</button>
        </div>
        <div id="add-msg" style="margin-top:8px;font-size:.82em;color:var(--red)"></div>
      </div>
    </div>
  </div>
</div>
</div>

<!-- ═══════════════════════════════════════════════════════════ -->
<!-- Modal Edition -->
<!-- ═══════════════════════════════════════════════════════════ -->
<div class="overlay" id="edit-overlay" onclick="overlayClose('edit-overlay',event)">
<div class="modal" onclick="event.stopPropagation()">
  <div class="modal-hdr">
    <span class="modal-title" id="edit-modal-title">✏️ Éditer la tâche</span>
    <button class="modal-close" onclick="closeEdit()">✕</button>
  </div>
  <div class="modal-body">

    <!-- Section 1 : Titre & Description -->
    <div class="acc" id="acc-main">
      <div class="acc-hdr" onclick="toggleAcc('acc-main')">
        <span class="acc-arrow open" id="acc-main-arrow">▶</span>
        <span style="color:var(--blue)">📝</span>
        <span>Titre & Description</span>
      </div>
      <div class="acc-body open" id="acc-main-body">
        <div class="form-grid">
          <div class="form-group full">
            <label class="form-label">Titre *</label>
            <input class="form-input" id="edit-title" placeholder="Titre...">
          </div>
          <div class="form-group full">
            <label class="form-label">Description</label>
            <textarea class="form-input" id="edit-desc" rows="3"></textarea>
          </div>
        </div>
      </div>
    </div>

    <!-- Section 2 : Classification -->
    <div class="acc" id="acc-class">
      <div class="acc-hdr" onclick="toggleAcc('acc-class')">
        <span class="acc-arrow open" id="acc-class-arrow">▶</span>
        <span style="color:var(--orange)">🏷️</span>
        <span>Classification</span>
      </div>
      <div class="acc-body open" id="acc-class-body">
        <div class="form-grid">
          <div class="form-group">
            <label class="form-label">Catégorie</label>
            <select class="form-input" id="edit-cat"></select>
          </div>
          <div class="form-group">
            <label class="form-label">Priorité</label>
            <div class="seg-group" id="edit-prio-seg">
              <button class="seg-btn" onclick="setPrio('edit','low',this)">🔵 Basse</button>
              <button class="seg-btn" onclick="setPrio('edit','normal',this)">Normal</button>
              <button class="seg-btn" onclick="setPrio('edit','high',this)">🟠 Haute</button>
              <button class="seg-btn" onclick="setPrio('edit','urgent',this)">🔴 Urgent</button>
            </div>
          </div>
          <div class="form-group full">
            <label class="form-label">Statut</label>
            <div class="seg-group" id="edit-status-seg">
              <button class="seg-btn" onclick="setStatus('todo',this)">📋 À faire</button>
              <button class="seg-btn stat-wip" onclick="setStatus('in_progress',this)">⚙️ En cours</button>
              <button class="seg-btn stat-done" onclick="setStatus('done',this)">✅ Terminé</button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Section 3 : Rappel & Récurrence -->
    <div class="acc" id="acc-remind">
      <div class="acc-hdr" onclick="toggleAcc('acc-remind')">
        <span class="acc-arrow" id="acc-remind-arrow">▶</span>
        <span style="color:var(--yellow)">⏰</span>
        <span>Rappel & Récurrence</span>
        <span id="acc-remind-badge" style="margin-left:auto;font-size:.72em;color:var(--text3)"></span>
      </div>
      <div class="acc-body" id="acc-remind-body">
        <div class="form-grid">
          <div class="form-group">
            <label class="form-label">📅 Date & heure du rappel</label>
            <input type="datetime-local" class="form-input" id="edit-reminder">
            <div style="display:flex;gap:6px;margin-top:4px">
              <button class="btn btn-ghost btn-sm" onclick="clearReminder()">✕ Effacer</button>
            </div>
          </div>
          <div class="form-group">
            <label class="form-label">🔁 Récurrence</label>
            <select class="form-input" id="edit-recur" onchange="toggleDays('edit')">
              <option value="">Aucune</option>
              <option value="daily">Quotidienne</option>
              <option value="weekly">Hebdomadaire</option>
              <option value="monthly">Mensuelle</option>
              <option value="yearly">Annuelle</option>
              <option value="custom">Jours spécifiques</option>
            </select>
          </div>
          <div class="form-group full" id="edit-days-wrap" style="display:none">
            <label class="form-label">Jours</label>
            <div class="days-picker" id="edit-days-picker"></div>
          </div>
        </div>
      </div>
    </div>

    <!-- Section 4 : Sous-tâches -->
    <div class="acc" id="acc-subs">
      <div class="acc-hdr" onclick="toggleAcc('acc-subs')">
        <span class="acc-arrow" id="acc-subs-arrow">▶</span>
        <span style="color:var(--green)">✅</span>
        <span>Sous-tâches</span>
        <span id="subs-count-badge" style="margin-left:auto;font-size:.72em;color:var(--text3)"></span>
      </div>
      <div class="acc-body" id="acc-subs-body">
        <div id="subs-progress-wrap" style="display:none;margin-bottom:8px">
          <div class="tc-progress">
            <div class="progress-track"><div class="progress-fill" id="subs-prog-fill" style="width:0%"></div></div>
            <div class="progress-text" id="subs-prog-text">0/0</div>
          </div>
        </div>
        <div id="subs-list"></div>
        <div class="sub-add">
          <input class="form-input" id="new-sub-input" placeholder="Ajouter une sous-tâche..." onkeydown="if(event.key==='Enter')addSub()">
          <button class="btn btn-success btn-sm" onclick="addSub()">＋</button>
          <button class="btn btn-purple btn-sm" onclick="genSubsAI()">🤖</button>
        </div>
        <div id="subs-ai-status" style="font-size:.78em;color:var(--purple);margin-top:4px"></div>
        <div id="subs-ai-box" style="display:none" class="ai-sug-box">
          <div style="font-size:.82em;font-weight:600;color:var(--purple);margin-bottom:6px">🤖 Suggestions Mistral</div>
          <div id="subs-ai-list"></div>
          <div style="display:flex;gap:6px;margin-top:8px">
            <button class="btn btn-success btn-sm" onclick="addAISubs()">✅ Ajouter la sélection</button>
            <button class="btn btn-ghost btn-sm" onclick="document.getElementById('subs-ai-box').style.display='none'">✕</button>
          </div>
        </div>
      </div>
    </div>

  </div>
  <div class="modal-footer">
    <button class="btn btn-danger btn-sm" onclick="deleteTask()">🗑 Supprimer</button>
    <button class="btn btn-warning btn-sm" onclick="archiveTask()">📦 Archiver</button>
    <div style="flex:1"></div>
    <button class="btn btn-ghost" onclick="closeEdit()">Annuler</button>
    <button class="btn btn-primary" onclick="saveEdit()">💾 Enregistrer</button>
  </div>
</div>
</div>

<!-- Modal Archives -->
<div class="overlay" id="arch-overlay" onclick="overlayClose('arch-overlay',event)">
<div class="modal" onclick="event.stopPropagation()">
  <div class="modal-hdr"><span class="modal-title">🗂 Tâches archivées</span><button class="modal-close" onclick="closeArchives()">✕</button></div>
  <div class="modal-body" id="arch-body"><div class="empty"><div class="empty-icon">📦</div><div class="empty-text">Chargement...</div></div></div>
  <div class="modal-footer"><button class="btn btn-ghost" onclick="closeArchives()">Fermer</button></div>
</div>
</div>

<!-- Modal IA -->
<div class="overlay" id="ai-overlay" onclick="overlayClose('ai-overlay',event)">
<div class="modal" onclick="event.stopPropagation()">
  <div class="modal-hdr"><span class="modal-title">🤖 Assistant IA — Mistral</span><button class="modal-close" onclick="closeAI()">✕</button></div>
  <div class="modal-body">
    <div class="form-group">
      <label class="form-label">Commande en langage naturel</label>
      <textarea class="form-input" id="ai-prompt" rows="4" placeholder="Ex: Crée une tâche urgente pour préparer la démo client vendredi 14h avec rappel jeudi 18h"></textarea>
    </div>
    <div id="ai-result" style="display:none;margin-top:10px;padding:10px;background:var(--purple2);border-radius:var(--radius2);font-size:.85em;color:var(--purple)"></div>
  </div>
  <div class="modal-footer">
    <button class="btn btn-ghost" onclick="closeAI()">Fermer</button>
    <button class="btn btn-purple" onclick="sendAI()">🤖 Envoyer à Mistral</button>
  </div>
</div>
</div>

<div class="toast" id="toast-msg"></div>

<script>
var API = window.location.origin;
var CUR_CAT = null;
var CUR_STATUS = '';
var CUR_SEARCH = '';
var CUR_VIEW = 'list';
var CUR_TASK_ID = null;
var ADD_PRIO = 'normal';
var EDIT_PRIO = 'normal';
var EDIT_STATUS = 'todo';
var ADD_DAYS = [];
var EDIT_DAYS = [];
var CATS = [];
var SEARCH_TMR = null;
var AI_SUGS = [];

var PRIO_ICON = {urgent:'🔴',high:'🟠',normal:'⚪',low:'🔵'};
var PRIO_CLASS = {urgent:'purg',high:'phig',normal:'pnor',low:'plow'};
var PRIO_LABEL = {urgent:'Urgent',high:'Haute',normal:'Normal',low:'Basse'};
var STATUS_LABEL = {todo:'À faire',in_progress:'En cours',done:'Terminé'};
var STATUS_BADGE_CLASS = {todo:'b-todo',in_progress:'b-wip',done:'b-done'};
var DAYS_FR = ['Lun','Mar','Mer','Jeu','Ven','Sam','Dim'];
var DAYS_EN = ['mon','tue','wed','thu','fri','sat','sun'];
var RECUR_LABEL = {daily:'Quotidien',weekly:'Hebdo',monthly:'Mensuel',yearly:'Annuel',custom:'Perso'};

/* ── Utils ────────────────────────────────────────────────── */
function api(path, opts) {
  opts = opts || {};
  return fetch(API + path, {
    method: opts.m || 'GET',
    headers: {'Content-Type':'application/json'},
    body: opts.b ? JSON.stringify(opts.b) : undefined
  }).then(function(r) {
    if (!r.ok) return r.json().then(function(e){ throw new Error(e.detail || r.statusText); });
    return r.json();
  });
}

function toast(msg, type) {
  var el = document.getElementById('toast-msg');
  var icons = {ok:'✅',err:'❌',info:'ℹ️'};
  el.innerHTML = (icons[type]||'') + ' ' + msg;
  el.className = 'toast show ' + (type||'ok');
  setTimeout(function(){ el.classList.remove('show'); }, 3000);
}

function esc(s) {
  return (s||'').replace(/&/g,'&amp;').replace(/</g,'<').replace(/>/g,'>');
}

function fmtDate(iso) {
  if (!iso) return '';
  var d = new Date(iso);
  return d.toLocaleString('fr-FR',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
}

function fmtDateInput(iso) {
  if (!iso) return '';
  var d = new Date(iso);
  var local = new Date(d.getTime() - d.getTimezoneOffset()*60000);
  return local.toISOString().slice(0,16);
}

/* ── Sort key ─────────────────────────────────────────────── */
function sortKey(t) {
  if (t.status === 'done') return [99,0];
  var now = new Date();
  var rem = t.reminder ? new Date(t.reminder) : null;
  var pc = {urgent:4,high:3,normal:2,low:1};
  var p = 5 - (pc[t.priority] || 2);
  if (rem) {
    if (rem < now) return [0, p];
    var d = (rem - now) / 86400000;
    if (d < 1) return [1, p];
    if (d < 7) return [2, p, d];
    return [3, p, d];
  }
  return [4, p];
}

/* ── Deadline badge ───────────────────────────────────────── */
function deadlineBadge(t) {
  if (!t.reminder) return '';
  var now = new Date();
  var rem = new Date(t.reminder);
  var d = Math.floor((rem - now) / 86400000);
  if (rem < now && t.status !== 'done') return '<span class="badge b-late">⚠ EN RETARD</span>';
  if (d === 0) return '<span class="badge b-today">🔔 AUJOURD HUI</span>';
  if (d === 1) return '<span class="badge b-tmw">📅 DEMAIN</span>';
  if (d <= 7)  return '<span class="badge b-soon">📅 J-' + d + '</span>';
  return '';
}

function catColor(name) {
  var c = CATS.find(function(x){ return x.name === name; });
  return c ? c.color : 'var(--text3)';
}

/* ── Init ─────────────────────────────────────────────────── */
function init() {
  Promise.all([loadHealth(), loadCats()]).then(function(){
    buildDayPicker('add');
    buildDayPicker('edit');
    loadTasks();
    setInterval(loadHealth, 30000);
    setInterval(function(){ if(CUR_VIEW==='list') loadTasks(); }, 60000);
  });
}

function loadHealth() {
  return api('/health').then(function(d){
    document.getElementById('sb-dot').classList.add('on');
    document.getElementById('sb-status').textContent = d.tasks + ' tâche(s)';
    document.getElementById('task-count').textContent = d.tasks + ' tâches actives';
  }).catch(function(){
    document.getElementById('sb-dot').classList.remove('on');
    document.getElementById('sb-status').textContent = 'Hors ligne';
  });
}

function loadCats() {
  return api('/categories').then(function(c){
    CATS = c;
    buildSidebar();
    buildCatSelects();
  }).catch(function(){});
}

/* ── Sidebar ──────────────────────────────────────────────── */
function buildSidebar() {
  var nav = document.getElementById('sb-nav');
  nav.innerHTML = '<div class="nav-section">Catégories</div>';
  var all = document.createElement('div');
  all.className = 'nav-item' + (CUR_CAT === null ? ' active' : '');
  all.id = 'nav-all';
  all.innerHTML = '<span>🗂</span><span>Toutes les tâches</span><span class="nav-count" id="nav-count-all">0</span>';
  all.onclick = function(){ selectCat(null, all); };
  nav.appendChild(all);
  CATS.forEach(function(c){
    var i = document.createElement('div');
    i.className = 'nav-item' + (CUR_CAT === c.id ? ' active' : '');
    i.innerHTML = '<span class="nav-dot" style="background:'+c.color+'"></span><span>'+esc(c.name)+'</span>';
    i.onclick = (function(cat,el){ return function(){ selectCat(cat.id, el); }; })(c, i);
    nav.appendChild(i);
  });
}

function buildCatSelects() {
  var opts = '<option value="">Aucune</option>' + CATS.map(function(c){
    return '<option value="'+esc(c.name)+'">'+esc(c.name)+'</option>';
  }).join('');
  document.getElementById('add-cat').innerHTML = opts;
  document.getElementById('edit-cat').innerHTML = opts;
}

/* ── Navigation ───────────────────────────────────────────── */
function selectCat(id, el) {
  CUR_CAT = id;
  document.querySelectorAll('.nav-item').forEach(function(i){ i.classList.remove('active'); });
  el.classList.add('active');
  var c = CATS.find(function(x){ return x.id === id; });
  document.getElementById('view-title').textContent = c ? c.name : 'Toutes les tâches';
  loadTasks();
}

function switchView(v, el) {
  CUR_VIEW = v;
  document.getElementById('view-list').style.display = v === 'list' ? 'block' : 'none';
  document.getElementById('view-kanban').style.display = v === 'kanban' ? 'block' : 'none';
  document.getElementById('view-add').style.display = v === 'add' ? 'block' : 'none';
  document.querySelectorAll('.tab').forEach(function(t){ t.classList.remove('active'); });
  if (el) el.classList.add('active');
  if (v === 'list') loadTasks();
  if (v === 'kanban') loadKanban();
}

function setStatusFilter(s, el) {
  CUR_STATUS = s;
  document.querySelectorAll('.filter-chip').forEach(function(b){ b.classList.remove('active'); });
  if (el) el.classList.add('active');
  loadTasks();
}

function doSearch() {
  clearTimeout(SEARCH_TMR);
  SEARCH_TMR = setTimeout(function(){
    CUR_SEARCH = document.getElementById('search-input').value;
    loadTasks();
  }, 300);
}

/* ── Load tasks ───────────────────────────────────────────── */
function loadTasks() {
  if (CUR_VIEW !== 'list') return;
  var out = document.getElementById('tasks-output');
  out.innerHTML = '<div class="empty"><div class="empty-icon">⏳</div><div class="empty-text">Chargement...</div></div>';
  var url = '/tasks?include_archived=false';
  if (CUR_CAT != null) url += '&category_id=' + CUR_CAT;
  if (CUR_STATUS) url += '&status=' + CUR_STATUS;
  api(url).then(function(tasks){
    if (CUR_SEARCH) {
      var k = CUR_SEARCH.toLowerCase();
      tasks = tasks.filter(function(t){
        return (t.title||'').toLowerCase().indexOf(k) >= 0 ||
               (t.description||'').toLowerCase().indexOf(k) >= 0;
      });
    }
    tasks.sort(function(a,b){
      var ka = sortKey(a), kb = sortKey(b);
      for (var i = 0; i < Math.max(ka.length, kb.length); i++) {
        var d = (ka[i]||0) - (kb[i]||0);
        if (d !== 0) return d;
      }
      return 0;
    });
    var cnt = document.getElementById('nav-count-all');
    if (cnt) cnt.textContent = tasks.length;
    if (!tasks.length) {
      out.innerHTML = '<div class="empty">' +
        '<div class="empty-icon">🎉</div>' +
        '<div class="empty-text">' + (CUR_CAT != null ? 'Aucune tâche dans cette catégorie' : 'Aucune tâche !') + '</div>' +
        '<div class="empty-sub">' + (CUR_CAT != null ? 'Les tâches sans catégorie sont dans "Toutes"' : 'Cliquez + Nouvelle tâche pour commencer') + '</div>' +
        '</div>';
      return;
    }
    /* Groupement */
    var groups = {};
    tasks.forEach(function(t){
      var k = sortKey(t)[0];
      if (!groups[k]) groups[k] = [];
      groups[k].push(t);
    });
    var GROUP_INFO = {
      0: ['⚠️ En retard', 'var(--red)'],
      1: ['🔔 Aujourd hui', 'var(--orange)'],
      2: ['📅 Cette semaine', 'var(--yellow)'],
      3: ['🗓️ Prochainement', 'var(--blue)'],
      4: ['📋 Sans échéance', 'var(--text3)'],
      99:['✅ Terminées', 'var(--green)']
    };
    var html = '';
    [0,1,2,3,4,99].forEach(function(g){
      var gr = groups[g];
      if (!gr || !gr.length) return;
      var info = GROUP_INFO[g];
      html += '<div class="group-hdr">' +
        '<div class="group-line" style="background:'+info[1]+'"></div>' +
        '<span class="group-label" style="color:'+info[1]+';background:'+info[1]+'22">'+info[0]+'</span>' +
        '<div class="group-line" style="background:'+info[1]+'"></div>' +
        '</div>';
      gr.forEach(function(t){ html += renderCard(t); });
    });
    out.innerHTML = html;
  }).catch(function(e){
    out.innerHTML = '<div class="empty"><div class="empty-icon">❌</div><div class="empty-text">Erreur : '+esc(e.message)+'</div></div>';
  });
}

/* ── Render task card (vue condensée) ─────────────────────── */
function renderCard(t) {
  var pclass = PRIO_CLASS[t.priority] || 'pnor';
  if (t.status === 'done') pclass = 'pdone';
  var sbadge = '<span class="badge ' + (STATUS_BADGE_CLASS[t.status]||'b-todo') + '">' + (STATUS_LABEL[t.status]||t.status) + '</span>';
  var dbadge = deadlineBadge(t);
  var rbadge = (t.recurrence && t.recurrence !== '') ? '<span class="badge b-rec">🔁 ' + (RECUR_LABEL[t.recurrence]||t.recurrence) + '</span>' : '';
  var picon = PRIO_ICON[t.priority] || '';
  /* Meta : catégorie + rappel */
  var meta = '';
  if (t.category) meta += '<span class="tc-cat"><span class="tc-cat-dot" style="background:'+catColor(t.category)+'"></span>' + esc(t.category) + '</span>';
  if (t.reminder) {
    var remClass = 'reminder-badge';
    var now = new Date(), rem = new Date(t.reminder);
    var diff = (rem - now) / 86400000;
    if (rem < now && t.status !== 'done') remClass += ' late';
    else if (diff < 1) remClass += ' today';
    else if (diff < 7) remClass += ' soon';
    meta += '<span class="' + remClass + '">⏰ ' + fmtDate(t.reminder) + '</span>';
  }
  if (t.recurrence && t.recurrence !== '') {
    meta += '<span style="font-size:.72em;color:var(--purple)">🔁 ' + (RECUR_LABEL[t.recurrence]||t.recurrence) + '</span>';
  }
  /* Description courte */
  var desc = t.description ? '<div class="tc-desc">' + esc(t.description.substring(0,120)) + '</div>' : '';
  /* Progress */
  var prog = '';
  if (t.subtask_count > 0) {
    var pct = Math.round(t.subtask_done / t.subtask_count * 100);
    var pfill = t.subtask_done === t.subtask_count ? 'var(--green)' : 'var(--blue)';
    prog = '<div class="tc-progress">' +
      '<div class="progress-track"><div class="progress-fill" style="width:'+pct+'%;background:'+pfill+'"></div></div>' +
      '<div class="progress-text">'+t.subtask_done+'/'+t.subtask_count+'</div>' +
      '</div>';
  }
  return '<div class="task-card ' + pclass + '" onclick="openEdit(' + t.id + ')">' +
    '<div class="tc-main">' +
      '<div class="tc-prio">' + picon + '</div>' +
      '<div class="tc-body">' +
        '<div class="tc-row1">' +
          '<div class="tc-title">' + esc(t.title) + '</div>' +
          '<div class="tc-badges">' + dbadge + sbadge + '</div>' +
        '</div>' +
        desc +
        '<div class="tc-meta">' + meta + '</div>' +
        prog +
      '</div>' +
    '</div>' +
    '</div>';
}

/* ── Kanban ───────────────────────────────────────────────── */
function loadKanban() {
  var board = document.getElementById('kanban-board');
  board.innerHTML = '<div class="empty"><div class="empty-icon">⏳</div><div class="empty-text">Chargement...</div></div>';
  api('/tasks').then(function(tasks){
    if (CUR_CAT != null) {
      var c = CATS.find(function(x){ return x.id === CUR_CAT; });
      if (c) tasks = tasks.filter(function(t){ return t.category === c.name; });
    }
    board.innerHTML = '';
    var cols = [
      ['todo', '📋 À faire', 'var(--text3)'],
      ['in_progress', '⚙️ En cours', 'var(--orange)'],
      ['done', '✅ Terminé', 'var(--green)']
    ];
    cols.forEach(function(col){
      var s = col[0], l = col[1], cl = col[2];
      var ts = tasks.filter(function(t){ return t.status === s; });
      var colEl = document.createElement('div');
      colEl.className = 'k-col';
      colEl.innerHTML = '<div class="k-col-hdr">' +
        '<span class="k-col-title" style="color:'+cl+'">' + l + '</span>' +
        '<span class="k-col-count">' + ts.length + '</span>' +
        '</div>' +
        '<div class="k-col-body" id="kb-' + s + '"></div>';
      board.appendChild(colEl);
      var body = colEl.querySelector('.k-col-body');
      ts.forEach(function(t){
        var card = document.createElement('div');
        card.className = 'task-card ' + (PRIO_CLASS[t.priority]||'pnor');
        card.style.marginBottom = '6px';
        card.style.borderLeftColor = s==='done' ? 'var(--green)' : (s==='in_progress' ? 'var(--orange)' : 'var(--blue)');
        var prev = s !== 'todo' ? '<button class="btn btn-ghost btn-sm" onclick="event.stopPropagation();moveTask('+t.id+','+(s==='done'?'\'in_progress\'':'\'todo\'')+')">&larr;</button>' : '';
        var next = s !== 'done' ? '<button class="btn btn-primary btn-sm" onclick="event.stopPropagation();moveTask('+t.id+','+(s==='todo'?'\'in_progress\'':'\'done\'')+')">&rarr;</button>' : '';
        var prog = t.subtask_count > 0 ?
          '<div class="tc-progress" style="margin-top:4px"><div class="progress-track"><div class="progress-fill" style="width:'+Math.round(t.subtask_done/t.subtask_count*100)+'%;background:'+(t.subtask_done===t.subtask_count?'var(--green)':'var(--blue)')+'"></div></div><div class="progress-text">'+t.subtask_done+'/'+t.subtask_count+'</div></div>' : '';
        card.innerHTML = '<div class="tc-main">' +
          '<div class="tc-prio">' + (PRIO_ICON[t.priority]||'') + '</div>' +
          '<div class="tc-body">' +
            '<div class="tc-title">' + esc(t.title) + '</div>' +
            '<div class="tc-meta" style="margin-top:3px">' + (t.category?'<span>'+esc(t.category)+'</span>':'') + deadlineBadge(t) + '</div>' +
            prog +
            '<div style="display:flex;gap:4px;margin-top:6px">'+prev+next+'<button class="btn btn-ghost btn-sm" style="margin-left:auto" onclick="event.stopPropagation();openEdit('+t.id+')">✏</button></div>' +
          '</div>' +
          '</div>';
        card.onclick = function(){ openEdit(t.id); };
        body.appendChild(card);
      });
    });
  }).catch(function(e){
    board.innerHTML = '<div class="empty"><div class="empty-icon">❌</div><div class="empty-text">Erreur : '+esc(e.message)+'</div></div>';
  });
}

function moveTask(id, status) {
  api('/task/'+id, {m:'PUT', b:{status:status}}).then(function(){
    loadKanban(); loadTasks();
  });
}

/* ── Accordion ────────────────────────────────────────────── */
function toggleAcc(id) {
  var body  = document.getElementById(id + '-body');
  var arrow = document.getElementById(id + '-arrow');
  var open  = body.classList.toggle('open');
  if (arrow) arrow.classList.toggle('open', open);
}

function openAcc(id) {
  var body  = document.getElementById(id + '-body');
  var arrow = document.getElementById(id + '-arrow');
  if (!body.classList.contains('open')) {
    body.classList.add('open');
    if (arrow) arrow.classList.add('open');
  }
}

/* ── Prio / Status setters ────────────────────────────────── */
function setPrio(prefix, val, el) {
  if (prefix === 'add') ADD_PRIO = val; else EDIT_PRIO = val;
  var seg = document.getElementById(prefix + '-prio-seg');
  seg.querySelectorAll('.seg-btn').forEach(function(b){ b.classList.remove('active'); });
  el.classList.add('active');
}

function setStatus(val, el) {
  EDIT_STATUS = val;
  var seg = document.getElementById('edit-status-seg');
  seg.querySelectorAll('.seg-btn').forEach(function(b){ b.classList.remove('active'); });
  el.classList.add('active');
}

/* ── Days picker ──────────────────────────────────────────── */
function buildDayPicker(prefix) {
  var c = document.getElementById(prefix + '-days-picker');
  if (!c) return;
  c.innerHTML = '';
  DAYS_FR.forEach(function(l, i){
    var b = document.createElement('button');
    b.className = 'day-btn';
    b.textContent = l;
    b.dataset.d = DAYS_EN[i];
    b.onclick = (function(d, btn){
      return function(){
        btn.classList.toggle('active');
        var arr = prefix === 'add' ? ADD_DAYS : EDIT_DAYS;
        var x = arr.indexOf(d);
        if (x >= 0) arr.splice(x,1); else arr.push(d);
      };
    })(DAYS_EN[i], b);
    c.appendChild(b);
  });
}

function toggleDays(prefix) {
  var val  = document.getElementById(prefix + '-recur').value;
  var wrap = document.getElementById(prefix + '-days-wrap');
  if (wrap) wrap.style.display = val === 'custom' ? 'block' : 'none';
}

function clearReminder() {
  document.getElementById('edit-reminder').value = '';
}

/* ── Open edit ────────────────────────────────────────────── */
function openEdit(id) {
  CUR_TASK_ID = id;
  api('/task/'+id).then(function(t){
    document.getElementById('edit-modal-title').textContent = '✏️ ' + t.title;
    document.getElementById('edit-title').value = t.title || '';
    document.getElementById('edit-desc').value  = t.description || '';
    /* Catégorie */
    var sel = document.getElementById('edit-cat');
    for (var i=0; i<sel.options.length; i++) {
      if (sel.options[i].value === t.category) { sel.selectedIndex = i; break; }
    }
    /* Priorité */
    EDIT_PRIO = t.priority || 'normal';
    var pmap = {low:'🔵 Basse',normal:'Normal',high:'🟠 Haute',urgent:'🔴 Urgent'};
    document.getElementById('edit-prio-seg').querySelectorAll('.seg-btn').forEach(function(b){
      b.classList.toggle('active', b.textContent.trim() === (pmap[EDIT_PRIO]||'Normal'));
    });
    /* Statut */
    EDIT_STATUS = t.status || 'todo';
    var smap = {todo:'📋 À faire',in_progress:'⚙️ En cours',done:'✅ Terminé'};
    document.getElementById('edit-status-seg').querySelectorAll('.seg-btn').forEach(function(b){
      b.classList.toggle('active', b.textContent.trim() === smap[EDIT_STATUS]);
    });
    /* Rappel */
    document.getElementById('edit-reminder').value = t.reminder ? fmtDateInput(t.reminder) : '';
    /* Badge rappel dans accordéon */
    var rb = document.getElementById('acc-remind-badge');
    if (rb) rb.textContent = t.reminder ? fmtDate(t.reminder) : '';
    /* Récurrence */
    document.getElementById('edit-recur').value = t.recurrence || '';
    EDIT_DAYS = [];
    if (t.recurrence === 'custom' && t.recurrence_days) {
      try { EDIT_DAYS = JSON.parse(t.recurrence_days); } catch(e){}
    }
    toggleDays('edit');
    document.getElementById('edit-days-picker').querySelectorAll('.day-btn').forEach(function(b){
      b.classList.toggle('active', EDIT_DAYS.indexOf(b.dataset.d) >= 0);
    });
    /* Ouvrir rappel si données */
    if (t.reminder || (t.recurrence && t.recurrence !== '')) openAcc('acc-remind');
    /* Sous-tâches */
    renderSubs(t.subtasks || []);
    /* Badge subs */
    var sb = document.getElementById('acc-subs-arrow');
    if (sb) sb.classList.remove('open');
    /* Ouvrir subs si des données */
    if (t.subtasks && t.subtasks.length > 0) openAcc('acc-subs');
    document.getElementById('edit-overlay').classList.add('open');
    document.getElementById('edit-title').focus();
  }).catch(function(e){ toast('Erreur : ' + e.message, 'err'); });
}

function closeEdit() {
  document.getElementById('edit-overlay').classList.remove('open');
  CUR_TASK_ID = null;
  loadTasks();
  if (CUR_VIEW === 'kanban') loadKanban();
}

function overlayClose(id, e) {
  if (e.target === document.getElementById(id)) {
    document.getElementById(id).classList.remove('open');
    if (id === 'edit-overlay') { CUR_TASK_ID = null; loadTasks(); }
  }
}

/* ── Save edit ────────────────────────────────────────────── */
function saveEdit() {
  if (!CUR_TASK_ID) return;
  var ti = document.getElementById('edit-title').value.trim();
  if (!ti) { toast('Titre obligatoire !', 'err'); return; }
  var rv  = document.getElementById('edit-reminder').value;
  var rec = document.getElementById('edit-recur').value;
  api('/task/'+CUR_TASK_ID, {m:'PUT', b:{
    title:       ti,
    description: document.getElementById('edit-desc').value,
    category:    document.getElementById('edit-cat').value,
    priority:    EDIT_PRIO,
    status:      EDIT_STATUS
  }}).then(function(){
    return api('/task/'+CUR_TASK_ID+'/reminder', {m:'PUT', b:{reminder: rv ? rv+':00' : null}});
  }).then(function(){
    return api('/task/'+CUR_TASK_ID+'/recurrence', {m:'PUT', b:{
      recurrence:      rec || 'none',
      recurrence_days: rec === 'custom' ? JSON.stringify(EDIT_DAYS) : null
    }});
  }).then(function(){
    toast('Tâche mise à jour !', 'ok');
    closeEdit();
  }).catch(function(e){ toast('Erreur : ' + e.message, 'err'); });
}

/* ── Create task ──────────────────────────────────────────── */
function createTask() {
  var ti  = document.getElementById('add-title').value.trim();
  var msg = document.getElementById('add-msg');
  if (!ti) { msg.textContent = 'Titre obligatoire !'; return; }
  var rv  = document.getElementById('add-reminder').value;
  var rec = document.getElementById('add-recur').value;
  api('/task', {m:'POST', b:{
    title:       ti,
    description: document.getElementById('add-desc').value,
    category:    document.getElementById('add-cat').value,
    priority:    ADD_PRIO,
    reminder:    rv ? rv+':00' : null
  }}).then(function(t){
    if (rec) {
      return api('/task/'+t.id+'/recurrence', {m:'PUT', b:{
        recurrence: rec,
        recurrence_days: rec==='custom' ? JSON.stringify(ADD_DAYS) : null
      }}).then(function(){ return t; });
    }
    return t;
  }).then(function(){
    toast('Tâche créée !', 'ok');
    document.getElementById('add-title').value = '';
    document.getElementById('add-desc').value  = '';
    document.getElementById('add-reminder').value = '';
    document.getElementById('add-recur').value = '';
    ADD_PRIO = 'normal';
    document.getElementById('add-prio-seg').querySelectorAll('.seg-btn').forEach(function(b,i){ b.classList.toggle('active',i===1); });
    msg.textContent = '';
    switchView('list');
  }).catch(function(e){ msg.textContent = 'Erreur : ' + e.message; });
}

function openNew() {
  switchView('add');
  document.querySelectorAll('.tab').forEach(function(t,i){ t.classList.toggle('active',i===2); });
}

/* ── Delete / Archive ─────────────────────────────────────── */
function deleteTask() {
  if (!CUR_TASK_ID || !confirm('Supprimer définitivement cette tâche ?')) return;
  api('/task/'+CUR_TASK_ID, {m:'DELETE'}).then(function(){
    toast('Tâche supprimée', 'ok'); closeEdit();
  }).catch(function(e){ toast(e.message, 'err'); });
}

function archiveTask() {
  if (!CUR_TASK_ID) return;
  api('/task/'+CUR_TASK_ID+'/archive', {m:'POST'}).then(function(){
    toast('Tâche archivée', 'ok'); closeEdit();
  }).catch(function(e){ toast(e.message, 'err'); });
}

function archDone() {
  if (!confirm('Archiver toutes les tâches terminées ?')) return;
  api('/tasks/archive-done', {m:'POST'}).then(function(d){
    toast(d.archived + ' tâche(s) archivée(s)', 'ok'); loadTasks();
  }).catch(function(e){ toast(e.message, 'err'); });
}

function delDone() {
  if (!confirm('Supprimer définitivement toutes les tâches terminées ?')) return;
  api('/tasks/delete-done', {m:'DELETE'}).then(function(d){
    toast(d.deleted + ' tâche(s) supprimée(s)', 'ok'); loadTasks();
  }).catch(function(e){ toast(e.message, 'err'); });
}

/* ── Archives ─────────────────────────────────────────────── */
function openArchives() {
  document.getElementById('arch-overlay').classList.add('open');
  var body = document.getElementById('arch-body');
  body.innerHTML = '<div class="empty"><div class="empty-icon">⏳</div></div>';
  api('/tasks/archived').then(function(tasks){
    if (!tasks.length) {
      body.innerHTML = '<div class="empty"><div class="empty-icon">📭</div><div class="empty-text">Aucune tâche archivée</div></div>';
      return;
    }
    body.innerHTML = tasks.map(function(t){
      return '<div style="display:flex;align-items:center;gap:8px;padding:8px;background:var(--bg3);border-radius:var(--radius2);margin-bottom:6px">' +
        '<div style="flex:1"><div style="font-weight:600;font-size:.88em">'+esc(t.title)+'</div>' +
        '<div style="font-size:.72em;color:var(--text3)">'+esc(t.category||'')+' '+(t.updated ? '— '+new Date(t.updated).toLocaleDateString('fr-FR') : '')+'</div></div>' +
        '<button class="btn btn-success btn-sm" onclick="restoreTask('+t.id+')">↩ Restaurer</button>' +
        '<button class="btn btn-danger btn-sm" onclick="deleteArchived('+t.id+')">✕</button>' +
        '</div>';
    }).join('');
  }).catch(function(e){ body.innerHTML = '<div class="empty"><div class="empty-text">Erreur : '+esc(e.message)+'</div></div>'; });
}

function closeArchives() { document.getElementById('arch-overlay').classList.remove('open'); }

function restoreTask(id) {
  api('/task/'+id+'/unarchive', {m:'POST'}).then(function(){
    toast('Tâche restaurée !', 'ok'); openArchives(); loadTasks();
  });
}

function deleteArchived(id) {
  if (!confirm('Supprimer ?')) return;
  api('/task/'+id, {m:'DELETE'}).then(function(){
    toast('Supprimée', 'ok'); openArchives();
  });
}

/* ── Subtasks ─────────────────────────────────────────────── */
function renderSubs(subs) {
  var el   = document.getElementById('subs-list');
  var pb   = document.getElementById('subs-progress-wrap');
  var fill = document.getElementById('subs-prog-fill');
  var txt  = document.getElementById('subs-prog-text');
  var badge= document.getElementById('subs-count-badge');
  var done = subs.filter(function(s){ return s.done; }).length;
  var tot  = subs.length;
  if (tot > 0) {
    var pct = Math.round(done/tot*100);
    fill.style.width = pct + '%';
    fill.style.background = done===tot ? 'var(--green)' : 'var(--blue)';
    txt.textContent = done + '/' + tot;
    pb.style.display = 'block';
    badge.textContent = done + '/' + tot;
  } else {
    pb.style.display = 'none';
    badge.textContent = '';
  }
  el.innerHTML = tot ? subs.map(function(s){
    return '<div class="sub-item">' +
      '<input type="checkbox" class="sub-cb" ' + (s.done?'checked':'') + ' onchange="toggleSub('+s.id+')">' +
      '<span class="sub-text ' + (s.done?'done':'') + '">' + esc(s.title) + '</span>' +
      '<button class="sub-del" onclick="deleteSub('+s.id+')">✕</button>' +
      '</div>';
  }).join('') : '<div style="color:var(--text3);font-size:.82em;padding:4px 0">Aucune sous-tâche.</div>';
}

function toggleSub(sid) {
  if (!CUR_TASK_ID) return;
  api('/task/'+CUR_TASK_ID+'/subtask/'+sid+'/toggle', {m:'POST'}).then(function(){
    api('/task/'+CUR_TASK_ID).then(function(t){ renderSubs(t.subtasks||[]); });
  });
}

function deleteSub(sid) {
  if (!CUR_TASK_ID) return;
  api('/task/'+CUR_TASK_ID+'/subtask/'+sid, {m:'DELETE'}).then(function(){
    api('/task/'+CUR_TASK_ID).then(function(t){ renderSubs(t.subtasks||[]); });
  });
}

function addSub() {
  if (!CUR_TASK_ID) return;
  var inp = document.getElementById('new-sub-input');
  var ti  = inp.value.trim();
  if (!ti) return;
  api('/task/'+CUR_TASK_ID+'/subtask', {m:'POST', b:{title:ti}}).then(function(){
    inp.value = '';
    api('/task/'+CUR_TASK_ID).then(function(t){ renderSubs(t.subtasks||[]); });
  }).catch(function(){ toast('Limite 10 sous-tâches', 'err'); });
}

function genSubsAI() {
  if (!CUR_TASK_ID) return;
  var tt  = document.getElementById('edit-title').value;
  var td  = document.getElementById('edit-desc').value;
  var st  = document.getElementById('subs-ai-status');
  st.textContent = '🤖 Génération en cours...';
  document.getElementById('subs-ai-box').style.display = 'none';
  api('/task/'+CUR_TASK_ID+'/subtasks/ai', {m:'POST', b:{task_title:tt, task_desc:td}}).then(function(d){
    AI_SUGS = d.suggestions || [];
    if (!AI_SUGS.length) { st.textContent = 'Aucune suggestion générée.'; return; }
    st.textContent = '';
    document.getElementById('subs-ai-list').innerHTML = AI_SUGS.map(function(s,i){
      return '<div class="ai-sug-item"><input type="checkbox" id="aisg'+i+'" checked style="accent-color:var(--purple)"><label for="aisg'+i+'" class="ai-sug-label">' + esc(s) + '</label></div>';
    }).join('');
    document.getElementById('subs-ai-box').style.display = 'block';
    openAcc('acc-subs');
  }).catch(function(e){ st.textContent = 'Erreur : ' + e.message; });
}

function addAISubs() {
  var promises = [];
  for (var i=0; i<AI_SUGS.length; i++) {
    var cb = document.getElementById('aisg'+i);
    if (cb && cb.checked) {
      (function(title){ promises.push(api('/task/'+CUR_TASK_ID+'/subtask', {m:'POST', b:{title:title}}).catch(function(){})); })(AI_SUGS[i]);
    }
  }
  Promise.all(promises).then(function(){
    document.getElementById('subs-ai-box').style.display = 'none';
    document.getElementById('subs-ai-status').textContent = '';
    api('/task/'+CUR_TASK_ID).then(function(t){ renderSubs(t.subtasks||[]); });
  });
}

/* ── IA ───────────────────────────────────────────────────── */
function openAI() { document.getElementById('ai-overlay').classList.add('open'); }
function closeAI() { document.getElementById('ai-overlay').classList.remove('open'); }

function sendAI() {
  var tx  = document.getElementById('ai-prompt').value.trim();
  var res = document.getElementById('ai-result');
  if (!tx) return;
  res.style.display = 'block';
  res.textContent = '🤖 Mistral analyse votre demande...';
  api('/task/ai', {m:'POST', b:{text:tx}}).then(function(d){
    res.textContent = d.result;
    loadTasks();
    toast('Commande IA traitée !', 'ok');
  }).catch(function(e){ res.textContent = 'Erreur : ' + e.message; });
}

/* ── Keyboard ─────────────────────────────────────────────── */
document.addEventListener('keydown', function(e){
  if (e.key === 'Escape') {
    closeEdit();
    closeArchives();
    closeAI();
    document.getElementById('ai-overlay').classList.remove('open');
  }
  if ((e.ctrlKey || e.metaKey) && e.key === 'n') { e.preventDefault(); openNew(); }
});

/* ── Start ────────────────────────────────────────────────── */
init();
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def web_ui():
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
        app, host="0.0.0.0", port=port,
        log_level="warning", access_log=False)
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
