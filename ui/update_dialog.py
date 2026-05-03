"""
Dialog de mise a jour QuickMind.
Fenetre redimensionnable avec zone d erreur complete visible.
"""
import customtkinter as ctk
from core.updater import download_and_install, restart_app


class UpdateDialog(ctk.CTkToplevel):
    def __init__(self, master, release_info: dict):
        super().__init__(master)
        self.release_info = release_info
        self.title("Mise a jour disponible")
        self.geometry("600x500")
        self.minsize(500, 420)
        self.resizable(True, True)
        self.grab_set()
        self._build()

    def _build(self):
        pad = {"padx": 20, "pady": 6}

        ctk.CTkLabel(self,
            text="Nouvelle version disponible !",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#1E90FF"
        ).pack(**pad)

        # Info version
        info_frame = ctk.CTkFrame(self, fg_color=("gray85","gray20"), corner_radius=8)
        info_frame.pack(fill="x", padx=20, pady=4)
        ctk.CTkLabel(info_frame,
            text=(
                f"  Version actuelle : v{self._get_current()}\n"
                f"  Nouvelle version : v{self.release_info['version']}\n"
                f"  Publiee le       : {self.release_info['published']}"
            ),
            font=ctk.CTkFont(family="Consolas", size=12),
            justify="left", anchor="w"
        ).pack(padx=12, pady=8, fill="x")

        # Notes de version
        ctk.CTkLabel(self, text="Notes de version :",
            anchor="w", font=ctk.CTkFont(size=12, weight="bold")
        ).pack(fill="x", padx=20, pady=(6,2))

        notes_box = ctk.CTkTextbox(self, height=110,
            font=ctk.CTkFont(family="Consolas", size=11))
        notes_box.pack(fill="x", padx=20, pady=(0,6))
        body = self.release_info.get("body","") or "Aucune note de version."
        notes_box.insert("0.0", body)
        notes_box.configure(state="disabled")

        # Zone statut scrollable
        ctk.CTkLabel(self, text="Statut :",
            anchor="w", font=ctk.CTkFont(size=11, weight="bold")
        ).pack(fill="x", padx=20, pady=(4,0))

        self._status_box = ctk.CTkTextbox(
            self, height=60,
            font=ctk.CTkFont(family="Consolas", size=11),
            state="disabled", wrap="word", text_color="gray"
        )
        self._status_box.pack(fill="x", padx=20, pady=(2,6))

        # Barre de progression
        self._progress = ctk.CTkProgressBar(self, height=14, corner_radius=6)
        self._progress.pack(fill="x", padx=20, pady=(0,8))
        self._progress.set(0)

        # Boutons
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(4,14))

        self._update_btn = ctk.CTkButton(
            btn_row,
            text="Mettre a jour maintenant",
            height=38,
            fg_color="#1E90FF", hover_color="#0060CC",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._start_update
        )
        self._update_btn.pack(side="left", expand=True, padx=(0,6))

        ctk.CTkButton(
            btn_row, text="Plus tard", height=38,
            fg_color="gray30", hover_color="gray20",
            command=self.destroy
        ).pack(side="right", expand=True, padx=(6,0))

    def _get_current(self) -> str:
        import yaml
        from pathlib import Path
        cfg = Path(__file__).parent.parent / "config.yaml"
        with open(cfg, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)["app"]["version"]

    def _set_status(self, msg: str, color: str = "gray"):
        self._status_box.configure(state="normal")
        self._status_box.delete("0.0", "end")
        self._status_box.insert("0.0", msg)
        self._status_box.configure(state="disabled", text_color=color)
        self._status_box.see("end")

    def _start_update(self):
        self._update_btn.configure(state="disabled", text="Installation...")
        self._set_status("Demarrage de la mise a jour...", "gray")

        def on_progress(msg, pct):
            self.after(0, lambda: (
                self._set_status(msg, "gray"),
                self._progress.set(pct / 100)
            ))

        def on_done():
            self.after(0, self._on_done)

        def on_error(err):
            self.after(0, lambda: self._on_error(err))

        # Passe new_version pour que config.yaml soit mis a jour
        download_and_install(
            zip_url=self.release_info["zip_url"],
            asset_id=self.release_info.get("asset_id"),
            new_version=self.release_info["version"],   # ← nouveau
            on_progress=on_progress,
            on_done=on_done,
            on_error=on_error,
        )

    def _on_done(self):
        self._set_status(
            "Installation terminee ! Redemarrage dans 2 secondes...",
            "#32CD32"
        )
        self._progress.set(1.0)
        self.after(2000, restart_app)

    def _on_error(self, err: str):
        self._set_status(f"ERREUR :\n{err}", "#FF4444")
        self._update_btn.configure(state="normal", text="Reessayer")
        print(f"[Updater] Erreur : {err}")
