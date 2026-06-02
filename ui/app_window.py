import customtkinter as ctk
from ui.sidebar import Sidebar
from ui.task_panel import TaskPanel
from ui.kanban_panel import KanbanPanel
from ui.prompt_bar import PromptBar
from ui.ai_panel import AIPanel
from ui.outlook_panel import OutlookPanel
from core.database import init_db
from core.scheduler import start_scheduler
import yaml
import threading
from pathlib import Path

_cfg_path = Path(__file__).parent.parent / "config.yaml"
with open(_cfg_path, "r", encoding="utf-8") as f:
    _cfg = yaml.safe_load(f)

_DEFAULT_VIEW = _cfg.get("app", {}).get("default_view", "kanban")


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Fix redraw multi-ecrans — desactiver scaling automatique CTk
        try:
            ctk.deactivate_automatic_dpi_awareness()
        except Exception:
            pass
        try:
            self.tk.call("tk", "scaling", 1.0)
        except Exception:
            pass

        ctk.set_appearance_mode(_cfg["app"]["theme"])
        ctk.set_default_color_theme("blue")

        self.title("QuickMind  v" + _cfg["app"]["version"] +
                   "  —  IA locale Mistral + Outlook")
        self.geometry("1200x800")
        self.minsize(900, 600)

        init_db()
        start_scheduler()

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=3)
        self.grid_rowconfigure(1, weight=2)
        self.grid_rowconfigure(2, weight=0)

        self.selected_category_id = None
        self._ai_visible           = False
        self._update_dialog        = None
        self._kanban_mode          = (_DEFAULT_VIEW == "kanban")

        # Sidebar
        self.sidebar = Sidebar(self, on_select=self._on_category_select)
        self.sidebar.grid(row=0, column=0, rowspan=2, sticky="nsw",
                          padx=(10, 0), pady=10)

        # Task panel (liste)
        self.task_panel = TaskPanel(self)

        # Kanban panel
        self.kanban_panel = KanbanPanel(self)

        # Afficher la vue par defaut
        if self._kanban_mode:
            self.kanban_panel.grid(row=0, column=1, sticky="nsew",
                                   padx=10, pady=(10, 4))
        else:
            self.task_panel.grid(row=0, column=1, sticky="nsew",
                                 padx=10, pady=(10, 4))

        # IA Panel
        self.ai_panel = AIPanel(self, on_action_done=self._on_ai_action)

        # Barre basse
        self.prompt_bar = PromptBar(
            self,
            on_submit=self._on_prompt,
            on_toggle_ai=self._toggle_ai,
            on_outlook=self._open_outlook,
            on_toggle_kanban=self._toggle_kanban,
            kanban_active=self._kanban_mode,
            on_move_screen=self._move_to_screen,
        )
        self.prompt_bar.grid(row=2, column=0, columnspan=2,
                             sticky="ew", padx=10, pady=(0, 10))

        # Refresh initial
        if self._kanban_mode:
            self.kanban_panel.refresh(category_id=None)
        else:
            self.task_panel.refresh(category_id=None)

        # Lancer l API REST apres que l UI soit prete
        self.after(500, self._start_api)

        # Verif mise a jour
        updater_cfg = _cfg.get("updater", {})
        if updater_cfg.get("enabled", True) and updater_cfg.get("check_on_startup", True):
            print("[Updater] Verification dans 3 secondes...")
            self.after(3000, self._check_for_update)

    # ── API REST ──────────────────────────────────────────────────────────────
    def _start_api(self):
        """Lance l API REST FastAPI en arriere-plan."""
        api_cfg = _cfg.get("api", {})
        if not api_cfg.get("enabled", True):
            print("[API] Desactivee dans config.yaml")
            return
        try:
            from core.api_server import start_api_server
            port = api_cfg.get("port", 8765)
            start_api_server(port=port, ui_callback=self._on_ai_action, tk_app=self)
        except ImportError:
            print("[API] fastapi/uvicorn non installes.")
            print("[API] Lance : pip install fastapi uvicorn")
        except Exception as e:
            print(f"[API] Erreur demarrage : {e}")
            import traceback
            traceback.print_exc()

    # ── Callbacks ─────────────────────────────────────────────────────────────
    def _on_category_select(self, cat_id):
        self.selected_category_id = cat_id
        if self._kanban_mode:
            self.kanban_panel.refresh(category_id=cat_id)
        else:
            self.task_panel.refresh(category_id=cat_id)

    def _toggle_kanban(self):
        self._kanban_mode = not self._kanban_mode
        if self._kanban_mode:
            self.task_panel.grid_forget()
            self.kanban_panel.grid(row=0, column=1, sticky="nsew",
                                   padx=10, pady=(10, 4))
            self.kanban_panel.refresh(category_id=self.selected_category_id)
        else:
            self.kanban_panel.grid_forget()
            self.task_panel.grid(row=0, column=1, sticky="nsew",
                                 padx=10, pady=(10, 4))
            self.task_panel.refresh(category_id=self.selected_category_id)

    def _toggle_ai(self):
        self._ai_visible = not self._ai_visible
        if self._ai_visible:
            self.ai_panel.grid(row=1, column=1, sticky="nsew",
                               padx=10, pady=(0, 4))
        else:
            self.ai_panel.grid_forget()

    def _open_outlook(self):
        OutlookPanel(self, on_task_created=self._on_ai_action)

    def _on_ai_action(self):
        if self._kanban_mode:
            self.kanban_panel.refresh(category_id=self.selected_category_id)
        else:
            self.task_panel.refresh(category_id=self.selected_category_id)

    def _open_file_dialog(self, path: str):
        from ui.file_drop_dialog import FileDropDialog
        FileDropDialog(self, file_path=path, on_task_created=self._on_ai_action)

    def _on_prompt(self, text: str):
        txt = text.lower().strip()
        if "urgent" in txt:
            self.task_panel.refresh(category_id=self.selected_category_id,
                                    priority_filter="urgent")
        elif "termin" in txt or "done" in txt:
            self.task_panel.refresh(category_id=self.selected_category_id,
                                    status_filter="done")
        elif "faire" in txt or "todo" in txt:
            self.task_panel.refresh(category_id=self.selected_category_id,
                                    status_filter="todo")
        else:
            self.task_panel.refresh(category_id=self.selected_category_id,
                                    keyword=text)

    # ── Mise a jour ───────────────────────────────────────────────────────────
    def _check_for_update(self):
        print("[Updater] Lancement verification...")
        def _run():
            try:
                from core.updater import check_for_update
                release = check_for_update()
                if release:
                    print(f"[Updater] Nouvelle version : v{release['version']}")
                    self.after(0, lambda: self._show_update_dialog(release))
                else:
                    print("[Updater] Deja a jour.")
            except Exception as e:
                import traceback
                print(f"[Updater] Erreur : {e}")
                traceback.print_exc()
        threading.Thread(target=_run, daemon=True).start()

    # ── Multi-ecrans ──────────────────────────────────────────────────────────
    def _get_screens(self) -> list:
        """Retourne la liste des ecrans via Win32 API."""
        import ctypes

        class RECT(ctypes.Structure):
            _fields_ = [
                ("left",   ctypes.c_long), ("top",    ctypes.c_long),
                ("right",  ctypes.c_long), ("bottom", ctypes.c_long),
            ]

        monitors = []

        def _callback(hMon, hdcMon, lpRect, lParam):
            r = ctypes.cast(lpRect, ctypes.POINTER(RECT)).contents
            monitors.append({
                "x":      r.left,
                "y":      r.top,
                "width":  r.right  - r.left,
                "height": r.bottom - r.top,
            })
            return True

        MonitorEnumProc = ctypes.WINFUNCTYPE(
            ctypes.c_bool,
            ctypes.c_ulong, ctypes.c_ulong,
            ctypes.POINTER(RECT),
            ctypes.c_double,
        )
        ctypes.windll.user32.EnumDisplayMonitors(
            None, None, MonitorEnumProc(_callback), 0)
        return monitors

    def _move_to_screen(self):
        """
        Teleporte QuickMind vers l ecran suivant en un clic.
        Evite completement le freeze du drag & drop entre ecrans.
        """
        screens = self._get_screens()
        if len(screens) < 2:
            print("[Screen] Un seul ecran detecte.")
            return

        # Position actuelle
        cur_x = self.winfo_x()
        cur_y = self.winfo_y()
        w     = self.winfo_width()
        h     = self.winfo_height()

        # Trouver l ecran actuel
        cur_idx = 0
        for i, s in enumerate(screens):
            if (s["x"] <= cur_x < s["x"] + s["width"] and
                    s["y"] <= cur_y < s["y"] + s["height"]):
                cur_idx = i
                break

        # Ecran suivant (rotation)
        nxt = screens[(cur_idx + 1) % len(screens)]

        # Centrer sur le nouvel ecran
        new_x = nxt["x"] + (nxt["width"]  - w) // 2
        new_y = nxt["y"] + (nxt["height"] - h) // 2

        # Teleportation instantanee — sans freeze !
        self.geometry(f"{w}x{h}+{new_x}+{new_y}")
        self.lift()   # remettre au premier plan
        print(f"[Screen] Ecran {cur_idx+1} → Ecran {(cur_idx+1)%len(screens)+1} "
              f"({nxt['width']}x{nxt['height']})")

    def _show_update_dialog(self, release: dict):
        try:
            from ui.update_dialog import UpdateDialog
            self.title("QuickMind  v" + _cfg["app"]["version"] +
                       f"  —  v{release['version']} disponible !")
            self.prompt_bar.show_update_badge(release["version"])
            self._update_dialog = UpdateDialog(self, release_info=release)
        except Exception as e:
            import traceback
            print(f"[Updater] Erreur dialog : {e}")
            traceback.print_exc()
