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







@app.get("/app.js")
def serve_app_js():
    """Sert le fichier JavaScript de l application."""
    from fastapi.responses import Response
    from pathlib import Path
    for p in [
        Path(__file__).parent / "app.js",
    ]:
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                js = f.read()
            return Response(content=js, media_type="application/javascript",
                headers={"Cache-Control": "no-cache"})
    return Response(content="// app.js not found", media_type="application/javascript")





class VisionRequest(BaseModel):
    prompt:           str
    image_b64:        Optional[str] = None
    image_mime:       Optional[str] = "image/png"
    default_category: Optional[str] = ""
    default_reminder: Optional[str] = None


@app.get("/groq/status")
def groq_status():
    try:
        from agents.groq_vision import is_available, _load_token
        has_key = bool(_load_token())
        avail   = is_available()
        return {
            "available": avail,
            "has_key":   has_key,
            "status":    "ok" if avail else ("no_key" if not has_key else "unreachable")
        }
    except Exception as e:
        return {"available": False, "has_key": False, "status": str(e)}


@app.post("/tasks/vision")
def create_tasks_vision(data: VisionRequest):
    try:
        from agents.groq_vision import analyze_and_generate_tasks
        from core.database import add_task, add_subtask, get_categories, init_db
        from datetime import datetime as dt
        init_db()
        cats  = get_categories()
        cmap  = {c.name.lower(): c.id for c in cats}
        res   = analyze_and_generate_tasks(
            prompt           = data.prompt,
            image_b64        = data.image_b64,
            image_mime       = data.image_mime or "image/png",
            categories       = [c.name for c in cats],
            default_category = data.default_category or "",
            default_reminder = data.default_reminder,
        )
        created = []
        for t in res.get("tasks", []):
            cname = t.get("category", data.default_category or "")
            cid   = cmap.get(cname.lower()) if cname else None
            rdt   = None
            if t.get("reminder"):
                try:
                    rdt = dt.fromisoformat(t["reminder"])
                except Exception:
                    pass
            task = add_task(
                title       = t.get("title", "Tache"),
                description = t.get("description", ""),
                category_id = cid,
                priority    = t.get("priority", "normal"),
                reminder_at = rdt,
            )
            subs = []
            for s in t.get("subtasks", [])[:8]:
                if s.strip():
                    sub = add_subtask(task.id, s.strip())
                    if sub: subs.append({"id": sub.id, "title": sub.title})
            created.append({
                "id":       task.id,
                "title":    task.title,
                "category": cname,
                "priority": task.priority,
                "reminder": task.reminder_at.isoformat() if task.reminder_at else None,
                "subtasks": subs,
            })
        _refresh_ui()
        return {
            "analysis":      res.get("analysis", ""),
            "tasks_created": len(created),
            "tasks":         created,
        }
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))



@app.get("/ai/status")
def ai_status():
    """Retourne le statut des moteurs IA disponibles."""
    status = {"groq": False, "groq_model": "", "ollama": False, "active": "none"}
    # Verifier Groq
    try:
        from agents.local_ai import _get_groq_key, _groq_available, GROQ_MODEL
        has_key = bool(_get_groq_key())
        avail   = _groq_available() if has_key else False
        status["groq"]       = avail
        status["groq_key"]   = has_key
        status["groq_model"] = GROQ_MODEL
    except Exception as e:
        status["groq_error"] = str(e)
    # Verifier Ollama
    try:
        import requests as _r
        resp = _r.get("http://localhost:11434/api/tags", timeout=3)
        status["ollama"] = resp.status_code == 200
    except Exception:
        status["ollama"] = False
    # Determiner le moteur actif
    if status["groq"]:
        status["active"] = f"groq/{status['groq_model']}"
    elif status["ollama"]:
        status["active"] = "ollama/mistral"
    return status



