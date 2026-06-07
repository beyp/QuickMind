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
    category: Optional[str] = None,
    status:   Optional[str] = None,
    priority: Optional[str] = None,
):
    from core.database import get_tasks, get_categories
    cats       = {c.name.lower(): c.id for c in get_categories()}
    cats_by_id = {c.id: c.name        for c in get_categories()}
    cat_id     = cats.get(category.lower()) if category else None
    tasks      = get_tasks(category_id=cat_id, status=status)
    if priority:
        tasks = [t for t in tasks if t.priority == priority]
    from core.database import get_subtask_progress
    result_list = []
    for t in tasks:
        done_c, total_c = get_subtask_progress(t.id)
        result_list.append({
            "id":            t.id,
            "title":         t.title,
            "description":   t.description,
            "category":      cats_by_id.get(t.category_id, ""),
            "priority":      t.priority,
            "status":        t.status,
            "reminder":      t.reminder_at.isoformat() if t.reminder_at else None,
            "created_at":    t.created_at.isoformat(),
            "recurrence":    t.recurrence,
            "subtask_done":  done_c,
            "subtask_count": total_c,
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


WEB_UI = """
<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
<title>QuickMind</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
       background: #1a1a2e; color: #e0e0e0; min-height: 100vh; }
.container { max-width: 680px; margin: 0 auto; padding: 16px; }
h1 { color: #1E90FF; font-size: 1.6em; margin-bottom: 2px; }
.subtitle { color: #888; font-size: 0.85em; margin-bottom: 16px; }
.health { font-size: 0.8em; color: #555; text-align: right; margin-bottom: 12px; }
.green { color: #32CD32; } .red { color: #FF4444; }
.card { background: #16213e; border-radius: 12px; padding: 16px;
        margin-bottom: 12px; border: 1px solid #0f3460; }
h3 { color: #1E90FF; margin-bottom: 12px; font-size: 1em; }
label { display: block; margin-bottom: 4px; color: #aaa; font-size: 0.82em; }
input, textarea, select {
  width: 100%; padding: 9px 12px; border-radius: 8px;
  border: 1px solid #0f3460; background: #0f3460; color: #e0e0e0;
  font-size: 0.95em; margin-bottom: 10px; outline: none;
  -webkit-appearance: none; }
input:focus, textarea:focus, select:focus { border-color: #1E90FF; }
textarea { resize: vertical; min-height: 70px; }
.row { display: flex; gap: 10px; }
.row > div { flex: 1; }
.btn { width: 100%; padding: 11px; border-radius: 8px; border: none;
       cursor: pointer; font-size: 0.95em; font-weight: bold;
       -webkit-tap-highlight-color: transparent; }
.btn-primary { background: #1E90FF; color: white; }
.btn-ai      { background: #9370DB; color: white; margin-top: 6px; }
.btn-danger  { background: #8b0000; color: white; }
.btn-success { background: #2a5a2a; color: white; }
.btn-gray    { background: #333; color: #aaa; }
.btn-sm { padding: 6px 12px; font-size: 0.82em; border-radius: 6px;
          border: none; cursor: pointer; font-weight: bold; }
#status { margin-top: 10px; padding: 9px 12px; border-radius: 8px;
          display: none; font-size: 0.88em; }
.ok  { background: #1a3a1a; color: #32CD32; border: 1px solid #32CD32; }
.err { background: #3a1a1a; color: #FF4444; border: 1px solid #FF4444; }
.tasks-list { margin-top: 6px; }
.task-item { padding: 10px 12px; background: #0f3460; border-radius: 8px;
             margin-bottom: 8px; cursor: pointer; transition: background 0.1s; }
.task-item:active { background: #1a4a8a; }
.task-header { display: flex; justify-content: space-between; align-items: flex-start; }
.task-title  { font-weight: bold; font-size: 0.95em; flex: 1; margin-right: 8px; }
.task-meta   { font-size: 0.78em; color: #888; margin-top: 3px; }
.badge { padding: 2px 7px; border-radius: 20px; font-size: 0.72em;
         font-weight: bold; white-space: nowrap; }
.badge-todo  { background: #333; color: #aaa; }
.badge-wip   { background: #3a2a00; color: #FF8C00; }
.badge-done  { background: #1a3a1a; color: #32CD32; }
.prio-urgent { color: #FF4444; }
.prio-high   { color: #FF8C00; }
.prio-normal { color: #1E90FF; }
.prio-low    { color: #888; }
/* Barre de progression */
.progress-bar { height: 5px; background: #0f3460; border-radius: 3px;
                margin-top: 5px; overflow: hidden; }
.progress-fill { height: 100%; background: #1E90FF; border-radius: 3px;
                 transition: width 0.3s; }
/* Modal */
.modal-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0;
                 background: rgba(0,0,0,0.7); z-index: 100;
                 display: none; overflow-y: auto; }
.modal-overlay.active { display: block; }
.modal { background: #16213e; border-radius: 12px; margin: 20px auto;
         max-width: 640px; padding: 20px; border: 1px solid #1E90FF; }
.modal-header { display: flex; justify-content: space-between;
                align-items: center; margin-bottom: 14px; }
.modal-title { color: #1E90FF; font-weight: bold; font-size: 1.1em; }
.modal-close { background: none; border: none; color: #888; font-size: 1.4em;
               cursor: pointer; padding: 0 6px; }
/* Sous-taches */
.subtask-item { display: flex; align-items: center; padding: 7px 0;
                border-bottom: 1px solid #0f3460; }
.subtask-item:last-child { border-bottom: none; }
.subtask-check { width: 20px; height: 20px; cursor: pointer; margin-right: 10px;
                 flex-shrink: 0; accent-color: #1E90FF; }
.subtask-title { flex: 1; font-size: 0.9em; }
.subtask-title.done { text-decoration: line-through; color: #666; }
.subtask-del { background: none; border: none; color: #666; cursor: pointer;
               font-size: 1em; padding: 0 4px; }
.add-subtask-row { display: flex; gap: 8px; margin-top: 8px; }
.add-subtask-row input { flex: 1; margin-bottom: 0; }
.add-subtask-row button { white-space: nowrap; }
.tabs { display: flex; gap: 8px; margin-bottom: 12px; }
.tab { flex: 1; padding: 8px; text-align: center; border-radius: 8px;
       border: none; cursor: pointer; font-size: 0.88em; font-weight: bold;
       background: #0f3460; color: #aaa; }
.tab.active { background: #1E90FF; color: white; }
.hdr { display: flex; justify-content: space-between; align-items: center;
       margin-bottom: 10px; }
.refresh-btn { padding: 5px 10px; border-radius: 6px; border: none;
               cursor: pointer; background: #0f3460; color: #888;
               font-size: 0.8em; }
.filter-row { display: flex; gap: 6px; margin-bottom: 10px; overflow-x: auto; }
.filter-btn { padding: 5px 10px; border-radius: 20px; border: none;
              cursor: pointer; font-size: 0.8em; background: #0f3460; color: #888;
              white-space: nowrap; }
.filter-btn.active { background: #1E90FF; color: white; }
.ai-row { display: flex; gap: 8px; }
.ai-row input { flex: 1; margin-bottom: 0; }
.ai-row button { white-space: nowrap; padding: 9px 14px; border-radius: 8px;
                 border: none; background: #9370DB; color: white;
                 cursor: pointer; font-weight: bold; }
</style>
</head>
<body>
<div class="container">
  <h1>⚡ QuickMind</h1>
  <p class="subtitle">Acces rapide — Mobile & Desktop</p>
  <div class="health" id="health">Connexion...</div>

  <!-- Tabs -->
  <div class="tabs">
    <button class="tab active" onclick="switchTab('tasks')">📋 Taches</button>
    <button class="tab" onclick="switchTab('add')">➕ Ajouter</button>
    <button class="tab" onclick="switchTab('ai')">🤖 IA</button>
  </div>

  <!-- Tab Taches -->
  <div id="tab-tasks">
    <div class="hdr">
      <div class="filter-row" id="filters">
        <button class="filter-btn active" onclick="setFilter('all')">Toutes</button>
        <button class="filter-btn" onclick="setFilter('todo')">A faire</button>
        <button class="filter-btn" onclick="setFilter('in_progress')">En cours</button>
        <button class="filter-btn" onclick="setFilter('done')">Terminees</button>
      </div>
      <button class="refresh-btn" onclick="loadTasks()">↻</button>
    </div>
    <div id="tasks-list">Chargement...</div>
  </div>

  <!-- Tab Ajouter -->
  <div id="tab-add" style="display:none">
    <div class="card">
      <label>Titre *</label>
      <input id="add-title" placeholder="Titre de la tache..." autofocus>
      <div class="row">
        <div>
          <label>Categorie</label>
          <select id="add-category">
            <option value="">Aucune</option>
          </select>
        </div>
        <div>
          <label>Priorite</label>
          <select id="add-priority">
            <option value="normal">Normal</option>
            <option value="low">Basse</option>
            <option value="high">Haute</option>
            <option value="urgent">Urgente</option>
          </select>
        </div>
      </div>
      <label>Description</label>
      <textarea id="add-desc" placeholder="Description (optionnel)..."></textarea>
      <label>Rappel</label>
      <input id="add-reminder" type="datetime-local">
      <button class="btn btn-primary" onclick="createTask()">✅ Creer la tache</button>
      <div id="status"></div>
    </div>
  </div>

  <!-- Tab IA -->
  <div id="tab-ai" style="display:none">
    <div class="card">
      <label style="color:#9370DB;font-weight:bold;">🤖 Creer via IA</label>
      <div class="ai-row">
        <input id="ai-text" placeholder="Ex: Reunion equipe lundi 10h Travail urgente">
        <button onclick="createTaskAI()">Envoyer</button>
      </div>
      <div id="ai-status" style="margin-top:8px;font-size:0.85em;color:#888;"></div>
    </div>
  </div>
</div>

<!-- Modal Edition Tache -->
<div class="modal-overlay" id="modal-overlay" onclick="closeModal(event)">
  <div class="modal" onclick="event.stopPropagation()">
    <div class="modal-header">
      <span class="modal-title">✏️ Editer la tache</span>
      <button class="modal-close" onclick="closeModal()">✕</button>
    </div>

    <label>Titre *</label>
    <input id="edit-title">

    <label>Description</label>
    <textarea id="edit-desc"></textarea>

    <div class="row">
      <div>
        <label>Categorie</label>
        <select id="edit-category"></select>
      </div>
      <div>
        <label>Priorite</label>
        <select id="edit-priority">
          <option value="low">Basse</option>
          <option value="normal">Normal</option>
          <option value="high">Haute</option>
          <option value="urgent">Urgente</option>
        </select>
      </div>
    </div>

    <label>Statut</label>
    <select id="edit-status">
      <option value="todo">A faire</option>
      <option value="in_progress">En cours</option>
      <option value="done">Termine</option>
    </select>

    <!-- Sous-taches -->
    <div style="margin-top:12px;">
      <div class="hdr">
        <label style="margin:0;font-weight:bold;">Sous-taches</label>
        <span id="subtask-progress" style="font-size:0.8em;color:#888;"></span>
      </div>
      <div id="progress-bar-container" style="display:none;margin:4px 0 8px 0;">
        <div class="progress-bar">
          <div class="progress-fill" id="progress-fill" style="width:0%"></div>
        </div>
      </div>
      <div id="subtasks-list"></div>
      <div class="add-subtask-row">
        <input id="new-subtask" placeholder="Nouvelle sous-tache... (Entree)">
        <button class="btn-sm btn-primary" onclick="addSubtask()">＋</button>
      </div>
    </div>

    <div style="display:flex;gap:10px;margin-top:14px;">
      <button class="btn btn-success" onclick="saveTask()">💾 Enregistrer</button>
      <button class="btn btn-danger"  onclick="deleteCurrentTask()">🗑 Supprimer</button>
    </div>
  </div>
</div>

<script>
const API = window.location.origin;
let currentTaskId = null;
let currentFilter = "all";
let categories    = [];

// ── Init ─────────────────────────────────────────────────────────────────────
async function init() {
  await checkHealth();
  await loadCategories();
  await loadTasks();
}

async function checkHealth() {
  try {
    const d = await (await fetch(API+"/health")).json();
    document.getElementById("health").innerHTML =
      '<span class="green">●</span> QuickMind actif — '+d.tasks+' tache(s)';
  } catch(e) {
    document.getElementById("health").innerHTML =
      '<span class="red">●</span> Hors ligne';
  }
}

async function loadCategories() {
  try {
    categories = await (await fetch(API+"/categories")).json();
    // Remplir les selects
    const opts = categories.map(c =>
      `<option value="${c.name}">${c.name}</option>`).join("");
    document.getElementById("add-category").innerHTML =
      '<option value="">Aucune</option>' + opts;
    document.getElementById("edit-category").innerHTML =
      '<option value="">Aucune</option>' + opts;
  } catch(e) { console.log("Erreur categories:", e); }
}

// ── Tabs ─────────────────────────────────────────────────────────────────────
function switchTab(tab) {
  ["tasks","add","ai"].forEach(t => {
    document.getElementById("tab-"+t).style.display = t===tab ? "block" : "none";
  });
  document.querySelectorAll(".tab").forEach((btn, i) => {
    btn.classList.toggle("active", ["tasks","add","ai"][i] === tab);
  });
  if (tab === "tasks") loadTasks();
}

// ── Filtres ───────────────────────────────────────────────────────────────────
function setFilter(f) {
  currentFilter = f;
  document.querySelectorAll(".filter-btn").forEach(b => b.classList.remove("active"));
  event.target.classList.add("active");
  loadTasks();
}

// ── Taches ───────────────────────────────────────────────────────────────────
const PRIO_CLASS = {urgent:"prio-urgent",high:"prio-high",normal:"prio-normal",low:"prio-low"};
const STATUS_CLASS = {todo:"badge-todo",in_progress:"badge-wip",done:"badge-done"};
const STATUS_LBL   = {todo:"A faire",in_progress:"En cours",done:"Termine"};

async function loadTasks() {
  const el = document.getElementById("tasks-list");
  el.innerHTML = "Chargement...";
  try {
    let url = API+"/tasks";
    if (currentFilter !== "all") url += "?status=" + currentFilter;
    const tasks = await (await fetch(url)).json();
    if (!tasks.length) {
      el.innerHTML = "<p style='color:#555;padding:16px 0;text-align:center;'>Aucune tache.</p>";
      return;
    }
    el.innerHTML = tasks.map(t => {
      const subInfo = t.subtask_count > 0
        ? `<div class="progress-bar" style="margin-top:5px;">
             <div class="progress-fill" style="width:${Math.round(t.subtask_done/t.subtask_count*100)||0}%;
               background:${t.subtask_done===t.subtask_count?'#32CD32':'#1E90FF'}"></div>
           </div>
           <div style="font-size:0.75em;color:#888;margin-top:2px;">
             ${t.subtask_done}/${t.subtask_count} sous-taches
           </div>` : "";
      return `<div class="task-item" onclick="openTask(${t.id})">
        <div class="task-header">
          <div class="task-title ${PRIO_CLASS[t.priority]||''}">${t.title}</div>
          <span class="badge ${STATUS_CLASS[t.status]||''}">${STATUS_LBL[t.status]||t.status}</span>
        </div>
        <div class="task-meta">${t.category||''} ${t.reminder?'⏰ '+new Date(t.reminder).toLocaleString('fr-FR'):''}</div>
        ${subInfo}
      </div>`;
    }).join("");
  } catch(e) {
    el.innerHTML = "<p style='color:#555'>Erreur de connexion.</p>";
  }
}

// ── Modal edition ─────────────────────────────────────────────────────────────
async function openTask(taskId) {
  currentTaskId = taskId;
  try {
    const t = await (await fetch(`${API}/task/${taskId}`)).json();
    document.getElementById("edit-title").value    = t.title || "";
    document.getElementById("edit-desc").value     = t.description || "";
    document.getElementById("edit-priority").value = t.priority || "normal";
    document.getElementById("edit-status").value   = t.status   || "todo";
    // Categorie
    const catSel = document.getElementById("edit-category");
    for (let i = 0; i < catSel.options.length; i++) {
      if (catSel.options[i].value === t.category) {
        catSel.selectedIndex = i; break;
      }
    }
    // Charger les sous-taches
    renderSubtasks(t.subtasks || []);
    // Ouvrir le modal
    document.getElementById("modal-overlay").classList.add("active");
    document.getElementById("edit-title").focus();
  } catch(e) {
    showStatus("Erreur chargement : " + e.message, false);
  }
}

function closeModal(e) {
  if (!e || e.target === document.getElementById("modal-overlay")) {
    document.getElementById("modal-overlay").classList.remove("active");
    currentTaskId = null;
    loadTasks();
  }
}

// ── Sous-taches ───────────────────────────────────────────────────────────────
function renderSubtasks(subs) {
  const el    = document.getElementById("subtasks-list");
  const prog  = document.getElementById("subtask-progress");
  const bar   = document.getElementById("progress-fill");
  const barC  = document.getElementById("progress-bar-container");
  const done  = subs.filter(s => s.done).length;
  const total = subs.length;

  if (total > 0) {
    const pct = Math.round(done/total*100);
    prog.textContent = `${done}/${total} (${pct}%)`;
    bar.style.width  = pct + "%";
    bar.style.background = done===total ? "#32CD32" : "#1E90FF";
    barC.style.display = "block";
  } else {
    prog.textContent   = "";
    barC.style.display = "none";
  }

  el.innerHTML = subs.map(s => `
    <div class="subtask-item" id="sub-${s.id}">
      <input type="checkbox" class="subtask-check"
        ${s.done ? "checked" : ""}
        onchange="toggleSub(${s.id})">
      <span class="subtask-title ${s.done?'done':''}">${s.title}</span>
      <button class="subtask-del" onclick="deleteSub(${s.id})" title="Supprimer">✕</button>
    </div>
  `).join("") || '<p style="color:#555;font-size:0.85em;padding:6px 0;">Aucune sous-tache.</p>';

  // Bind Entree sur le champ ajout
  const inp = document.getElementById("new-subtask");
  inp.onkeydown = e => { if (e.key==="Enter") addSubtask(); };
}

async function toggleSub(subId) {
  if (!currentTaskId) return;
  try {
    await fetch(`${API}/task/${currentTaskId}/subtask/${subId}/toggle`, {method:"POST"});
    // Recharger les sous-taches
    const t = await (await fetch(`${API}/task/${currentTaskId}`)).json();
    renderSubtasks(t.subtasks || []);
  } catch(e) { console.log("Erreur toggle:", e); }
}

async function addSubtask() {
  if (!currentTaskId) return;
  const inp   = document.getElementById("new-subtask");
  const title = inp.value.trim();
  if (!title) return;
  try {
    const r = await fetch(`${API}/task/${currentTaskId}/subtask`, {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({title})
    });
    if (!r.ok) { alert("Limite de 10 sous-taches atteinte !"); return; }
    inp.value = "";
    const t = await (await fetch(`${API}/task/${currentTaskId}`)).json();
    renderSubtasks(t.subtasks || []);
  } catch(e) { console.log("Erreur ajout sous-tache:", e); }
}

async function deleteSub(subId) {
  if (!currentTaskId) return;
  try {
    await fetch(`${API}/task/${currentTaskId}/subtask/${subId}`, {method:"DELETE"});
    const t = await (await fetch(`${API}/task/${currentTaskId}`)).json();
    renderSubtasks(t.subtasks || []);
  } catch(e) { console.log("Erreur suppression:", e); }
}

// ── Sauvegarder tache ─────────────────────────────────────────────────────────
async function saveTask() {
  if (!currentTaskId) return;
  try {
    await fetch(`${API}/task/${currentTaskId}`, {
      method: "PUT",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({
        title:       document.getElementById("edit-title").value,
        description: document.getElementById("edit-desc").value,
        category:    document.getElementById("edit-category").value,
        priority:    document.getElementById("edit-priority").value,
        status:      document.getElementById("edit-status").value,
      })
    });
    closeModal();
  } catch(e) { alert("Erreur : " + e.message); }
}

async function deleteCurrentTask() {
  if (!currentTaskId) return;
  if (!confirm("Supprimer cette tache ?")) return;
  try {
    await fetch(`${API}/task/${currentTaskId}`, {method:"DELETE"});
    closeModal();
  } catch(e) { alert("Erreur : " + e.message); }
}

// ── Creer tache ───────────────────────────────────────────────────────────────
function showStatus(msg, ok) {
  const el = document.getElementById("status");
  el.textContent = msg;
  el.className   = ok ? "ok" : "err";
  el.style.display = "block";
  setTimeout(() => el.style.display = "none", 4000);
}

async function createTask() {
  const title = document.getElementById("add-title").value.trim();
  if (!title) { showStatus("Titre obligatoire !", false); return; }
  const rem = document.getElementById("add-reminder").value;
  try {
    const d = await (await fetch(API+"/task", {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({
        title,
        description: document.getElementById("add-desc").value,
        category:    document.getElementById("add-category").value,
        priority:    document.getElementById("add-priority").value,
        reminder:    rem ? rem+":00" : null,
      })
    })).json();
    showStatus("✅ Tache #"+d.id+" creee : "+d.title, true);
    document.getElementById("add-title").value       = "";
    document.getElementById("add-desc").value        = "";
    document.getElementById("add-reminder").value    = "";
    document.getElementById("add-priority").value    = "normal";
    switchTab("tasks");
  } catch(e) { showStatus("Erreur : "+e.message, false); }
}

async function createTaskAI() {
  const text = document.getElementById("ai-text").value.trim();
  if (!text) return;
  const aiStatus = document.getElementById("ai-status");
  aiStatus.textContent = "Mistral analyse...";
  try {
    const d = await (await fetch(API+"/task/ai", {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body: JSON.stringify({text})
    })).json();
    aiStatus.textContent = "✅ " + d.result;
    document.getElementById("ai-text").value = "";
    setTimeout(() => { aiStatus.textContent=""; }, 5000);
    loadTasks();
  } catch(e) { aiStatus.textContent = "Erreur : " + e.message; }
}

// ── Keyboard shortcuts ────────────────────────────────────────────────────────
document.addEventListener("keydown", e => {
  if (e.key === "Escape") closeModal();
  if (e.key === "Enter" && document.activeElement.id === "add-title") createTask();
});

init();
setInterval(checkHealth, 30000);
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
