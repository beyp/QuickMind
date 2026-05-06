import customtkinter as ctk
import tkinter.filedialog as fd
from pathlib import Path


class PromptBar(ctk.CTkFrame):
    def __init__(self, master, on_submit, on_toggle_ai=None,
                 on_outlook=None, on_toggle_kanban=None,
                 kanban_active=False):
        super().__init__(master, height=48, corner_radius=10)
        self.on_submit        = on_submit
        self.on_toggle_ai     = on_toggle_ai
        self.on_outlook       = on_outlook
        self.on_toggle_kanban = on_toggle_kanban
        self._update_btn      = None
        self._kanban_active   = kanban_active  # etat initial
        self._build()

    def _build(self):
        self.grid_columnconfigure(4, weight=1)

        # Bouton IA
        self._ai_btn = ctk.CTkButton(self, text="🤖 IA",
            width=70, height=36,
            fg_color="#1a3a5c", hover_color="#1E90FF",
            command=self._toggle_ai)
        self._ai_btn.grid(row=0, column=0, padx=(10, 4), pady=6)

        # Bouton Outlook
        ctk.CTkButton(self, text="📬 Outlook",
            width=100, height=36,
            fg_color="#0078D4", hover_color="#005a9e",
            command=self._open_outlook
        ).grid(row=0, column=1, padx=(0, 4), pady=6)

        # Bouton Analyser
        self._analyze_btn = ctk.CTkButton(self, text="📁 Analyser",
            width=110, height=36,
            fg_color="#4a2a6a", hover_color="#7B2FBE",
            command=self._open_file_picker)
        self._analyze_btn.grid(row=0, column=2, padx=(0, 4), pady=6)
        self._setup_button_drop()

        # Bouton Kanban — couleur selon etat initial
        self._kanban_btn = ctk.CTkButton(self,
            text="📋 Liste" if self._kanban_active else "📊 Kanban",
            width=100, height=36,
            fg_color="#2a5a3a" if self._kanban_active else "#1a3a2a",
            hover_color="#3a7a4a",
            command=self._toggle_kanban)
        self._kanban_btn.grid(row=0, column=3, padx=(0, 6), pady=6)

        # Champ de recherche
        self._entry = ctk.CTkEntry(self, height=36,
            placeholder_text="Recherche rapide : urgent, a faire, rapport...",
            font=ctk.CTkFont(size=12))
        self._entry.grid(row=0, column=4, sticky="ew", padx=(0, 8), pady=6)
        self._entry.bind("<Return>", lambda e: self._submit())

        ctk.CTkButton(self, text="Chercher", width=90, height=36,
            command=self._submit).grid(row=0, column=5, padx=(0, 6), pady=6)

        # Badge mise a jour (masque par defaut)
        self._update_btn = ctk.CTkButton(self, text="", width=0, height=36,
            fg_color="#FF8C00", hover_color="#CC6600",
            font=ctk.CTkFont(size=11, weight="bold"))

    def _setup_button_drop(self):
        try:
            import windnd
            def _on_drop(files):
                for f in files:
                    try:
                        path = f.decode("utf-8") if isinstance(f, bytes) else str(f)
                        if Path(path.strip()).exists():
                            self.after(0, lambda p=path.strip(): self._open_analysis(p))
                            self.after(0, lambda: self._analyze_btn.configure(
                                fg_color="#7B2FBE"))
                            self.after(1000, lambda: self._analyze_btn.configure(
                                fg_color="#4a2a6a"))
                            break
                    except Exception:
                        pass
            windnd.hook_dropfiles(self._analyze_btn, func=_on_drop)
            print("[DragDrop] Drag & drop actif sur le bouton Analyser.")
        except Exception as e:
            print(f"[DragDrop] Non disponible : {e}")

    def _toggle_kanban(self):
        self._kanban_active = not self._kanban_active
        self._kanban_btn.configure(
            text="📋 Liste" if self._kanban_active else "📊 Kanban",
            fg_color="#2a5a3a" if self._kanban_active else "#1a3a2a"
        )
        if self.on_toggle_kanban:
            self.on_toggle_kanban()

    def _open_file_picker(self):
        path = fd.askopenfilename(
            title="Choisir un fichier a analyser par IA",
            filetypes=[
                ("Fichiers supportes",
                 "*.pdf *.docx *.doc *.xlsx *.xls *.txt *.md "
                 "*.csv *.eml *.msg *.png *.jpg *.jpeg *.gif *.bmp"),
                ("Tous", "*.*"),
            ]
        )
        if path:
            self._open_analysis(path)

    def _open_analysis(self, path: str):
        from ui.file_drop_dialog import FileDropDialog
        FileDropDialog(self.master, file_path=path,
                       on_task_created=self._on_file_done)

    def _on_file_done(self):
        if hasattr(self.master, "_on_ai_action"):
            self.master._on_ai_action()

    def show_update_badge(self, version: str):
        self._update_btn.configure(
            text=f"⬆️ v{version}", width=90,
            command=lambda: self._on_update_click(version))
        self._update_btn.grid(row=0, column=6, padx=(0, 10), pady=6)

    def _on_update_click(self, version: str):
        from core.updater import check_for_update
        from ui.update_dialog import UpdateDialog
        release = check_for_update()
        if release:
            UpdateDialog(self.master, release_info=release)

    def _submit(self):
        text = self._entry.get().strip()
        if text:
            self.on_submit(text)
            self._entry.delete(0, "end")

    def _toggle_ai(self):
        if self.on_toggle_ai:
            self.on_toggle_ai()
            current = self._ai_btn.cget("fg_color")
            self._ai_btn.configure(
                fg_color="#1E90FF" if current == "#1a3a5c" else "#1a3a5c")

    def _open_outlook(self):
        if self.on_outlook:
            self.on_outlook()
