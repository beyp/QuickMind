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

        # Fix redraw multi-ecrans
        try:
            ctk.deactivate_automatic_dpi_awareness()
        except Exception:
            pass
        # Appliquer DPI+font_scale au demarrage (sans toucher taille/position)

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

    def _get_screen_dpi(self) -> float:
        """Recupere le DPI reel de l ecran actuel."""
        try:
            import ctypes
            hwnd = self.winfo_id()
            hmon = ctypes.windll.user32.MonitorFromWindow(hwnd, 2)
            dpi_x = ctypes.c_uint()
            dpi_y = ctypes.c_uint()
            ctypes.windll.shcore.GetDpiForMonitor(
                hmon, 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y))
            factor = dpi_x.value / 96.0
            print(f"[DPI] DPI={dpi_x.value} factor={factor:.2f}")
            return round(factor, 2)
        except Exception as e:
            print(f"[DPI] Fallback 1.0 : {e}")
            return 1.0

    def _apply_dpi_scaling_only(self):
        """
        Au demarrage : le scaling a deja ete applique dans main.py.
        Cette methode ne fait rien — conservee pour compatibilite.
        """
        print("[DPI] Scaling pre-applique dans main.py — OK")

    def _apply_screen_scaling(self):
        """
        Appele APRES un basculement d ecran.
        Recalcule le scaling si le nouvel ecran a un DPI different.
        Minimal pour rester fluide : on ne change le scaling QUE si le DPI change.
        """
        factor     = self._get_screen_dpi()
        font_scale = _cfg.get("app", {}).get("font_scale", 1.2)
        new_widget = round(factor * font_scale, 2)
        new_window = round(factor, 2)

        try:
            import customtkinter as ctk
            # Lire le scaling actuel
            current = ctk.ScalingTracker.get_widget_scaling(self)
            if abs(current - new_widget) > 0.05:
                # DPI different → mettre a jour (provoque un redraw)
                ctk.set_widget_scaling(new_widget)
                ctk.set_window_scaling(new_window)
                print(f"[DPI] Basculement : {current:.2f} -> {new_widget:.2f}")
            else:
                print(f"[DPI] Meme DPI ({new_widget:.2f}) — pas de redraw")
        except Exception as e:
            print(f"[DPI] Erreur basculement scaling : {e}")

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

    def _get_screen_dpi(self) -> float:
        """Recupere le DPI reel de l ecran actuel."""
        try:
            import ctypes
            hwnd = self.winfo_id()
            hmon = ctypes.windll.user32.MonitorFromWindow(hwnd, 2)
            dpi_x = ctypes.c_uint()
            dpi_y = ctypes.c_uint()
            ctypes.windll.shcore.GetDpiForMonitor(
                hmon, 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y))
            factor = dpi_x.value / 96.0
            print(f"[DPI] DPI={dpi_x.value} factor={factor:.2f}")
            return round(factor, 2)
        except Exception as e:
            print(f"[DPI] Fallback 1.0 : {e}")
            return 1.0

    def _apply_dpi_scaling_only(self):
        """
        Au demarrage : le scaling a deja ete applique dans main.py.
        Cette methode ne fait rien — conservee pour compatibilite.
        """
        print("[DPI] Scaling pre-applique dans main.py — OK")

    def _apply_screen_scaling(self):
        """
        Appele APRES un basculement d ecran.
        Applique le DPI + font_scale du nouvel ecran via CustomTkinter.
        Le centrage a deja ete fait dans _move_to_screen.
        """
        factor     = self._get_screen_dpi()
        font_scale = _cfg.get("app", {}).get("font_scale", 1.2)
        final      = round(factor * font_scale, 2)
        try:
            ctk.set_widget_scaling(final)
            ctk.set_window_scaling(factor)
            print(f"[DPI] Post-basculement : widget={final} window={factor}")
        except Exception as e:
            print(f"[DPI] Erreur scaling : {e}")
            try:
                self.tk.call("tk", "scaling", final)
            except Exception:
                pass

    def _move_to_screen(self):
        """
        Teleporte QuickMind vers l ecran suivant.
        Strategie plein ecran :
          - Si zoomed : on teleporte DIRECTEMENT en plein ecran sur l autre ecran
            sans passer par normal (evite tous les redraws intermediaires)
          - Si normal : on teleporte a 80% centre
        """
        screens = self._get_screens()
        if len(screens) < 2:
            print("[Screen] Un seul ecran detecte.")
            return

        is_zoomed = self.state() == "zoomed"

        if is_zoomed:
            # ── Plein ecran → plein ecran sur l autre ecran ───────────────────
            # Detecter l ecran actuel via la position sauvegardee
            # (winfo_x en mode zoomed retourne la position avant maximisation)
            # On utilise le centre de l ecran actuel comme reference
            screens_sorted = screens

            # Trouver sur quel ecran on est en mode zoomed
            # En mode zoomed, winfo_x/y peuvent etre negatifs ou incorrects
            # On utilise GetCursorPos pour savoir ou est la souris
            try:
                import ctypes
                class POINT(ctypes.Structure):
                    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
                pt = POINT()
                ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
                mouse_x, mouse_y = pt.x, pt.y
            except Exception:
                mouse_x = self.winfo_x() + self.winfo_width()  // 2
                mouse_y = self.winfo_y() + self.winfo_height() // 2

            cur_idx = 0
            for i, s in enumerate(screens):
                if (s["x"] <= mouse_x < s["x"] + s["width"] and
                        s["y"] <= mouse_y < s["y"] + s["height"]):
                    cur_idx = i
                    break

            nxt_idx = (cur_idx + 1) % len(screens)
            nxt     = screens[nxt_idx]

            # Teleporter en plein ecran sur l ecran cible :
            # 1. Quitter zoomed SILENCIEUSEMENT (withdraw masque la fenetre)
            self.withdraw()
            self.state("normal")
            # 2. Positionner sur l ecran cible
            self.geometry(
                f"{nxt['width']}x{nxt['height']}"
                f"+{nxt['x']}+{nxt['y']}"
            )
            # 3. Remettre en plein ecran DIRECTEMENT
            self.deiconify()
            self.state("zoomed")

            print(f"[Screen] Zoomed Ecran {cur_idx+1} -> Ecran {nxt_idx+1} "
                  f"({nxt['width']}x{nxt['height']})")

        else:
            # ── Mode normal → 80% centre sur l ecran suivant ──────────────────
            self.update_idletasks()

            win_cx = self.winfo_x() + self.winfo_width()  // 2
            win_cy = self.winfo_y() + self.winfo_height() // 2

            cur_idx = 0
            for i, s in enumerate(screens):
                if (s["x"] <= win_cx < s["x"] + s["width"] and
                        s["y"] <= win_cy < s["y"] + s["height"]):
                    cur_idx = i
                    break

            nxt_idx = (cur_idx + 1) % len(screens)
            nxt     = screens[nxt_idx]

            new_w = int(nxt["width"]  * 0.80)
            new_h = int(nxt["height"] * 0.80)
            new_x = nxt["x"] + (nxt["width"]  - new_w) // 2
            new_y = nxt["y"] + (nxt["height"] - new_h) // 2

            self.geometry(f"{new_w}x{new_h}+{new_x}+{new_y}")
            self.lift()
            print(f"[Screen] Normal Ecran {cur_idx+1} -> Ecran {nxt_idx+1} | "
                  f"{new_w}x{new_h} centre")

        # Appliquer le scaling DPI uniquement si l ecran a un DPI different
        self.after(300, self._apply_screen_scaling)

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
