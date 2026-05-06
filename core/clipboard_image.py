"""
Gestion des images depuis le presse-papier Windows.
Detecte, sauvegarde et genere une miniature.
"""
import os
import yaml
from pathlib import Path
from datetime import datetime


_cfg_path = Path(__file__).parent.parent / "config.yaml"
with open(_cfg_path, "r", encoding="utf-8") as f:
    _cfg = yaml.safe_load(f)

ATT_DIR = Path(_cfg["attachments"]["path"])
ATT_DIR.mkdir(parents=True, exist_ok=True)

THUMB_SIZE = (200, 150)   # taille miniature


def has_image_in_clipboard() -> bool:
    """Verifie si le presse-papier contient une image."""
    try:
        from PIL import ImageGrab
        img = ImageGrab.grabclipboard()
        return img is not None
    except Exception:
        return False


def save_clipboard_image(task_id: int) -> tuple[str, str] | None:
    """
    Sauvegarde l image du presse-papier.
    Retourne (chemin_image, chemin_miniature) ou None si pas d image.
    """
    try:
        from PIL import ImageGrab, Image

        img = ImageGrab.grabclipboard()
        if img is None:
            return None

        # Dossier de la tache
        task_dir = ATT_DIR / f"task_{task_id}"
        task_dir.mkdir(parents=True, exist_ok=True)

        # Nom de fichier avec timestamp
        ts    = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"image_{ts}.png"
        path  = task_dir / fname
        img.save(str(path), "PNG")

        # Miniature
        thumb_fname = f"thumb_{ts}.png"
        thumb_path  = task_dir / thumb_fname
        thumb = img.copy()
        thumb.thumbnail(THUMB_SIZE)
        thumb.save(str(thumb_path), "PNG")

        print(f"[Clipboard] Image sauvegardee : {path}")
        return str(path), str(thumb_path)

    except Exception as e:
        print(f"[Clipboard] Erreur : {e}")
        return None


def get_thumbnail(image_path: str) -> object | None:
    """Charge une miniature PIL pour affichage dans Tkinter."""
    try:
        from PIL import Image, ImageTk
        img = Image.open(image_path)
        img.thumbnail(THUMB_SIZE)
        return ImageTk.PhotoImage(img)
    except Exception as e:
        print(f"[Clipboard] Erreur miniature : {e}")
        return None
