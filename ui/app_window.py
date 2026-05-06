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


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

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
        self._kanban_mode          = False

        # Sidebar
        self.sidebar = Sidebar(self, on_select=self._on_category_select)
        self.sidebar.grid(row=0, column=0, rowspan=2, sticky="nsw",
                          padx=(10,0), pady=10)

        # Task panel (liste)
        self.task_panel = TaskPanel(self)
        self.task_panel.grid(row=0, column=1, sticky="nsew",
                             padx=10, pady=(10,4))

        # Kanban panel (masque par defaut)
        self.kanban_panel = KanbanPanel(self)

        # IA Panel
        self.ai_panel = AIPanel(self, on_action_done=self._on_ai_action)

        # Barre basse
        self.prompt_bar = PromptBar(self,
            on_submit=self._on_prompt,
            on_toggle_ai=self._toggle_ai,
            on_outlook=self._open_outlook,
            on_toggle_kanban=self._toggle_kanban,
        )
        self.prompt_bar.grid(row=2, column=0, columnspan=2,
                             sticky="ew", padx=10, pady=(0,10))

        self.task_panel.refresh(category_id=None)

        # Verif mise a jour
        updater_cfg = _cfg.get("updater", {})
        if updater_cfg.get("enabled", True) and updater_cfg.get("check_on_startup", True):
            print("[Updater] Verification dans 3 secondes...")
            self.after(3000, self._check_for_update)

    def _on_category_select(self, cat_id):
        self.selected_category_id = cat_id
        if self._kanban_mode:
            self.kanban_panel.refresh(category_id=cat_id)
        else:
            self.task_panel.refresh(category_id=cat_id)

    def _toggle_kanban(self):
        """Bascule entre vue liste et vue Kanban."""
        self._kanban_mode = not self._kanban_mode
        if self._kanban_mode:
            self.task_panel.grid_forget()
            self.kanban_panel.grid(row=0, column=1, sticky="nsew",
                                   padx=10, pady=(10,4))
            self.kanban_panel.refresh(category_id=self.selected_category_id)
        else:
            self.kanban_panel.grid_forget()
            self.task_panel.grid(row=0, column=1, sticky="nsew",
                                 padx=10, pady=(10,4))
            self.task_panel.refresh(category_id=self.selected_category_id)

    def _toggle_ai(self):
        self._ai_visible = not self._ai_visible
        if self._ai_visible:
            self.ai_panel.grid(row=1, column=1, sticky="nsew",
                               padx=10, pady=(0,4))
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
