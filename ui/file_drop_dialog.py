"""
Dialog d analyse de fichier par IA.
S affiche apres selection ou glisser-deposer sur le bouton Analyser.
"""
import customtkinter as ctk
import threading
from pathlib import Path
from core.database import add_task, get_categories, init_db
from core.file_handler import save_attachment


PRIORITY_COLORS = {
    "urgent": "#FF4444",
    "high":   "#FF8C00",
    "normal": "#1E90FF",
    "low":    "#888888",
}

FILE_ICONS = {
    ".pdf":  "📕 PDF",
    ".docx": "📘 Word", ".doc": "📘 Word",
    ".xlsx": "📗 Excel", ".xls": "📗 Excel",
    ".txt":  "📄 Texte", ".md": "📄 Markdown", ".csv": "📊 CSV",
    ".eml":  "📧 Email", ".msg": "📧 Email Outlook",
    ".png":  "🖼️ Image", ".jpg": "🖼️ Image",
    ".jpeg": "🖼️ Image", ".gif": "🖼️ Image", ".bmp": "🖼️ Image",
}


class FileDropDialog(ctk.CTkToplevel):
    def __init__(self, master, file_path: str, on_task_created=None):
        super().__init__(master)
        self.file_path       = file_path
        self.on_task_created = on_task_created
        self._analysis       = None

        fname = Path(file_path).name
        self.title(f"Analyser : {fname}")
        self.geometry("620x620")
        self.minsize(520, 520)
        self.resizable(True, True)
        self.grab_set()

        init_db()
        cats = get_categories()
        self._cat_map   = {c.name: c.id for c in cats}
        self._cat_names = [c.name for c in cats]

        self._build(fname)
        self.after(300, self._start_analysis)

    def _build(self, fname: str):
        pad = {"padx": 20, "pady": 6}

        # Header
        ctk.CTkLabel(self,
            text="🤖  Analyse IA du fichier",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color="#1E90FF"
        ).pack(**pad)

        # Info fichier
        ext   = Path(self.file_path).suffix.lower()
        ftype = FILE_ICONS.get(ext, f"📎 {ext}")
        info  = ctk.CTkFrame(self, fg_color=("gray85","gray20"), corner_radius=8)
        info.pack(fill="x", padx=20, pady=4)
        ctk.CTkLabel(info,
            text=f"  Fichier : {fname}\n  Type    : {ftype}",
            font=ctk.CTkFont(family="Consolas", size=11),
            justify="left", anchor="w"
        ).pack(padx=10, pady=8, fill="x")

        # Résumé IA
        ctk.CTkLabel(self, text="Résumé IA :", anchor="w",
            font=ctk.CTkFont(size=11, weight="bold")
        ).pack(fill="x", padx=20, pady=(6,0))
        self._summary_box = ctk.CTkTextbox(self, height=70,
            font=ctk.CTkFont(size=11), state="disabled", wrap="word")
        self._summary_box.pack(fill="x", padx=20, pady=(2,4))

        # Actions détectées
        ctk.CTkLabel(self, text="Actions détectées :", anchor="w",
            font=ctk.CTkFont(size=11, weight="bold")
        ).pack(fill="x", padx=20)
        self._actions_box = ctk.CTkTextbox(self, height=80,
            font=ctk.CTkFont(size=11), state="disabled", wrap="word")
        self._actions_box.pack(fill="x", padx=20, pady=(2,6))

        # Titre
        ctk.CTkLabel(self, text="Titre de la tâche :", anchor="w").pack(fill="x", padx=20)
        self._title_e = ctk.CTkEntry(self, height=34)
        self._title_e.pack(fill="x", padx=20, pady=(2,6))

        # Catégorie + Priorité
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=(0,6))
        row.grid_columnconfigure(0, weight=1)
        row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(row, text="Catégorie :", anchor="w").grid(
            row=0, column=0, sticky="w", padx=(0,8))
        self._cat_var = ctk.StringVar(
            value=self._cat_names[0] if self._cat_names else "")
        ctk.CTkOptionMenu(row, values=self._cat_names,
            variable=self._cat_var, height=32
        ).grid(row=1, column=0, sticky="ew", padx=(0,8))

        ctk.CTkLabel(row, text="Priorité :", anchor="w").grid(
            row=0, column=1, sticky="w")
        self._prio_var = ctk.StringVar(value="normal")
        ctk.CTkSegmentedButton(row,
            values=["low","normal","high","urgent"],
            variable=self._prio_var
        ).grid(row=1, column=1, sticky="ew")

        # Joindre le fichier
        self._attach_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(self,
            text="📎 Joindre le fichier à la tâche",
            variable=self._attach_var,
            font=ctk.CTkFont(size=12)
        ).pack(anchor="w", padx=20, pady=4)

        # Statut
        self._status_label = ctk.CTkLabel(self,
            text="⏳ Analyse Mistral en cours...",
            text_color="#FFD700",
            font=ctk.CTkFont(size=11))
        self._status_label.pack(padx=20, pady=(4,2))

        # Boutons
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(6,14))
        self._create_btn = ctk.CTkButton(
            btn_row, text="✅  Créer la tâche", height=38,
            fg_color="#2a5a2a", hover_color="#1a4a1a",
            font=ctk.CTkFont(size=13, weight="bold"),
            state="disabled",
            command=self._create_task
        )
        self._create_btn.pack(side="left", expand=True, padx=(0,6))
        ctk.CTkButton(btn_row, text="Annuler", height=38,
            fg_color="gray30", hover_color="gray20",
            command=self.destroy
        ).pack(side="right", expand=True, padx=(6,0))

    def _set_text(self, widget, text: str):
        widget.configure(state="normal")
        widget.delete("0.0", "end")
        widget.insert("0.0", text)
        widget.configure(state="disabled")

    def _start_analysis(self):
        def _run():
            try:
                from agents.file_analyzer import analyze_with_ai
                result = analyze_with_ai(self.file_path, self._cat_names)
                self.after(0, lambda: self._on_done(result))
            except Exception as e:
                self.after(0, lambda: self._on_error(str(e)))
        threading.Thread(target=_run, daemon=True).start()

    def _on_done(self, result: dict):
        self._analysis = result
        self._title_e.delete(0, "end")
        self._title_e.insert(0, result.get("title", ""))
        summary = result.get("summary") or result.get("description","")[:200]
        self._set_text(self._summary_box, summary)
        actions = result.get("actions", [])
        self._set_text(self._actions_box,
            "\n".join(f"  • {a}" for a in actions) if actions
            else "Aucune action détectée.")
        if result.get("category") in self._cat_map:
            self._cat_var.set(result["category"])
        prio = result.get("priority", "normal")
        if prio in ["low","normal","high","urgent"]:
            self._prio_var.set(prio)
        self._status_label.configure(
            text=f"✅ Analyse terminée  |  Priorité suggérée : {prio}",
            text_color=PRIORITY_COLORS.get(prio, "#1E90FF")
        )
        self._create_btn.configure(state="normal")

    def _on_error(self, error: str):
        self._set_text(self._summary_box, f"Erreur : {error}")
        self._set_text(self._actions_box, "")
        self._status_label.configure(
            text="⚠️ Analyse echouee — creez la tache manuellement",
            text_color="#FF8C00"
        )
        fname = Path(self.file_path).name
        self._title_e.insert(0, f"Tache : {fname}")
        self._create_btn.configure(state="normal")

    def _create_task(self):
        title = self._title_e.get().strip()
        if not title:
            return
        cat_id   = self._cat_map.get(self._cat_var.get())
        priority = self._prio_var.get()
        desc_parts = []
        if self._analysis:
            if self._analysis.get("summary"):
                desc_parts.append(self._analysis["summary"])
            if self._analysis.get("actions"):
                desc_parts.append("\nActions identifiees :")
                for a in self._analysis["actions"]:
                    desc_parts.append(f"  - {a}")
            desc_parts.append(f"\nFichier source : {self.file_path}")
        task = add_task(
            title=title,
            description="\n".join(desc_parts),
            category_id=cat_id,
            priority=priority,
        )
        if self._attach_var.get():
            try:
                new_path = save_attachment(self.file_path, task.id)
                from core.database import set_task_attachments
                set_task_attachments(task.id, [new_path])
            except Exception as e:
                print(f"[FileAnalyzer] Erreur PJ : {e}")
        self.destroy()
        if self.on_task_created:
            self.on_task_created()
