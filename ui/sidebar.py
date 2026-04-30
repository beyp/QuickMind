import customtkinter as ctk
from core.database import get_categories, add_category, delete_category
import tkinter.simpledialog as sd
import tkinter.colorchooser as cc


def _separator(parent):
    """Remplace CTkSeparator (absent de certaines versions)."""
    ctk.CTkFrame(parent, height=1, fg_color=("gray70", "gray30")).pack(
        fill="x", padx=8, pady=2
    )


class Sidebar(ctk.CTkFrame):
    def __init__(self, master, on_select):
        super().__init__(master, width=200, corner_radius=12)
        self.on_select = on_select
        self._build()

    def _build(self):
        # Titre
        ctk.CTkLabel(
            self, text="📂  Catégories",
            font=ctk.CTkFont(size=15, weight="bold")
        ).pack(padx=12, pady=(14, 6))

        _separator(self)

        # Bouton "Toutes"
        self._btn_all = ctk.CTkButton(
            self, text="🗂  Toutes les tâches",
            fg_color="transparent",
            hover_color=("#dce3ee", "#2a2d3e"),
            anchor="w",
            command=lambda: self.on_select(None)
        )
        self._btn_all.pack(fill="x", padx=8, pady=(6, 2))

        # Frame scrollable pour les catégories
        self._cat_frame = ctk.CTkScrollableFrame(self, label_text="", height=350)
        self._cat_frame.pack(fill="both", expand=True, padx=8, pady=4)

        self._refresh_categories()

        # Bouton ajouter catégorie
        ctk.CTkButton(
            self, text="＋  Catégorie",
            height=30, corner_radius=8,
            command=self._add_category
        ).pack(fill="x", padx=8, pady=(4, 12))

    def _refresh_categories(self):
        for w in self._cat_frame.winfo_children():
            w.destroy()

        cats = get_categories()
        for cat in cats:
            row = ctk.CTkFrame(self._cat_frame, fg_color="transparent")
            row.pack(fill="x", pady=2)

            dot = ctk.CTkLabel(row, text="●", text_color=cat.color, width=18)
            dot.pack(side="left")

            btn = ctk.CTkButton(
                row, text=cat.name,
                fg_color="transparent",
                hover_color=("#dce3ee", "#2a2d3e"),
                anchor="w",
                command=lambda cid=cat.id: self.on_select(cid)
            )
            btn.pack(side="left", fill="x", expand=True)

            del_btn = ctk.CTkButton(
                row, text="✕", width=24, height=24,
                fg_color="transparent", hover_color="#550000",
                text_color="#888",
                command=lambda cid=cat.id: self._delete_category(cid)
            )
            del_btn.pack(side="right")

    def _add_category(self):
        name = sd.askstring("Nouvelle catégorie", "Nom de la catégorie :")
        if not name:
            return
        color_result = cc.askcolor(title="Choisir une couleur")
        color = color_result[1] if color_result and color_result[1] else "#1E90FF"
        add_category(name.strip(), color)
        self._refresh_categories()

    def _delete_category(self, cat_id: int):
        delete_category(cat_id)
        self._refresh_categories()
        self.on_select(None)
