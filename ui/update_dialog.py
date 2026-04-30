"""
Dialog de mise à jour QuickMind.
S affiche quand une nouvelle version est détectée.
"""
import customtkinter as ctk
from core.updater import download_and_install, restart_app


class UpdateDialog(ctk.CTkToplevel):
    """
    Fenêtre de notification de mise à jour avec barre de progression.
    """
    def __init__(self, master, release_info: dict):
        super().__init__(master)
        self.release_info = release_info
        self.title("⬆️  Mise à jour disponible")
        self.geometry("520x400")
        self.resizable(False, False)
        self.grab_set()
        self._build()

    def _build(self):
        pad = {"padx": 20, "pady": 8}

        # ── Header ────────────────────────────────────────────────────────
        ctk.CTkLabel(self,
            text="⬆️  Nouvelle version disponible !",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#1E90FF"
        ).pack(**pad)

        # ── Info version ──────────────────────────────────────────────────
        version_frame = ctk.CTkFrame(self, fg_color=("gray85","gray20"), corner_radius=8)
        version_frame.pack(fill="x", padx=20, pady=4)

        ctk.CTkLabel(version_frame,
            text=(
                f"  Version actuelle : v{self._get_current()}\n"
                f"  Nouvelle version : v{self.release_info['version']}\n"
                f"  Publiée le       : {self.release_info['published']}"
            ),
            font=ctk.CTkFont(family="Consolas", size=12),
            justify="left", anchor="w"
        ).pack(padx=12, pady=10, fill="x")

        # ── Notes de version ──────────────────────────────────────────────
        ctk.CTkLabel(self, text="Notes de version :",
            anchor="w", font=ctk.CTkFont(size=12, weight="bold")
        ).pack(fill="x", padx=20, pady=(8,2))

        notes_box = ctk.CTkTextbox(self, height=100,
            font=ctk.CTkFont(family="Consolas", size=11))
        notes_box.pack(fill="x", padx=20, pady=(0,8))
        body = self.release_info.get("body","") or "Aucune note de version."
        notes_box.insert("0.0", body)
        notes_box.configure(state="disabled")

        # ── Barre de progression ──────────────────────────────────────────
        self._progress_label = ctk.CTkLabel(self, text="",
            font=ctk.CTkFont(size=11), text_color="gray")
        self._progress_label.pack(padx=20, pady=(0,2))

        self._progress = ctk.CTkProgressBar(self, height=14, corner_radius=6)
        self._progress.pack(fill="x", padx=20, pady=(0,8))
        self._progress.set(0)

        # ── Boutons ───────────────────────────────────────────────────────
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(4,16))

        self._update_btn = ctk.CTkButton(
            btn_row,
            text="⬆️  Mettre à jour maintenant",
            height=38,
            fg_color="#1E90FF", hover_color="#0060CC",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._start_update
        )
        self._update_btn.pack(side="left", expand=True, padx=(0,6))

        ctk.CTkButton(
            btn_row,
            text="Plus tard",
            height=38,
            fg_color="gray30", hover_color="gray20",
            command=self.destroy
        ).pack(side="right", expand=True, padx=(6,0))

    def _get_current(self) -> str:
        import yaml
        from pathlib import Path
        cfg_path = Path(__file__).parent.parent / "config.yaml"
        with open(cfg_path,"r",encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        return cfg["app"]["version"]

    def _start_update(self):
        """Lance le téléchargement et l installation."""
        self._update_btn.configure(state="disabled", text="Installation...")

        def on_progress(msg: str, pct: int):
            self.after(0, lambda: self._on_progress(msg, pct))

        def on_done():
            self.after(0, self._on_done)

        def on_error(err: str):
            self.after(0, lambda: self._on_error(err))

        download_and_install(
            zip_url=self.release_info["zip_url"],
            on_progress=on_progress,
            on_done=on_done,
            on_error=on_error,
        )

    def _on_progress(self, msg: str, pct: int):
        self._progress_label.configure(text=msg)
        self._progress.set(pct / 100)

    def _on_done(self):
        self._progress_label.configure(
            text="✅ Installation terminée ! Redémarrage...",
            text_color="#32CD32"
        )
        self._progress.set(1.0)
        self.after(1500, restart_app)

    def _on_error(self, err: str):
        self._progress_label.configure(
            text=f"❌ Erreur : {err}",
            text_color="#FF4444"
        )
        self._update_btn.configure(state="normal", text="⬆️  Réessayer")
