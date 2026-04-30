import shutil
import yaml
from pathlib import Path

_cfg_path = Path(__file__).parent.parent / "config.yaml"
with open(_cfg_path, "r", encoding="utf-8") as f:
    _cfg = yaml.safe_load(f)

ATT_DIR = Path(_cfg["attachments"]["path"])
ATT_DIR.mkdir(parents=True, exist_ok=True)


def save_attachment(src_path: str, task_id: int) -> str:
    """Copie le fichier dans le dossier attachments et retourne le nouveau path."""
    src = Path(src_path)
    dest = ATT_DIR / f"task_{task_id}_{src.name}"
    shutil.copy2(src, dest)
    return str(dest)

def open_attachment(path: str):
    import os
    os.startfile(path)
