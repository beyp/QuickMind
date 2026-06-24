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
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>QuickMind</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,sans-serif;background:#1a1a2e;color:#e0e0e0;min-height:100vh}
.app{display:flex;height:100vh;overflow:hidden}
.sidebar{width:190px;background:#16213e;border-right:1px solid #0f3460;display:flex;flex-direction:column}
.sbh{padding:12px 10px 8px;border-bottom:1px solid #0f3460}
.sbt{color:#1E90FF;font-size:1em;font-weight:bold}
.sbs{color:#555;font-size:.72em;margin-top:2px}
.sbn{flex:1;overflow-y:auto;padding:6px 0}
.ni{padding:7px 10px;cursor:pointer;font-size:.85em;display:flex;align-items:center;gap:7px;color:#aaa;border-left:3px solid transparent}
.ni:hover{background:#0f3460;color:#e0e0e0}
.ni.active{background:#1E90FF22;color:#1E90FF;border-left-color:#1E90FF;font-weight:bold}
.nd{width:9px;height:9px;border-radius:50%}
.nc{margin-left:auto;font-size:.7em;background:#0f3460;padding:1px 5px;border-radius:8px}
.main{flex:1;display:flex;flex-direction:column;overflow:hidden;min-width:0}
.tb{padding:8px 12px;background:#16213e;border-bottom:1px solid #0f3460;display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.tbt{color:#1E90FF;font-weight:bold;font-size:.9em}
.hd{width:7px;height:7px;border-radius:50%;background:#555}
.hd.on{background:#32CD32}
.tabs{display:flex;background:#16213e;border-bottom:1px solid #0f3460}
.tab{padding:7px 12px;cursor:pointer;font-size:.82em;color:#888;border-bottom:2px solid transparent;white-space:nowrap}
.tab.active{color:#1E90FF;border-bottom-color:#1E90FF}
.content{flex:1;overflow-y:auto;padding:10px}
.fs{display:flex;gap:5px;margin-bottom:8px;flex-wrap:wrap}
.fb{padding:4px 9px;border-radius:14px;border:1px solid #0f3460;cursor:pointer;font-size:.78em;background:#0f3460;color:#888}
.fb.active{background:#1E90FF;color:#fff;border-color:#1E90FF}
.sr{display:flex;gap:6px;margin-bottom:8px}
.sr input{flex:1;padding:6px 10px;border-radius:6px;border:1px solid #0f3460;background:#0f3460;color:#e0e0e0;font-size:.85em;outline:none}
.gh{display:flex;align-items:center;gap:8px;margin:10px 0 5px;font-size:.78em;font-weight:bold}
.gl{flex:1;height:1px}
.tc{background:#16213e;border-radius:8px;padding:9px 11px;margin-bottom:7px;border-left:3px solid #1E90FF;cursor:pointer}
.tc:hover{background:#1a2a4a}
.th{display:flex;justify-content:space-between;align-items:flex-start;gap:6px}
.tt{font-weight:bold;font-size:.9em;flex:1}
.bgs{display:flex;gap:3px;flex-wrap:wrap}
.bg{padding:2px 6px;border-radius:10px;font-size:.68em;font-weight:bold}
.btd{background:#333;color:#aaa}.bwp{background:#3a2a00;color:#FF8C00}.bdn{background:#1a3a1a;color:#32CD32}
.bov{background:#3a0000;color:#FF4444}.bto{background:#3a2000;color:#FF8C00}.btm{background:#3a3a00;color:#FFD700}
.bsn{background:#1a2a1a;color:#32CD32}.brc{background:#2a1a3a;color:#9370DB}
.tm{font-size:.73em;color:#666;margin-top:3px;display:flex;gap:7px;flex-wrap:wrap}
.td{font-size:.78em;color:#666;margin-top:3px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.pb{height:4px;background:#0f3460;border-radius:2px;margin-top:4px;overflow:hidden}
.pf{height:100%;border-radius:2px}
.kanban{display:flex;gap:10px;height:calc(100%-10px);overflow-x:auto}
.kcol{min-width:260px;flex:1;background:#16213e;border-radius:8px;display:flex;flex-direction:column;max-height:100%;overflow:hidden}
.kch{padding:9px 11px;font-weight:bold;font-size:.85em;border-bottom:1px solid #0f3460;display:flex;justify-content:space-between}
.kcb{flex:1;overflow-y:auto;padding:7px}
.btn{padding:6px 12px;border-radius:6px;border:none;cursor:pointer;font-size:.82em;font-weight:bold}
.bp{background:#1E90FF;color:#fff}.bs{background:#2a5a2a;color:#32CD32}.bda{background:#5a1a1a;color:#FF4444}
.bo{background:#3a2a00;color:#FF8C00}.bpu{background:#2a1a3a;color:#9370DB}.bg2{background:#333;color:#aaa}
.bsm{padding:3px 7px;font-size:.76em;border-radius:4px}
.ov{position:fixed;inset:0;background:rgba(0,0,0,.75);z-index:200;display:none;overflow-y:auto}
.ov.open{display:block}
.modal{background:#16213e;border-radius:10px;margin:15px auto;max-width:580px;border:1px solid #1E90FF;overflow:hidden}
.mh{padding:12px 16px;background:#1a2a4a;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #0f3460}
.mt{color:#1E90FF;font-weight:bold;font-size:.95em}
.mc{background:none;border:none;color:#888;font-size:1.2em;cursor:pointer}
.mb{padding:14px 16px;max-height:62vh;overflow-y:auto}
.mf{padding:10px 16px;background:#1a2a4a;border-top:1px solid #0f3460;display:flex;gap:7px;justify-content:flex-end}
.acc{border:1px solid #0f3460;border-radius:6px;margin-bottom:7px;overflow:hidden}
.ach{padding:7px 11px;background:#0f3460;cursor:pointer;display:flex;align-items:center;gap:7px;font-size:.85em;font-weight:bold}
.ach:hover{background:#1a3460}
.acr{font-size:.75em}
.acb{padding:11px;display:none}
.acb.open{display:block}
.fg{margin-bottom:9px}
.fl{display:block;font-size:.78em;color:#aaa;margin-bottom:3px}
.fr{display:flex;gap:9px}
.fr .fg{flex:1}
input,textarea,select{width:100%;padding:7px 9px;border-radius:6px;border:1px solid #0f3460;background:#0f3460;color:#e0e0e0;font-size:.88em;outline:none;-webkit-appearance:none}
input:focus,textarea:focus,select:focus{border-color:#1E90FF}
textarea{resize:vertical;min-height:55px}
.sg{display:flex;border-radius:6px;overflow:hidden;border:1px solid #0f3460}
.sb{flex:1;padding:6px 3px;border:none;background:#0f3460;color:#888;cursor:pointer;font-size:.76em;font-weight:bold;text-align:center}
.sb.active{background:#1E90FF;color:#fff}
.si{display:flex;align-items:center;gap:7px;padding:5px 0;border-bottom:1px solid #0f3460}
.si:last-child{border-bottom:none}
.sc{width:15px;height:15px;cursor:pointer;accent-color:#1E90FF}
.stt{flex:1;font-size:.86em}
.stt.dn{text-decoration:line-through;color:#666}
.sd{background:none;border:none;color:#555;cursor:pointer;font-size:.85em}
.asr{display:flex;gap:5px;margin-top:7px}
.asr input{flex:1;margin-bottom:0}
.toast{position:fixed;bottom:18px;right:18px;padding:9px 14px;border-radius:7px;font-size:.85em;z-index:999;opacity:0;transition:opacity .3s;pointer-events:none;max-width:300px}
.toast.show{opacity:1}
.tok{background:#1a3a1a;color:#32CD32;border:1px solid #32CD32}
.ter{background:#3a1a1a;color:#FF4444;border:1px solid #FF4444}
.drow{display:flex;gap:4px;flex-wrap:wrap;margin-top:5px}
.dbtn{padding:4px 8px;border-radius:4px;border:1px solid #0f3460;background:#0f3460;color:#888;cursor:pointer;font-size:.76em}
.dbtn.active{background:#1E90FF;color:#fff;border-color:#1E90FF}
@media(max-width:600px){
.sidebar{width:100%;height:auto;border-right:none;border-bottom:1px solid #0f3460}
.app{flex-direction:column}
.sbn{display:flex;flex-direction:row;overflow-x:auto;padding:4px 0}
.ni{flex-shrink:0;padding:5px 9px;border-left:none;border-bottom:3px solid transparent}
.ni.active{border-bottom-color:#1E90FF;border-left-color:transparent}
.kanban{flex-direction:column}.kcol{min-width:auto;min-height:250px}
}
</style>
</head>
<body>
<div class="app">
<div class="sidebar">
<div class="sbh"><div class="sbt">QuickMind</div><div class="sbs" id="hsb">Connexion...</div></div>
<div class="sbn" id="snv"><div class="ni active" onclick="SC(null,this)">
<span>Toutes</span><span class="nc" id="ca0">0</span></div></div>
</div>
<div class="main">
<div class="tb">
<span class="hd" id="hdt"></span>
<span class="tbt" id="vtl">Toutes les taches</span>
<button class="btn bp bsm" onclick="ON()">+ Nouvelle</button>
<button class="btn bpu bsm" onclick="OAI()">IA</button>
<button class="btn bo bsm" onclick="AD()">Archiver termine</button>
<button class="btn bda bsm" onclick="DD()">Suppr termine</button>
<button class="btn bg2 bsm" onclick="OA()">Archives</button>
</div>
<div class="tabs">
<div class="tab active" onclick="SV('l',this)">Liste</div>
<div class="tab" onclick="SV('k',this)">Kanban</div>
<div class="tab" onclick="SV('a',this)">Ajouter</div>
</div>
<div class="content" id="ct">
<div id="vl">
<div class="fs">
<button class="fb active" onclick="SF('',this)">Toutes</button>
<button class="fb" onclick="SF('todo',this)">A faire</button>
<button class="fb" onclick="SF('in_progress',this)">En cours</button>
<button class="fb" onclick="SF('done',this)">Terminees</button>
</div>
<div class="sr"><input id="sr2" placeholder="Rechercher..." oninput="DB()"></div>
<div id="tc2">Chargement...</div>
</div>
<div id="vk" style="display:none;height:calc(100vh - 140px)"><div class="kanban" id="kb"></div></div>
<div id="va" style="display:none">
<div style="max-width:500px">
<div class="fg"><label class="fl">Titre *</label><input id="at"></div>
<div class="fr">
<div class="fg"><label class="fl">Categorie</label><select id="ac2"></select></div>
<div class="fg"><label class="fl">Priorite</label>
<div class="sg" id="apb">
<button class="sb" onclick="SPR('a','low',this)">Basse</button>
<button class="sb active" onclick="SPR('a','normal',this)">Normal</button>
<button class="sb" onclick="SPR('a','high',this)">Haute</button>
<button class="sb" onclick="SPR('a','urgent',this)">Urgent</button>
</div></div></div>
<div class="fg"><label class="fl">Description</label><textarea id="adc" rows="3"></textarea></div>
<div class="fr">
<div class="fg"><label class="fl">Rappel</label><input type="datetime-local" id="ar"></div>
<div class="fg"><label class="fl">Recurrence</label>
<select id="arc" onchange="TRD('a')">
<option value="">Aucune</option><option value="daily">Quotidienne</option>
<option value="weekly">Hebdomadaire</option><option value="monthly">Mensuelle</option>
<option value="yearly">Annuelle</option><option value="custom">Jours specifiques</option>
</select></div></div>
<div id="adr" style="display:none;margin-bottom:9px"><label class="fl">Jours</label><div class="drow" id="adys"></div></div>
<div style="display:flex;gap:7px;margin-top:10px">
<button class="btn bp" onclick="CT()">Creer</button>
<button class="btn bg2" onclick="SV('l')">Annuler</button>
</div>
<div id="ast" style="margin-top:7px;font-size:.82em;color:#FF4444"></div>
</div></div></div></div></div>
<!-- Modal Edition -->
<div class="ov" id="eov" onclick="if(event.target===this)CE()">
<div class="modal" onclick="event.stopPropagation()">
<div class="mh"><span class="mt" id="emt">Editer</span><button class="mc" onclick="CE()">X</button></div>
<div class="mb">
<div class="acc" id="a1"><div class="ach" onclick="TA('a1')"><span class="acr">v</span><span style="color:#1E90FF">Titre et Description</span></div>
<div class="acb open"><div class="fg"><label class="fl">Titre *</label><input id="et"></div><div class="fg"><label class="fl">Description</label><textarea id="ed" rows="3"></textarea></div></div></div>
<div class="acc" id="a2"><div class="ach" onclick="TA('a2')"><span class="acr">v</span><span style="color:#FF8C00">Classification</span></div>
<div class="acb open">
<div class="fr">
<div class="fg"><label class="fl">Categorie</label><select id="ec"></select></div>
<div class="fg"><label class="fl">Priorite</label><div class="sg" id="epb">
<button class="sb" onclick="SPR('e','low',this)">Basse</button>
<button class="sb" onclick="SPR('e','normal',this)">Normal</button>
<button class="sb" onclick="SPR('e','high',this)">Haute</button>
<button class="sb" onclick="SPR('e','urgent',this)">Urgent</button>
</div></div></div>
<div class="fg"><label class="fl">Statut</label><div class="sg" id="esb">
<button class="sb" onclick="SST('todo',this)">A faire</button>
<button class="sb" onclick="SST('in_progress',this)">En cours</button>
<button class="sb" onclick="SST('done',this)">Termine</button>
</div></div></div></div>
<div class="acc" id="a3"><div class="ach" onclick="TA('a3')"><span class="acr">></span><span style="color:#FFD700">Rappel et Recurrence</span></div>
<div class="acb">
<div class="fr">
<div class="fg"><label class="fl">Rappel</label><input type="datetime-local" id="er"></div>
<div class="fg"><label class="fl">Recurrence</label>
<select id="erc" onchange="TRD('e')">
<option value="">Aucune</option><option value="daily">Quotidienne</option>
<option value="weekly">Hebdomadaire</option><option value="monthly">Mensuelle</option>
<option value="yearly">Annuelle</option><option value="custom">Jours specifiques</option>
</select></div></div>
<div id="edr" style="display:none"><label class="fl">Jours</label><div class="drow" id="edys"></div></div>
</div></div>
<div class="acc" id="a4"><div class="ach" onclick="TA('a4')"><span class="acr">></span><span style="color:#32CD32">Sous-taches</span><span id="spb" style="margin-left:auto;font-size:.75em;color:#888"></span></div>
<div class="acb">
<div id="spbr" style="display:none;margin-bottom:7px"><div class="pb"><div class="pf" id="sbr"></div></div></div>
<div id="sl"></div>
<div class="asr"><input id="ns" placeholder="Nouvelle sous-tache..." onkeydown="if(event.key==='Enter')AS()">
<button class="btn bs bsm" onclick="AS()">+</button>
<button class="btn bpu bsm" onclick="GS()">IA</button></div>
<div id="sas" style="font-size:.78em;color:#9370DB;margin-top:4px"></div>
<div id="aisg" style="display:none;margin-top:7px;border:1px solid #9370DB;border-radius:6px;padding:9px">
<div style="font-size:.82em;color:#9370DB;margin-bottom:5px;font-weight:bold">Suggestions IA :</div>
<div id="aisl"></div>
<div style="display:flex;gap:5px;margin-top:7px">
<button class="btn bs bsm" onclick="AIS()">Ajouter selection</button>
<button class="btn bg2 bsm" onclick="document.getElementById('aisg').style.display='none'">X</button>
</div></div></div></div>
</div>
<div class="mf">
<button class="btn bda bsm" onclick="DCT()">Supprimer</button>
<button class="btn bo bsm" onclick="ACT()">Archiver</button>
<button class="btn bg2" onclick="CE()">Annuler</button>
<button class="btn bp" onclick="SE()">Enregistrer</button>
</div></div></div>
<!-- Modal Archives -->
<div class="ov" id="aov" onclick="if(event.target===this)CA()">
<div class="modal" onclick="event.stopPropagation()">
<div class="mh"><span class="mt">Archives</span><button class="mc" onclick="CA()">X</button></div>
<div class="mb" id="ab"></div>
<div class="mf"><button class="btn bg2" onclick="CA()">Fermer</button></div>
</div></div>
<!-- Modal IA -->
<div class="ov" id="iov" onclick="if(event.target===this)CI()">
<div class="modal" onclick="event.stopPropagation()">
<div class="mh"><span class="mt">Assistant IA Mistral</span><button class="mc" onclick="CI()">X</button></div>
<div class="mb">
<div class="fg"><label class="fl">Commande naturelle</label>
<textarea id="aip" rows="3" placeholder="Ex: Cree une tache urgente pour la demo vendredi 14h..."></textarea></div>
<div id="air" style="display:none;font-size:.83em;color:#9370DB;padding:8px;background:#0f3460;border-radius:6px;margin-top:8px"></div>
</div>
<div class="mf"><button class="btn bg2" onclick="CI()">Fermer</button><button class="btn bpu" onclick="SAI()">Envoyer a Mistral</button></div>
</div></div>
<div class="toast" id="tst"></div>
<script>
var A=window.location.origin;
var CC=null,CS='',CQ='',CV='l',TID=null,EP='normal',ES='todo',AP='normal',ARD=[],ERD=[],CATS=[],STI=null,AISG=[];
var PC={urgent:'#FF4444',high:'#FF8C00',normal:'#1E90FF',low:'#555'};
var SL={todo:'A faire',in_progress:'En cours',done:'Termine'};
var SB2={todo:'btd',in_progress:'bwp',done:'bdn'};
var DF=['Lun','Mar','Mer','Jeu','Ven','Sam','Dim'];
var DE=['mon','tue','wed','thu','fri','sat','sun'];
var RF={daily:'Quotidien',weekly:'Hebdo',monthly:'Mensuel',yearly:'Annuel',custom:'Perso'};

function F(p,o){
  o=o||{};
  return fetch(A+p,{method:o.m||'GET',headers:{'Content-Type':'application/json'},body:o.b?JSON.stringify(o.b):undefined})
  .then(function(r){
    if(!r.ok)return r.json().then(function(e){throw new Error(e.detail||r.statusText);});
    return r.json();
  });
}

function T(m,ok){
  var e=document.getElementById('tst');
  e.textContent=m;e.className='toast show '+(ok?'tok':'ter');
  setTimeout(function(){e.classList.remove('show');},3000);
}

function E(s){return(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}

function init(){
  Promise.all([CHK(),LC()]).then(function(){
    BD('a');BD('e');
    document.getElementById('arc').onchange=function(){TRD('a');};
    LT();
    setInterval(CHK,30000);
    setInterval(function(){if(CV==='l')LT();},60000);
  });
}

function CHK(){
  return F('/health').then(function(d){
    document.getElementById('hdt').classList.add('on');
    document.getElementById('hsb').textContent=d.tasks+' tache(s)';
  }).catch(function(){
    document.getElementById('hdt').classList.remove('on');
    document.getElementById('hsb').textContent='Hors ligne';
  });
}

function LC(){
  return F('/categories').then(function(c){CATS=c;BS();BCS();}).catch(function(){});
}

function BS(){
  var n=document.getElementById('snv');n.innerHTML='';
  var a=document.createElement('div');
  a.className='ni'+(CC===null?' active':'');
  a.innerHTML='<span>Toutes</span><span class="nc" id="ca0">0</span>';
  a.onclick=function(){SC(null,a);};n.appendChild(a);
  CATS.forEach(function(c){
    var i=document.createElement('div');
    i.className='ni'+(CC===c.id?' active':'');
    i.innerHTML='<span class="nd" style="background:'+c.color+';display:inline-block;margin-right:4px"></span><span>'+c.name+'</span>';
    i.onclick=(function(cat,el){return function(){SC(cat.id,el);};})(c,i);
    n.appendChild(i);
  });
}

function BCS(){
  var o='<option value="">Aucune</option>'+CATS.map(function(c){return'<option value="'+c.name+'">'+c.name+'</option>';}).join('');
  document.getElementById('ac2').innerHTML=o;
  document.getElementById('ec').innerHTML=o;
}

function BD(px){
  var c=document.getElementById(px==='a'?'adys':'edys');if(!c)return;c.innerHTML='';
  DF.forEach(function(l,i){
    var b=document.createElement('button');b.className='dbtn';b.textContent=l;b.dataset.d=DE[i];
    b.onclick=(function(d,btn){return function(){
      btn.classList.toggle('active');
      var arr=px==='a'?ARD:ERD,x=arr.indexOf(d);
      if(x>=0)arr.splice(x,1);else arr.push(d);
    };})(DE[i],b);
    c.appendChild(b);
  });
}

function TRD(px){
  var v=document.getElementById(px==='a'?'arc':'erc').value;
  var r=document.getElementById(px==='a'?'adr':'edr');
  if(r)r.style.display=v==='custom'?'block':'none';
}

function SC(id,el){
  CC=id;
  document.querySelectorAll('.ni').forEach(function(i){i.classList.remove('active');});
  el.classList.add('active');
  var c=CATS.find(function(x){return x.id===id;});
  document.getElementById('vtl').textContent=c?c.name:'Toutes les taches';
  LT();
}

function SV(v,el){
  CV=v;
  document.getElementById('vl').style.display=v==='l'?'block':'none';
  document.getElementById('vk').style.display=v==='k'?'block':'none';
  document.getElementById('va').style.display=v==='a'?'block':'none';
  document.querySelectorAll('.tab').forEach(function(t){t.classList.remove('active');});
  if(el)el.classList.add('active');
  if(v==='l')LT();if(v==='k')LK();
}

function SF(s,el){
  CS=s;
  document.querySelectorAll('.fb').forEach(function(b){b.classList.remove('active');});
  if(el)el.classList.add('active');LT();
}

function DB(){clearTimeout(STI);STI=setTimeout(function(){CQ=document.getElementById('sr2').value;LT();},300);}

function SPR(px,v,el){
  if(px==='a')AP=v;else EP=v;
  document.getElementById(px==='a'?'apb':'epb').querySelectorAll('.sb').forEach(function(b){b.classList.remove('active');});
  el.classList.add('active');
}

function SST(v,el){
  ES=v;
  document.getElementById('esb').querySelectorAll('.sb').forEach(function(b){b.classList.remove('active');});
  el.classList.add('active');
}

function GK(t){
  if(t.status==='done')return[99,0];
  var now=new Date(),rem=t.reminder?new Date(t.reminder):null;
  var pc={urgent:4,high:3,normal:2,low:1},p=5-(pc[t.priority]||2);
  if(rem){if(rem<now)return[0,p];var d=(rem-now)/86400000;if(d<1)return[1,p];if(d<7)return[2,p];return[3,p,d];}
  return[4,p];
}

function DL(t){
  if(!t.reminder)return'';
  var now=new Date(),rem=new Date(t.reminder),d=Math.floor((rem-now)/86400000);
  if(rem<now&&t.status!=='done')return'<span class="bg bov">EN RETARD</span>';
  if(d===0)return'<span class="bg bto">AUJOURD HUI</span>';
  if(d===1)return'<span class="bg btm">DEMAIN</span>';
  if(d<=7)return'<span class="bg bsn">J-'+d+'</span>';
  return'';
}

function GCC(n){var c=CATS.find(function(x){return x.name===n;});return c?c.color:'#888';}

function LT(){
  if(CV!=='l')return;
  var el=document.getElementById('tc2');
  el.innerHTML='<div style="color:#555;padding:20px">Chargement...</div>';
  var url='/tasks?include_archived=false';
  if(CC!=null)url+='&category_id='+CC;
  if(CS)url+='&status='+CS;
  F(url).then(function(tasks){
    if(CQ){var k=CQ.toLowerCase();tasks=tasks.filter(function(t){return(t.title||'').toLowerCase().indexOf(k)>=0||(t.description||'').toLowerCase().indexOf(k)>=0;});}
    tasks.sort(function(a,b){var ka=GK(a),kb=GK(b);for(var i=0;i<Math.max(ka.length,kb.length);i++){var d=(ka[i]||0)-(kb[i]||0);if(d!==0)return d;}return 0;});
    var ce=document.getElementById('ca0');if(ce)ce.textContent=tasks.length;
    if(!tasks.length){el.innerHTML='<div style="color:#555;padding:30px;text-align:center">'+(CC!=null?'Aucune tache dans cette categorie.':'Aucune tache. Cliquez + Nouvelle !')+'</div>';return;}
    var G={};tasks.forEach(function(t){var k=GK(t)[0];if(!G[k])G[k]=[];G[k].push(t);});
    var GI={0:['En retard','#FF4444'],1:["Aujourd hui",'#FF8C00'],2:['Cette semaine','#FFD700'],3:['Prochainement','#1E90FF'],4:['Sans echeance','#888'],99:['Terminees','#32CD32']};
    var h='';
    [0,1,2,3,4,99].forEach(function(g){
      var gr=G[g];if(!gr||!gr.length)return;
      var lb=GI[g][0],cl=GI[g][1];
      h+='<div class="gh"><div class="gl" style="background:'+cl+';opacity:.4"></div><span style="color:'+cl+';padding:0 7px;white-space:nowrap">'+lb+'</span><div class="gl" style="background:'+cl+';opacity:.4"></div></div>';
      gr.forEach(function(t){
        var pc2=PC[t.priority]||'#888';
        var rb=t.recurrence&&t.recurrence!==''?'<span class="bg brc">'+(RF[t.recurrence]||t.recurrence)+'</span>':'';
        var ci=t.category?'<span style="color:'+GCC(t.category)+'">'+t.category+'</span>':'';
        var ri=t.reminder?'<span>'+new Date(t.reminder).toLocaleString('fr-FR',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'})+'</span>':'';
        var pr=t.subtask_count>0?'<div style="font-size:.72em;color:#888;margin-top:3px">'+t.subtask_done+'/'+t.subtask_count+' sous-taches</div><div class="pb"><div class="pf" style="width:'+Math.round(t.subtask_done/t.subtask_count*100)+'%;background:'+(t.subtask_done===t.subtask_count?'#32CD32':'#1E90FF')+'"></div></div>':'';
        var ds=t.description?'<div class="td">'+E(t.description.substring(0,100))+'</div>':'';
        h+='<div class="tc" onclick="OE('+t.id+')" style="border-left-color:'+pc2+'"><div class="th"><div class="tt">'+E(t.title)+'</div><div class="bgs">'+DL(t)+rb+'<span class="bg '+(SB2[t.status]||'btd')+'">'+SL[t.status]+'</span></div></div>'+ds+'<div class="tm">'+ci+ri+'</div>'+pr+'</div>';
      });
    });
    el.innerHTML=h;
  }).catch(function(e){el.innerHTML='<div style="color:#FF4444;padding:20px">Erreur: '+e.message+'</div>';});
}

function LK(){
  var b=document.getElementById('kb');b.innerHTML='<div style="color:#555;padding:20px">Chargement...</div>';
  F('/tasks').then(function(tasks){
    if(CC!=null){var c=CATS.find(function(x){return x.id===CC;});if(c)tasks=tasks.filter(function(t){return t.category===c.name;});}
    b.innerHTML='';
    [['todo','A faire','#888'],['in_progress','En cours','#FF8C00'],['done','Termine','#32CD32']].forEach(function(item){
      var s=item[0],l=item[1],cl=item[2];
      var ts=tasks.filter(function(t){return t.status===s;});
      var col=document.createElement('div');col.className='kcol';
      col.innerHTML='<div class="kch"><span style="color:'+cl+'">'+l+'</span><span style="color:#555;font-size:.82em">'+ts.length+'</span></div><div class="kcb" id="kb-'+s+'"></div>';
      b.appendChild(col);
      var bd2=col.querySelector('.kcb');
      ts.forEach(function(t){
        var c2=document.createElement('div');c2.className='tc';c2.style.borderLeftColor=PC[t.priority]||'#888';c2.style.marginBottom='6px';
        var pr=t.subtask_count>0?'<div class="pb" style="margin-top:4px"><div class="pf" style="width:'+Math.round(t.subtask_done/t.subtask_count*100)+'%;background:'+(t.subtask_done===t.subtask_count?'#32CD32':'#1E90FF')+'"></div></div>':'';
        var prev=s!=='todo'?'<button class="btn bg2 bsm" onclick="MT('+t.id+','+(s==='done'?''in_progress'':''todo'')+');event.stopPropagation();">&lt;</button>':'';
        var next=s!=='done'?'<button class="btn bp bsm" onclick="MT('+t.id+','+(s==='todo'?''in_progress'':''done'')+');event.stopPropagation();">&gt;</button>':'';
        c2.innerHTML='<div style="font-weight:bold;font-size:.86em;margin-bottom:3px">'+E(t.title)+'</div><div style="font-size:.72em;color:#666">'+t.category+' '+DL(t)+'</div>'+pr+'<div style="display:flex;gap:3px;margin-top:5px">'+prev+next+'<button class="btn bg2 bsm" style="margin-left:auto" onclick="OE('+t.id+');event.stopPropagation()">Edit</button></div>';
        c2.onclick=function(){OE(t.id);};bd2.appendChild(c2);
      });
    });
  }).catch(function(e){b.innerHTML='<div style="color:#FF4444;padding:20px">Erreur: '+e.message+'</div>';});
}

function MT(id,s){F('/task/'+id,{m:'PUT',b:{status:s}}).then(function(){LK();LT();});}

function OE(id){
  TID=id;
  F('/task/'+id).then(function(t){
    document.getElementById('emt').textContent='Editer: '+t.title;
    document.getElementById('et').value=t.title||'';
    document.getElementById('ed').value=t.description||'';
    var cs=document.getElementById('ec');for(var i=0;i<cs.options.length;i++)if(cs.options[i].value===t.category){cs.selectedIndex=i;break;}
    EP=t.priority||'normal';
    var pm={low:'Basse',normal:'Normal',high:'Haute',urgent:'Urgent'};
    document.getElementById('epb').querySelectorAll('.sb').forEach(function(b){b.classList.toggle('active',b.textContent===(pm[EP]||'Normal'));});
    ES=t.status||'todo';
    var sm={todo:'A faire',in_progress:'En cours',done:'Termine'};
    document.getElementById('esb').querySelectorAll('.sb').forEach(function(b){b.classList.toggle('active',b.textContent.trim()===sm[ES]);});
    if(t.reminder){var d=new Date(t.reminder),l=new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,16);document.getElementById('er').value=l;}
    else document.getElementById('er').value='';
    document.getElementById('erc').value=t.recurrence||'';
    ERD=[];if(t.recurrence==='custom'&&t.recurrence_days){try{ERD=JSON.parse(t.recurrence_days);}catch(e){}}
    TRD('e');
    document.getElementById('edys').querySelectorAll('.dbtn').forEach(function(b){b.classList.toggle('active',ERD.indexOf(b.dataset.d)>=0);});
    if(t.reminder||t.recurrence)OAC('a3');
    RS(t.subtasks||[]);
    document.getElementById('eov').classList.add('open');
  }).catch(function(e){T('Erreur: '+e.message,false);});
}

function CE(){document.getElementById('eov').classList.remove('open');TID=null;LT();if(CV==='k')LK();}

function RS(subs){
  var el=document.getElementById('sl'),pb=document.getElementById('spb'),bar=document.getElementById('sbr'),pb2=document.getElementById('spbr');
  var done=subs.filter(function(s){return s.done;}).length,tot=subs.length;
  if(tot>0){pb.textContent=done+'/'+tot;var p=Math.round(done/tot*100);bar.style.width=p+'%';bar.style.background=done===tot?'#32CD32':'#1E90FF';pb2.style.display='block';}
  else{pb.textContent='';pb2.style.display='none';}
  el.innerHTML=tot?subs.map(function(s){return'<div class="si"><input type="checkbox" class="sc" '+(s.done?'checked':'')+' onchange="TS('+s.id+')"><span class="stt '+(s.done?'dn':'')+'" >'+E(s.title)+'</span><button class="sd" onclick="DS('+s.id+')">X</button></div>';}).join(''):'<div style="color:#555;font-size:.8em;padding:4px 0">Aucune sous-tache.</div>';
}

function TS(sid){if(!TID)return;F('/task/'+TID+'/subtask/'+sid+'/toggle',{m:'POST'}).then(function(){F('/task/'+TID).then(function(t){RS(t.subtasks||[]);});});}
function DS(sid){if(!TID)return;F('/task/'+TID+'/subtask/'+sid,{m:'DELETE'}).then(function(){F('/task/'+TID).then(function(t){RS(t.subtasks||[]);});});}

function AS(){
  if(!TID)return;var inp=document.getElementById('ns'),ti=inp.value.trim();if(!ti)return;
  F('/task/'+TID+'/subtask',{m:'POST',b:{title:ti}}).then(function(){inp.value='';F('/task/'+TID).then(function(t){RS(t.subtasks||[]);});}).catch(function(){T('Limite 10 sous-taches',false);});
}

function GS(){
  if(!TID)return;
  var tt=document.getElementById('et').value,td=document.getElementById('ed').value,st=document.getElementById('sas');
  st.textContent='IA Generation...';document.getElementById('aisg').style.display='none';
  F('/task/'+TID+'/subtasks/ai',{m:'POST',b:{task_title:tt,task_desc:td}}).then(function(d){
    AISG=d.suggestions||[];if(!AISG.length){st.textContent='Aucune suggestion.';return;}
    st.textContent='';
    document.getElementById('aisl').innerHTML=AISG.map(function(s,i){return'<div style="display:flex;align-items:center;gap:6px;padding:2px 0"><input type="checkbox" id="sg'+i+'" checked style="accent-color:#9370DB"><label for="sg'+i+'" style="font-size:.85em">'+E(s)+'</label></div>';}).join('');
    document.getElementById('aisg').style.display='block';
  }).catch(function(e){st.textContent='Erreur: '+e.message;});
}

function AIS(){
  for(var i=0;i<AISG.length;i++){var cb=document.getElementById('sg'+i);if(cb&&cb.checked){(function(t){F('/task/'+TID+'/subtask',{m:'POST',b:{title:t}}).catch(function(){});})(AISG[i]);}}
  document.getElementById('aisg').style.display='none';document.getElementById('sas').textContent='';
  setTimeout(function(){F('/task/'+TID).then(function(t){RS(t.subtasks||[]);});},500);
}

function SE(){
  if(!TID)return;
  var ti=document.getElementById('et').value.trim();if(!ti){T('Titre obligatoire !',false);return;}
  var rv=document.getElementById('er').value,rc=document.getElementById('erc').value;
  F('/task/'+TID,{m:'PUT',b:{title:ti,description:document.getElementById('ed').value,category:document.getElementById('ec').value,priority:EP,status:ES}})
  .then(function(){return F('/task/'+TID+'/reminder',{m:'PUT',b:{reminder:rv?rv+':00':null}});})
  .then(function(){return F('/task/'+TID+'/recurrence',{m:'PUT',b:{recurrence:rc||'none',recurrence_days:rc==='custom'?JSON.stringify(ERD):null}});})
  .then(function(){T('Mise a jour !',true);CE();})
  .catch(function(e){T('Erreur: '+e.message,false);});
}

function CT(){
  var ti=document.getElementById('at').value.trim(),st=document.getElementById('ast');
  if(!ti){st.textContent='Titre obligatoire !';return;}
  var rv=document.getElementById('ar').value,rc=document.getElementById('arc').value;
  F('/task',{m:'POST',b:{title:ti,description:document.getElementById('adc').value,category:document.getElementById('ac2').value,priority:AP,reminder:rv?rv+':00':null}})
  .then(function(t){
    if(rc)return F('/task/'+t.id+'/recurrence',{m:'PUT',b:{recurrence:rc,recurrence_days:rc==='custom'?JSON.stringify(ARD):null}}).then(function(){return t;});
    return t;
  })
  .then(function(){
    T('Tache creee !',true);
    document.getElementById('at').value='';document.getElementById('adc').value='';document.getElementById('ar').value='';document.getElementById('arc').value='';
    AP='normal';document.getElementById('apb').querySelectorAll('.sb').forEach(function(b,i){b.classList.toggle('active',i===1);});
    SV('l');
  }).catch(function(e){st.textContent='Erreur: '+e.message;});
}

function AD(){if(!confirm('Archiver toutes les taches terminees ?'))return;F('/tasks/archive-done',{m:'POST'}).then(function(d){T(d.archived+' archivee(s)',true);LT();});}
function DD(){if(!confirm('Supprimer definitivement les taches terminees ?'))return;F('/tasks/delete-done',{m:'DELETE'}).then(function(d){T(d.deleted+' supprimee(s)',true);LT();});}
function ACT(){if(!TID)return;F('/task/'+TID+'/archive',{m:'POST'}).then(function(){T('Archivee',true);CE();});}
function DCT(){if(!TID||!confirm('Supprimer ?'))return;F('/task/'+TID,{m:'DELETE'}).then(function(){T('Supprimee',true);CE();});}

function ON(){SV('a');document.querySelectorAll('.tab').forEach(function(t,i){t.classList.toggle('active',i===2);});}

function OA(){
  document.getElementById('aov').classList.add('open');
  var b=document.getElementById('ab');b.innerHTML='Chargement...';
  F('/tasks/archived').then(function(tasks){
    if(!tasks.length){b.innerHTML='<div style="color:#555;text-align:center;padding:20px">Aucune tache archivee.</div>';return;}
    b.innerHTML=tasks.map(function(t){return'<div style="display:flex;align-items:center;gap:7px;padding:7px;background:#0f3460;border-radius:6px;margin-bottom:5px"><div style="flex:1"><div style="font-weight:bold;font-size:.88em">'+E(t.title)+'</div><div style="font-size:.72em;color:#666">'+t.category+' '+(t.updated?'- '+new Date(t.updated).toLocaleDateString('fr-FR'):'')+'</div></div><button class="btn bs bsm" onclick="RT('+t.id+')">Restaurer</button><button class="btn bda bsm" onclick="DAT('+t.id+')">X</button></div>';}).join('');
  }).catch(function(e){b.innerHTML='Erreur: '+e.message;});
}

function RT(id){F('/task/'+id+'/unarchive',{m:'POST'}).then(function(){T('Restauree !',true);OA();LT();});}
function DAT(id){if(!confirm('Supprimer ?'))return;F('/task/'+id,{m:'DELETE'}).then(function(){T('Supprimee',true);OA();});}
function CA(){document.getElementById('aov').classList.remove('open');}

function OAI(){document.getElementById('iov').classList.add('open');}
function CI(){document.getElementById('iov').classList.remove('open');}
function SAI(){
  var tx=document.getElementById('aip').value.trim(),r=document.getElementById('air');
  if(!tx)return;r.style.display='block';r.textContent='IA analyse...';
  F('/task/ai',{m:'POST',b:{text:tx}}).then(function(d){r.textContent=d.result;LT();}).catch(function(e){r.textContent='Erreur: '+e.message;});
}

function TA(id){var b=document.querySelector('#'+id+' .acb'),a=document.querySelector('#'+id+' .acr');var o=b.classList.toggle('open');a.textContent=o?'v':'>';}
function OAC(id){var b=document.querySelector('#'+id+' .acb'),a=document.querySelector('#'+id+' .acr');if(!b.classList.contains('open')){b.classList.add('open');a.textContent='v';}}

document.addEventListener('keydown',function(e){if(e.key==='Escape'){CE();CA();CI();}});
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
