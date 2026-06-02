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
    return [
        {
            "id":          t.id,
            "title":       t.title,
            "description": t.description,
            "category":    cats_by_id.get(t.category_id, ""),
            "priority":    t.priority,
            "status":      t.status,
            "reminder":    t.reminder_at.isoformat() if t.reminder_at else None,
            "created_at":  t.created_at.isoformat(),
            "recurrence":  t.recurrence,
        }
        for t in tasks
    ]


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


WEB_UI = """
<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>QuickMind</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         background: #1a1a2e; color: #e0e0e0; min-height: 100vh; padding: 20px; }
  .container { max-width: 600px; margin: 0 auto; }
  h1 { color: #1E90FF; margin-bottom: 4px; font-size: 1.8em; }
  .subtitle { color: #888; margin-bottom: 20px; font-size: 0.9em; }
  .card { background: #16213e; border-radius: 12px; padding: 18px;
          margin-bottom: 14px; border: 1px solid #0f3460; }
  label { display: block; margin-bottom: 5px; color: #aaa; font-size: 0.85em; }
  input, textarea, select { width: 100%; padding: 9px 12px; border-radius: 8px;
    border: 1px solid #0f3460; background: #0f3460; color: #e0e0e0;
    font-size: 1em; margin-bottom: 10px; outline: none; }
  input:focus, textarea:focus, select:focus { border-color: #1E90FF; }
  textarea { resize: vertical; min-height: 70px; }
  .row { display: flex; gap: 10px; }
  .row > div { flex: 1; }
  .btn { width: 100%; padding: 11px; border-radius: 8px; border: none;
         cursor: pointer; font-size: 1em; font-weight: bold; }
  .btn-primary { background: #1E90FF; color: white; }
  .btn-ai      { background: #9370DB; color: white; margin-top: 6px; }
  #status { margin-top: 10px; padding: 9px 12px; border-radius: 8px;
            display: none; font-size: 0.9em; }
  .ok  { background: #1a3a1a; color: #32CD32; border: 1px solid #32CD32; }
  .err { background: #3a1a1a; color: #FF4444; border: 1px solid #FF4444; }
  .task-item { padding: 9px 12px; background: #0f3460; border-radius: 8px;
               margin-bottom: 7px; display: flex; justify-content: space-between; }
  .task-title { font-weight: bold; font-size: 0.95em; }
  .task-meta  { font-size: 0.78em; color: #888; margin-top: 2px; }
  .badge { padding: 2px 7px; border-radius: 20px; font-size: 0.72em; font-weight: bold; }
  .badge-todo { background: #333; color: #aaa; }
  .badge-wip  { background: #3a2a00; color: #FF8C00; }
  .badge-done { background: #1a3a1a; color: #32CD32; }
  .pur { color: #FF4444; } .hor { color: #FF8C00; }
  .nor { color: #1E90FF; } .lor { color: #888; }
  .ai-row { display: flex; gap: 8px; }
  .ai-row input { flex: 1; margin-bottom: 0; }
  .ai-row button { width: auto; padding: 9px 16px; border-radius: 8px;
                   border: none; background: #9370DB; color: white;
                   cursor: pointer; font-weight: bold; white-space: nowrap; }
  .health { font-size: 0.8em; color: #555; text-align: right; margin-bottom: 14px; }
  .green { color: #32CD32; }
  .hdr { display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; }
  .refresh { padding: 5px 12px; border-radius: 6px; border: none; cursor: pointer;
             background: #32CD32; color: #000; font-size: 0.82em; font-weight: bold; }
</style>
</head>
<body>
<div class="container">
  <h1>QuickMind</h1>
  <p class="subtitle">Acces rapide depuis n importe quel appareil</p>
  <div class="health" id="health">Connexion...</div>

  <div class="card">
    <h3 style="margin-bottom:14px;color:#1E90FF;">+ Nouvelle tache</h3>
    <label>Titre *</label>
    <input id="title" placeholder="Titre..." autofocus>
    <div class="row">
      <div>
        <label>Categorie</label>
        <select id="category">
          <option value="">Aucune</option>
          <option value="Travail">Travail</option>
          <option value="Perso">Perso</option>
          <option value="Projets">Projets</option>
          <option value="IA / Dev">IA / Dev</option>
        </select>
      </div>
      <div>
        <label>Priorite</label>
        <select id="priority">
          <option value="normal">Normal</option>
          <option value="low">Basse</option>
          <option value="high">Haute</option>
          <option value="urgent">Urgente</option>
        </select>
      </div>
    </div>
    <label>Rappel</label>
    <input id="reminder" type="datetime-local">
    <button class="btn btn-primary" onclick="createTask()">Creer la tache</button>
    <div style="margin-top:14px;padding-top:14px;border-top:1px solid #0f3460;">
      <label style="color:#9370DB;font-weight:bold;">IA — Langage naturel</label>
      <div class="ai-row">
        <input id="ai-text" placeholder="Ex: Preparer demo vendredi 14h...">
        <button onclick="createTaskAI()">IA Envoyer</button>
      </div>
    </div>
    <div id="status"></div>
  </div>

  <div class="card">
    <div class="hdr">
      <h3 style="color:#1E90FF;">Taches en cours</h3>
      <button class="refresh" onclick="loadTasks()">Rafraichir</button>
    </div>
    <div id="tasks-list">Chargement...</div>
  </div>
</div>
<script>
const API = window.location.origin;
async function checkHealth() {
  try {
    const d = await (await fetch(API+"/health")).json();
    document.getElementById("health").innerHTML =
      '<span class="green">OK</span> QuickMind actif — '+d.tasks+' tache(s)';
  } catch(e) { document.getElementById("health").textContent = "Hors ligne"; }
}
function showStatus(msg, ok) {
  const el = document.getElementById("status");
  el.textContent = msg; el.className = ok ? "ok" : "err";
  el.style.display = "block";
  setTimeout(() => el.style.display = "none", 4000);
}
async function createTask() {
  const title = document.getElementById("title").value.trim();
  if (!title) { showStatus("Titre obligatoire !", false); return; }
  const rem = document.getElementById("reminder").value;
  try {
    const d = await (await fetch(API+"/task", {method:"POST",
      headers:{"Content-Type":"application/json"},
      body: JSON.stringify({title,
        description: "",
        category: document.getElementById("category").value,
        priority: document.getElementById("priority").value,
        reminder: rem ? rem+":00" : null})})).json();
    showStatus("OK Tache #"+d.id+" creee : "+d.title, true);
    document.getElementById("title").value = "";
    document.getElementById("reminder").value = "";
    loadTasks();
  } catch(e) { showStatus("Erreur : "+e.message, false); }
}
async function createTaskAI() {
  const text = document.getElementById("ai-text").value.trim();
  if (!text) { showStatus("Entrez une commande !", false); return; }
  showStatus("Mistral analyse...", true);
  try {
    const d = await (await fetch(API+"/task/ai", {method:"POST",
      headers:{"Content-Type":"application/json"},
      body: JSON.stringify({text})})).json();
    showStatus("OK "+d.result, true);
    document.getElementById("ai-text").value = "";
    loadTasks();
  } catch(e) { showStatus("Erreur : "+e.message, false); }
}
async function loadTasks() {
  try {
    const todo = await (await fetch(API+"/tasks?status=todo")).json();
    const wip  = await (await fetch(API+"/tasks?status=in_progress")).json();
    const all  = [...wip, ...todo];
    const el   = document.getElementById("tasks-list");
    if (!all.length) { el.innerHTML='<p style="color:#555">Aucune tache en cours.</p>'; return; }
    const PC = {urgent:"pur",high:"hor",normal:"nor",low:"lor"};
    const SC = {todo:"badge-todo",in_progress:"badge-wip",done:"badge-done"};
    const SL = {todo:"A faire",in_progress:"En cours",done:"Termine"};
    el.innerHTML = all.slice(0,15).map(t=>`
      <div class="task-item">
        <div>
          <div class="task-title ${PC[t.priority]||''}">${t.title}</div>
          <div class="task-meta">${t.category||''} ${t.reminder?'Rappel: '+new Date(t.reminder).toLocaleString('fr-FR'):''}</div>
        </div>
        <span class="badge ${SC[t.status]||''}">${SL[t.status]||t.status}</span>
      </div>`).join("");
  } catch(e) { document.getElementById("tasks-list").innerHTML='<p style="color:#555">Erreur.</p>'; }
}
document.addEventListener("keydown",e=>{
  if(e.key==="Enter"&&document.activeElement.id==="title") createTask();
  if(e.key==="Enter"&&document.activeElement.id==="ai-text") createTaskAI();
});
checkHealth(); loadTasks();
setInterval(checkHealth, 30000);
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
    print(f"[API]   Tel    : http://{ip}:{port}")