WEB_UI = """



<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0,maximum-scale=1.0">
<title>QuickMind</title>
<style>
:root{--bg:#0f1117;--bg2:#1a1d27;--bg3:#242838;--bg4:#2e3347;--border:#2e3347;--border2:#3d4460;--blue:#4f8ef7;--blue3:#1e3a6e;--green:#3ecf6e;--green2:#1a5c35;--orange:#f7934f;--orange2:#7a4020;--red:#f75f5f;--red2:#7a2020;--purple:#a78bfa;--purple2:#3d2a6e;--yellow:#f7d04f;--yellow2:#6e5a20;--text:#e8eaf6;--text2:#9298b5;--text3:#6b7194;--radius:10px;--radius2:6px;--shadow:0 4px 20px rgba(0,0,0,.4)}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:var(--bg);color:var(--text);min-height:100vh;font-size:14px}
::-webkit-scrollbar{width:5px}::-webkit-scrollbar-track{background:var(--bg)}::-webkit-scrollbar-thumb{background:var(--border2);border-radius:3px}
.layout{display:flex;height:100vh;overflow:hidden}
.sidebar{width:220px;background:var(--bg2);border-right:1px solid var(--border);display:flex;flex-direction:column;flex-shrink:0}
.sb-logo{padding:16px 14px 12px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:10px}
.sb-logo-icon{width:32px;height:32px;background:linear-gradient(135deg,var(--blue),var(--purple));border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:16px;flex-shrink:0}
.sb-logo-text{font-weight:700;font-size:1em}.sb-logo-sub{font-size:.7em;color:var(--text3);margin-top:1px}
.sb-status{display:flex;align-items:center;gap:5px;padding:8px 14px;font-size:.72em;color:var(--text3)}
.sb-dot{width:6px;height:6px;border-radius:50%;background:#555;flex-shrink:0;transition:background .3s}.sb-dot.on{background:var(--green)}
.sb-nav{flex:1;overflow-y:auto;padding:8px}
.nav-section{font-size:.68em;font-weight:600;color:var(--text3);padding:8px 8px 4px;text-transform:uppercase;letter-spacing:.08em}
.nav-item{display:flex;align-items:center;gap:8px;padding:7px 10px;border-radius:var(--radius2);cursor:pointer;font-size:.85em;color:var(--text2);transition:all .15s;margin-bottom:2px;border:1px solid transparent}
.nav-item:hover{background:var(--bg3);color:var(--text)}.nav-item.active{background:var(--blue3);color:var(--blue);border-color:var(--blue3)}
.nav-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}.nav-count{margin-left:auto;font-size:.72em;background:var(--bg4);padding:1px 6px;border-radius:10px;color:var(--text3)}
.nav-item.active .nav-count{background:var(--blue3);color:var(--blue)}
.main{flex:1;display:flex;flex-direction:column;overflow:hidden;min-width:0}
.topbar{padding:10px 16px;background:var(--bg2);border-bottom:1px solid var(--border);display:flex;align-items:center;gap:8px;flex-shrink:0;flex-wrap:wrap}
.tb-title{font-weight:600;font-size:.95em;margin-right:4px}.tb-spacer{flex:1}
.tabs{display:flex;background:var(--bg2);border-bottom:1px solid var(--border);padding:0 16px;flex-shrink:0}
.tab{padding:9px 14px;cursor:pointer;font-size:.82em;color:var(--text3);border-bottom:2px solid transparent;white-space:nowrap;transition:all .15s}
.tab:hover{color:var(--text)}.tab.active{color:var(--blue);border-bottom-color:var(--blue)}
.content{flex:1;overflow-y:auto;padding:14px 16px}
.filter-bar{display:flex;align-items:center;gap:6px;margin-bottom:10px;flex-wrap:wrap}
.filter-chip{padding:4px 10px;border-radius:20px;border:1px solid var(--border2);cursor:pointer;font-size:.78em;color:var(--text3);background:var(--bg2);transition:all .15s;white-space:nowrap}
.filter-chip:hover{border-color:var(--blue);color:var(--blue)}.filter-chip.active{background:var(--blue3);color:var(--blue);border-color:var(--blue3)}
.search-wrap{flex:1;min-width:160px;position:relative}
.search-wrap input{width:100%;padding:6px 10px 6px 30px;border-radius:20px;border:1px solid var(--border2);background:var(--bg3);color:var(--text);font-size:.82em;outline:none}
.search-wrap input:focus{border-color:var(--blue)}.search-icon{position:absolute;left:10px;top:50%;transform:translateY(-50%);color:var(--text3);font-size:11px;pointer-events:none}
.group-hdr{display:flex;align-items:center;gap:8px;margin:14px 0 6px}.group-hdr:first-child{margin-top:0}
.group-line{flex:1;height:1px;opacity:.3}.group-label{font-size:.72em;font-weight:600;white-space:nowrap;text-transform:uppercase;letter-spacing:.06em;padding:2px 8px;border-radius:10px}
.task-card{background:var(--bg2);border-radius:var(--radius);border:1px solid var(--border);border-left:3px solid var(--blue);margin-bottom:6px;cursor:pointer;transition:all .15s;overflow:hidden}
.task-card:hover{border-color:var(--border2);box-shadow:var(--shadow);transform:translateY(-1px)}
.task-card.purg{border-left-color:var(--red)}.task-card.phig{border-left-color:var(--orange)}.task-card.pnor{border-left-color:var(--blue)}.task-card.plow{border-left-color:var(--text3)}.task-card.pdone{border-left-color:var(--green);opacity:.75}
.tc-main{display:flex;align-items:flex-start;gap:10px;padding:10px 12px}
.tc-prio{font-size:14px;flex-shrink:0;margin-top:1px}.tc-body{flex:1;min-width:0}
.tc-row1{display:flex;align-items:flex-start;gap:6px}.tc-title{font-weight:600;font-size:.9em;flex:1;line-height:1.3}
.tc-badges{display:flex;gap:3px;flex-wrap:wrap;flex-shrink:0}
.badge{display:inline-flex;align-items:center;gap:3px;padding:2px 6px;border-radius:8px;font-size:.68em;font-weight:600;white-space:nowrap}
.b-todo{background:#1e2333;color:var(--text3)}.b-wip{background:var(--orange2);color:var(--orange)}.b-done{background:var(--green2);color:var(--green)}
.b-late{background:var(--red2);color:var(--red)}.b-today{background:var(--orange2);color:var(--orange)}.b-tmw{background:var(--yellow2);color:var(--yellow)}.b-soon{background:var(--green2);color:var(--green)}.b-rec{background:var(--purple2);color:var(--purple)}
.tc-meta{display:flex;gap:8px;margin-top:4px;font-size:.72em;color:var(--text3);flex-wrap:wrap;align-items:center}
.tc-cat{display:flex;align-items:center;gap:3px}.tc-cat-dot{width:6px;height:6px;border-radius:50%}
.tc-desc{font-size:.78em;color:var(--text3);margin-top:3px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.tc-progress{margin-top:5px;display:flex;align-items:center;gap:6px}
.progress-track{flex:1;height:3px;background:var(--bg4);border-radius:2px;overflow:hidden}.progress-fill{height:100%;border-radius:2px;transition:width .3s}.progress-text{font-size:.68em;color:var(--text3);white-space:nowrap}
.kanban-wrap{display:flex;gap:12px;height:calc(100vh - 140px);overflow-x:auto;padding-bottom:8px}
.k-col{min-width:270px;flex:1;background:var(--bg2);border-radius:var(--radius);display:flex;flex-direction:column;max-height:100%;border:1px solid var(--border)}
.k-col-hdr{padding:10px 12px;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);flex-shrink:0}
.k-col-title{font-weight:600;font-size:.85em}.k-col-count{font-size:.72em;color:var(--text3);background:var(--bg4);padding:1px 6px;border-radius:8px}
.k-col-body{flex:1;overflow-y:auto;padding:8px}
.btn{display:inline-flex;align-items:center;gap:5px;padding:6px 12px;border-radius:var(--radius2);border:none;cursor:pointer;font-size:.82em;font-weight:500;transition:all .15s;white-space:nowrap}
.btn:hover{opacity:.88;transform:translateY(-1px)}.btn:active{transform:translateY(0)}
.btn-primary{background:var(--blue);color:#fff}.btn-success{background:var(--green2);color:var(--green);border:1px solid var(--green2)}.btn-danger{background:var(--red2);color:var(--red);border:1px solid var(--red2)}.btn-warning{background:var(--orange2);color:var(--orange);border:1px solid var(--orange2)}.btn-ghost{background:var(--bg3);color:var(--text2);border:1px solid var(--border2)}.btn-purple{background:var(--purple2);color:var(--purple);border:1px solid var(--purple2)}.btn-sm{padding:4px 8px;font-size:.75em}
.overlay{position:fixed;inset:0;background:rgba(0,0,0,.65);z-index:300;display:none;overflow-y:auto;backdrop-filter:blur(4px)}
.overlay.open{display:flex;align-items:flex-start;justify-content:center;padding:20px}
.modal{background:var(--bg2);border-radius:var(--radius);border:1px solid var(--border2);width:100%;max-width:620px;box-shadow:var(--shadow);overflow:hidden}
.modal-hdr{padding:14px 18px;background:var(--bg3);border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center}
.modal-title{font-weight:600;font-size:.95em}.modal-close{background:none;border:none;color:var(--text3);font-size:1.3em;cursor:pointer;padding:2px 6px;border-radius:4px}.modal-close:hover{background:var(--bg4);color:var(--text)}
.modal-body{padding:16px 18px;max-height:68vh;overflow-y:auto}.modal-footer{padding:12px 18px;background:var(--bg3);border-top:1px solid var(--border);display:flex;gap:8px;justify-content:flex-end}
.acc{border:1px solid var(--border);border-radius:var(--radius2);margin-bottom:8px;overflow:hidden}
.acc-hdr{padding:9px 12px;background:var(--bg3);cursor:pointer;display:flex;align-items:center;gap:8px;font-size:.85em;font-weight:600;user-select:none;transition:background .15s}.acc-hdr:hover{background:var(--bg4)}
.acc-arrow{font-size:.8em;color:var(--text3);transition:transform .2s}.acc-arrow.open{transform:rotate(90deg)}
.acc-body{padding:12px;display:none}.acc-body.open{display:block}
.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}.form-group{display:flex;flex-direction:column;gap:4px}.form-group.full{grid-column:1/-1}
.form-label{font-size:.75em;color:var(--text3);font-weight:500}
.form-input{width:100%;padding:8px 10px;border-radius:var(--radius2);border:1px solid var(--border2);background:var(--bg3);color:var(--text);font-size:.88em;outline:none;transition:border .15s;-webkit-appearance:none}
.form-input:focus{border-color:var(--blue)}textarea.form-input{resize:vertical;min-height:60px}
.seg-group{display:flex;border-radius:var(--radius2);overflow:hidden;border:1px solid var(--border2)}
.seg-btn{flex:1;padding:7px 4px;border:none;background:var(--bg3);color:var(--text3);cursor:pointer;font-size:.76em;font-weight:600;text-align:center;transition:all .15s}.seg-btn:hover{background:var(--bg4);color:var(--text)}.seg-btn.active{background:var(--blue);color:#fff}.seg-btn.s-wip.active{background:var(--orange)}.seg-btn.s-done.active{background:var(--green)}
.sub-item{display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--border)}.sub-item:last-child{border-bottom:none}
.sub-cb{width:15px;height:15px;cursor:pointer;accent-color:var(--blue);flex-shrink:0}.sub-text{flex:1;font-size:.86em}.sub-text.done{text-decoration:line-through;color:var(--text3)}.sub-del{background:none;border:none;color:var(--text3);cursor:pointer;font-size:.9em;padding:0 2px}.sub-del:hover{color:var(--red)}
.sub-add{display:flex;gap:6px;margin-top:8px}.sub-add input{flex:1;margin-bottom:0}
.days-picker{display:flex;gap:4px;flex-wrap:wrap;margin-top:4px}.day-btn{padding:4px 8px;border-radius:4px;border:1px solid var(--border2);background:var(--bg3);color:var(--text3);cursor:pointer;font-size:.74em;font-weight:600;transition:all .15s}.day-btn.active{background:var(--blue);color:#fff;border-color:var(--blue)}
.reminder-badge{display:inline-flex;align-items:center;gap:3px;font-size:.72em;color:var(--text3)}.reminder-badge.late{color:var(--red)}.reminder-badge.today{color:var(--orange)}.reminder-badge.soon{color:var(--yellow)}
.toast{position:fixed;bottom:20px;right:20px;padding:10px 16px;border-radius:var(--radius);font-size:.85em;z-index:999;opacity:0;transition:all .3s;pointer-events:none;max-width:320px;box-shadow:var(--shadow);border:1px solid}
.toast.show{opacity:1;transform:translateY(-4px)}.toast.ok{background:var(--green2);color:var(--green);border-color:var(--green2)}.toast.err{background:var(--red2);color:var(--red);border-color:var(--red2)}.toast.info{background:var(--blue3);color:var(--blue);border-color:var(--blue3)}
.ai-sug-box{border:1px solid var(--purple2);border-radius:var(--radius2);padding:10px;margin-top:8px;background:rgba(167,139,250,.05)}
.empty{text-align:center;padding:40px 20px;color:var(--text3)}.empty-icon{font-size:2.5em;margin-bottom:10px;opacity:.5}.empty-text{font-size:.9em;margin-bottom:4px}.empty-sub{font-size:.78em}
@media(max-width:640px){.sidebar{width:100%;height:auto;border-right:none;border-bottom:1px solid var(--border)}.layout{flex-direction:column}.sb-nav{display:flex;flex-direction:row;overflow-x:auto;padding:4px 8px;gap:4px}.nav-section{display:none}.nav-item{flex-shrink:0;padding:5px 10px;border-left:none;border-bottom:2px solid transparent}.nav-item.active{border-bottom-color:var(--blue);background:transparent}.kanban-wrap{flex-direction:column;height:auto}.k-col{min-width:auto}.form-grid{grid-template-columns:1fr}.form-group.full{grid-column:1}}
</style>
</head>
<body>
<div class="layout">
<div class="sidebar">
  <div class="sb-logo"><div class="sb-logo-icon">&#9889;</div><div><div class="sb-logo-text">QuickMind</div><div class="sb-logo-sub" id="task-count">Chargement...</div></div></div>
  <div class="sb-status"><div class="sb-dot" id="sb-dot"></div><span id="sb-status">Connexion...</span></div>
  <div class="sb-nav" id="sb-nav"><div class="nav-section">Categories</div><div class="nav-item active" id="nav-all" onclick="QM.selCat(null,this)"><span>&#128194;</span><span>Toutes</span><span class="nav-count" id="nav-count-all">0</span></div></div>
</div>
<div class="main">
  <div class="topbar">
    <span class="tb-title" id="view-title">Toutes les taches</span><div class="tb-spacer"></div>
    <button class="btn btn-primary btn-sm" onclick="QM.openNew()">+ Nouvelle</button>
    <button class="btn btn-purple btn-sm" onclick="QM.openAI()">IA</button>
    <button class="btn btn-warning btn-sm" onclick="QM.archDone()">Archiver fini</button>
    <button class="btn btn-danger btn-sm" onclick="QM.delDone()">Suppr fini</button>
    <button class="btn btn-ghost btn-sm" onclick="QM.openArchives()">Archives</button>
    <button class="btn btn-ghost btn-sm" onclick="QM.openVision()" title="Vision IA Groq">&#128247;</button>
    <span id="sb-health-info" style="font-size:.72em;color:var(--text3);white-space:nowrap">Refresh: 30s</span>
    <button class="btn btn-ghost btn-sm" onclick="QM.openSettings()" title="Reglages">&#9881;&#65039;</button>
  </div>
  <div class="tabs">
    <div class="tab active" onclick="QM.switchView('list',this)">Liste</div>
    <div class="tab" onclick="QM.switchView('kanban',this)">Kanban</div>
    <div class="tab" onclick="QM.switchView('add',this)">Ajouter</div>
  </div>
  <div class="content" id="content">
    <div id="view-list">
      <div class="filter-bar">
        <button class="filter-chip active" onclick="QM.setStatus('',this)">Toutes</button>
        <button class="filter-chip" onclick="QM.setStatus('todo',this)">A faire</button>
        <button class="filter-chip" onclick="QM.setStatus('in_progress',this)">En cours</button>
        <button class="filter-chip" onclick="QM.setStatus('done',this)">Terminees</button>
        <div class="search-wrap"><span class="search-icon">&#128269;</span><input id="search-input" placeholder="Rechercher..." oninput="QM.doSearch()"></div>
      </div>
      <div id="tasks-output"><div class="empty"><div class="empty-icon">&#8987;</div><div class="empty-text">Chargement...</div></div></div>
    </div>
    <div id="view-kanban" style="display:none"><div class="kanban-wrap" id="kanban-board"></div></div>
    <div id="view-add" style="display:none">
      <div style="max-width:520px">
        <div class="form-grid">
          <div class="form-group full"><label class="form-label">Titre *</label><input class="form-input" id="add-title" placeholder="Titre..."></div>
          <div class="form-group"><label class="form-label">Categorie</label><select class="form-input" id="add-cat"></select></div>
          <div class="form-group"><label class="form-label">Priorite</label><div class="seg-group" id="add-prio-seg"><button class="seg-btn" onclick="QM.setPrio('add','low',this)">Basse</button><button class="seg-btn active" onclick="QM.setPrio('add','normal',this)">Normal</button><button class="seg-btn" onclick="QM.setPrio('add','high',this)">Haute</button><button class="seg-btn" onclick="QM.setPrio('add','urgent',this)">Urgent</button></div></div>
          <div class="form-group full"><label class="form-label">Description</label><textarea class="form-input" id="add-desc" rows="3"></textarea></div>
          <div class="form-group"><label class="form-label">Rappel</label><input type="datetime-local" class="form-input" id="add-reminder"></div>
          <div class="form-group"><label class="form-label">Recurrence</label><select class="form-input" id="add-recur" onchange="QM.toggleDays('add')"><option value="">Aucune</option><option value="daily">Quotidienne</option><option value="weekly">Hebdomadaire</option><option value="monthly">Mensuelle</option><option value="yearly">Annuelle</option><option value="custom">Jours specifiques</option></select></div>
          <div class="form-group full" id="add-days-wrap" style="display:none"><label class="form-label">Jours</label><div class="days-picker" id="add-days-picker"></div></div>
        </div>
        <div style="display:flex;gap:8px;margin-top:14px"><button class="btn btn-primary" onclick="QM.createTask()">Creer la tache</button><button class="btn btn-ghost" onclick="QM.switchView('list')">Annuler</button></div>
        <div id="add-msg" style="margin-top:8px;font-size:.82em;color:var(--red)"></div>
      </div>
    </div>
  </div>
</div>
</div>
<!-- Modal Edition -->
<div class="overlay" id="edit-overlay" onclick="QM.overlayClose('edit-overlay',event)">
<div class="modal" onclick="event.stopPropagation()">
  <div class="modal-hdr"><span class="modal-title" id="edit-modal-title">Editer</span><button class="modal-close" onclick="QM.closeEdit()">X</button></div>
  <div class="modal-body">
    <div class="acc" id="acc-main"><div class="acc-hdr" onclick="QM.toggleAcc('acc-main')"><span class="acc-arrow open" id="acc-main-arrow">&#9658;</span><span style="color:var(--blue)">Titre et Description</span></div><div class="acc-body open" id="acc-main-body"><div class="form-grid"><div class="form-group full"><label class="form-label">Titre *</label><input class="form-input" id="edit-title"></div><div class="form-group full"><label class="form-label">Description</label><textarea class="form-input" id="edit-desc" rows="3"></textarea></div></div></div></div>
    <div class="acc" id="acc-class"><div class="acc-hdr" onclick="QM.toggleAcc('acc-class')"><span class="acc-arrow open" id="acc-class-arrow">&#9658;</span><span style="color:var(--orange)">Classification</span></div><div class="acc-body open" id="acc-class-body"><div class="form-grid"><div class="form-group"><label class="form-label">Categorie</label><select class="form-input" id="edit-cat"></select></div><div class="form-group"><label class="form-label">Priorite</label><div class="seg-group" id="edit-prio-seg"><button class="seg-btn" onclick="QM.setPrio('edit','low',this)">Basse</button><button class="seg-btn" onclick="QM.setPrio('edit','normal',this)">Normal</button><button class="seg-btn" onclick="QM.setPrio('edit','high',this)">Haute</button><button class="seg-btn" onclick="QM.setPrio('edit','urgent',this)">Urgent</button></div></div><div class="form-group full"><label class="form-label">Statut</label><div class="seg-group" id="edit-status-seg"><button class="seg-btn" onclick="QM.setStatus2('todo',this)">A faire</button><button class="seg-btn s-wip" onclick="QM.setStatus2('in_progress',this)">En cours</button><button class="seg-btn s-done" onclick="QM.setStatus2('done',this)">Termine</button></div></div></div></div></div>
    <div class="acc" id="acc-remind"><div class="acc-hdr" onclick="QM.toggleAcc('acc-remind')"><span class="acc-arrow" id="acc-remind-arrow">&#9658;</span><span style="color:var(--yellow)">Rappel et Recurrence</span><span id="acc-remind-badge" style="margin-left:auto;font-size:.72em;color:var(--text3)"></span></div><div class="acc-body" id="acc-remind-body"><div class="form-grid"><div class="form-group"><label class="form-label">Rappel</label><input type="datetime-local" class="form-input" id="edit-reminder"><button class="btn btn-ghost btn-sm" style="margin-top:4px;width:fit-content" onclick="QM.clearReminder()">Effacer</button></div><div class="form-group"><label class="form-label">Recurrence</label><select class="form-input" id="edit-recur" onchange="QM.toggleDays('edit')"><option value="">Aucune</option><option value="daily">Quotidienne</option><option value="weekly">Hebdomadaire</option><option value="monthly">Mensuelle</option><option value="yearly">Annuelle</option><option value="custom">Jours specifiques</option></select></div><div class="form-group full" id="edit-days-wrap" style="display:none"><label class="form-label">Jours</label><div class="days-picker" id="edit-days-picker"></div></div></div></div></div>
    <div class="acc" id="acc-subs"><div class="acc-hdr" onclick="QM.toggleAcc('acc-subs')"><span class="acc-arrow" id="acc-subs-arrow">&#9658;</span><span style="color:var(--green)">Sous-taches</span><span id="subs-count-badge" style="margin-left:auto;font-size:.72em;color:var(--text3)"></span></div><div class="acc-body" id="acc-subs-body"><div id="subs-progress-wrap" style="display:none;margin-bottom:8px"><div class="tc-progress"><div class="progress-track"><div class="progress-fill" id="subs-prog-fill" style="width:0%"></div></div><div class="progress-text" id="subs-prog-text">0/0</div></div></div><div id="subs-list"></div><div class="sub-add"><input class="form-input" id="new-sub-input" placeholder="Ajouter une sous-tache..." onkeydown="if(event.key==='Enter')QM.addSub()"><button class="btn btn-success btn-sm" onclick="QM.addSub()">+</button><button class="btn btn-purple btn-sm" onclick="QM.genSubsAI()">IA</button></div><div id="subs-ai-status" style="font-size:.78em;color:var(--purple);margin-top:4px"></div><div id="subs-ai-box" style="display:none" class="ai-sug-box"><div style="font-size:.82em;font-weight:600;color:var(--purple);margin-bottom:6px">Suggestions IA</div><div id="subs-ai-list"></div><div style="display:flex;gap:6px;margin-top:8px"><button class="btn btn-success btn-sm" onclick="QM.addAISubs()">Ajouter selection</button><button class="btn btn-ghost btn-sm" onclick="document.getElementById('subs-ai-box').style.display='none'">X</button></div></div></div></div>
  </div>
  <div class="modal-footer"><button class="btn btn-danger btn-sm" onclick="QM.deleteTask()">Supprimer</button><button class="btn btn-warning btn-sm" onclick="QM.archiveTask()">Archiver</button><div style="flex:1"></div><button class="btn btn-ghost" onclick="QM.closeEdit()">Annuler</button><button class="btn btn-primary" onclick="QM.saveEdit()">Enregistrer</button></div>
</div>
</div>
<!-- Modal Archives -->
<div class="overlay" id="arch-overlay" onclick="QM.overlayClose('arch-overlay',event)">
<div class="modal" onclick="event.stopPropagation()">
  <div class="modal-hdr"><span class="modal-title">Archives</span><button class="modal-close" onclick="QM.closeArchives()">X</button></div>
  <div class="modal-body" id="arch-body"></div>
  <div class="modal-footer"><button class="btn btn-ghost" onclick="QM.closeArchives()">Fermer</button></div>
</div>
</div>
<!-- Modal IA -->
<div class="overlay" id="ai-overlay" onclick="QM.overlayClose('ai-overlay',event)">
<div class="modal" onclick="event.stopPropagation()">
  <div class="modal-hdr"><span class="modal-title">Assistant IA Mistral</span><button class="modal-close" onclick="QM.closeAI()">X</button></div>
  <div class="modal-body"><div class="form-group"><label class="form-label">Commande naturelle</label><textarea class="form-input" id="ai-prompt" rows="4" placeholder="Ex: Cree une tache urgente pour la demo vendredi 14h..."></textarea></div><div id="ai-result" style="display:none;margin-top:10px;padding:10px;background:var(--purple2);border-radius:var(--radius2);font-size:.85em;color:var(--purple)"></div></div>
  <div class="modal-footer"><button class="btn btn-ghost" onclick="QM.closeAI()">Fermer</button><button class="btn btn-purple" onclick="QM.sendAI()">Envoyer a Mistral</button></div>
</div>
</div>

<!-- Modal Vision IA Groq -->
<div class="overlay" id="vision-overlay" onclick="QM.overlayClose('vision-overlay',event)">
<div class="modal" onclick="event.stopPropagation()" style="max-width:660px">
  <div class="modal-hdr">
    <span class="modal-title">&#128247; Vision IA Groq &#8212; Analyse et creation de taches</span>
    <button class="modal-close" onclick="QM.closeVision()">X</button>
  </div>
  <div class="modal-body" style="max-height:75vh">
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;padding:8px;background:var(--bg3);border-radius:6px">
      <span style="font-size:.8em;color:var(--text3)">Statut Groq :</span>
      <span id="groq-status-badge" style="font-size:.8em;color:var(--text3)">Verification...</span>
    </div>
    <div style="margin-bottom:12px">
      <label class="form-label" style="margin-bottom:6px">Image (Ctrl+V pour coller ou cliquer)</label>
      <div onclick="QM.visionChooseFile()" style="border:2px dashed var(--border2);border-radius:8px;padding:14px;text-align:center;cursor:pointer;transition:border .15s" onmouseenter="this.style.borderColor='var(--blue)'" onmouseleave="this.style.borderColor='var(--border2)'">
        <div id="vision-img-preview"></div>
        <div id="vision-img-status" style="font-size:.82em;color:var(--text3);margin-top:4px">Coller image Ctrl+V ou cliquer pour choisir</div>
      </div>
      <button class="btn btn-ghost btn-sm" style="margin-top:6px" onclick="QM.clearVisionImage()">Effacer image</button>
    </div>
    <div class="form-group" style="margin-bottom:10px">
      <label class="form-label">Instruction *</label>
      <textarea class="form-input" id="vision-prompt" rows="4" placeholder="Ex: Cree les taches pour ce projet avec rappels la semaine prochaine, categorie Travail&#10;&#10;Ou sans image : Prepare un plan pour organiser notre conference en juin avec les etapes cles"></textarea>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:12px">
      <div class="form-group">
        <label class="form-label">Categorie par defaut</label>
        <select class="form-input" id="vision-cat"><option value="">Auto (IA choisit)</option></select>
      </div>
      <div class="form-group">
        <label class="form-label">Rappel par defaut</label>
        <input type="datetime-local" class="form-input" id="vision-reminder">
      </div>
    </div>
    <div id="vision-result" style="display:none;margin-top:10px;border:1px solid var(--border2);border-radius:8px;padding:12px;background:var(--bg3)"></div>
  </div>
  <div class="modal-footer">
    <button class="btn btn-ghost" onclick="QM.closeVision()">Fermer</button>
    <button class="btn btn-purple" id="vision-send-btn" onclick="QM.sendVision()">&#128247; Analyser et creer les taches</button>
  </div>
</div></div>

<!-- Modal Settings -->
<div class="overlay" id="settings-overlay" onclick="QM.overlayClose('settings-overlay',event)">
<div class="modal" onclick="event.stopPropagation()" style="max-width:480px">
  <div class="modal-hdr">
    <span class="modal-title">&#9881;&#65039; Reglages QuickMind Web</span>
    <button class="modal-close" onclick="QM.closeSettings()">X</button>
  </div>
  <div class="modal-body">
    <div style="margin-bottom:16px;padding:10px;background:var(--bg3);border-radius:8px">
      <div style="font-size:.8em;font-weight:600;color:var(--text3);margin-bottom:6px;text-transform:uppercase;letter-spacing:.06em">Moteur IA</div>
      <div id="sett-ai-status" style="font-size:.85em;color:var(--text3)">Verification...</div>
    </div>
    <div class="form-grid">
      <div class="form-group">
        <label class="form-label">Frequence health check (secondes)</label>
        <input type="number" class="form-input" id="sett-health" min="5" max="300" value="30">
        <div style="font-size:.72em;color:var(--text3);margin-top:3px">Min 5s, Max 300s (5 min)</div>
      </div>
      <div class="form-group">
        <label class="form-label">Taille de la police (px)</label>
        <input type="number" class="form-input" id="sett-font" min="10" max="24" value="14">
        <div style="font-size:.72em;color:var(--text3);margin-top:3px">Min 10px, Max 24px</div>
      </div>
    </div>
    <div style="margin-top:14px;padding:10px;background:var(--bg3);border-radius:8px">
      <div style="font-size:.8em;font-weight:600;color:var(--text3);margin-bottom:8px;text-transform:uppercase;letter-spacing:.06em">Legende priorites</div>
      <div style="display:flex;flex-direction:column;gap:5px;font-size:.82em">
        <div style="display:flex;align-items:center;gap:8px"><div style="width:12px;height:12px;border-radius:2px;background:var(--red);flex-shrink:0"></div><span>Bordure rouge = Priorite URGENTE</span></div>
        <div style="display:flex;align-items:center;gap:8px"><div style="width:12px;height:12px;border-radius:2px;background:var(--orange);flex-shrink:0"></div><span>Bordure orange = Priorite HAUTE</span></div>
        <div style="display:flex;align-items:center;gap:8px"><div style="width:12px;height:12px;border-radius:2px;background:var(--blue);flex-shrink:0"></div><span>Bordure bleue = Priorite NORMALE</span></div>
        <div style="display:flex;align-items:center;gap:8px"><div style="width:12px;height:12px;border-radius:2px;background:var(--text3);flex-shrink:0"></div><span>Bordure grise = Priorite BASSE</span></div>
        <div style="display:flex;align-items:center;gap:8px"><div style="width:12px;height:12px;border-radius:2px;background:var(--green);flex-shrink:0"></div><span>Bordure verte = Tache TERMINEE</span></div>
      </div>
    </div>
  </div>
  <div class="modal-footer">
    <button class="btn btn-ghost" onclick="QM.closeSettings()">Annuler</button>
    <button class="btn btn-primary" onclick="QM.saveAndApply()">&#10003; Appliquer et sauvegarder</button>
  </div>
</div>
</div>
<div class="toast" id="toast-msg"></div>
<script src="/app.js"></script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def web_ui():
    return WEB_UI


@app.get("/app.js")
def serve_app_js():
    """Sert le fichier JavaScript."""
    from fastapi.responses import Response
    from pathlib import Path
    p = Path(__file__).parent / "app.js"
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            js = f.read()
        return Response(content=js, media_type="application/javascript",
            headers={"Cache-Control":"no-cache, no-store, must-revalidate"})
    return Response(content="// app.js not found", media_type="application/javascript")


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


@app.get("/", response_class=HTMLResponse)
def web_ui():
    return WEB_UI


@app.get("/app.js")
def serve_app_js():
    from fastapi.responses import Response
    from pathlib import Path
    p = Path(__file__).parent / "app.js"
    if p.exists():
        with open(p, "r", encoding="utf-8") as f: js = f.read()
        return Response(content=js, media_type="application/javascript",
            headers={"Cache-Control":"no-cache, no-store, must-revalidate"})
    return Response(content="// not found", media_type="application/javascript")


_server_thread = None
_server = None


def start_api_server(port: int = 8765, ui_callback=None, tk_app=None):
    global _server_thread, _server
    if ui_callback: set_ui_callback(ui_callback)
    if tk_app: set_tk_app(tk_app)
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="warning", access_log=False)
    _server = uvicorn.Server(config)
    def _run():
        import asyncio
        loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
        loop.run_until_complete(_server.serve())
    _server_thread = threading.Thread(target=_run, daemon=True, name="QuickMind-API")
    _server_thread.start()
    import socket
    try: ip = socket.gethostbyname(socket.gethostname())
    except Exception: ip = "localhost"
    print(f"[API] Serveur demarre :")
    print(f"[API]   Local  : http://localhost:{port}")
    print(f"[API]   Reseau : http://{ip}:{port}")
    print(f"[API]   Docs   : http://localhost:{port}/docs")
