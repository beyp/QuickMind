"""
build_release.py — Genere le ZIP propre pour la release GitHub de QuickMind.
Usage : python build_release.py

Le ZIP genere est pret a uploader directement sur GitHub Releases.
- Sans .git, sans data/, sans .env, sans __pycache__
- Nomme automatiquement selon la version dans config.yaml
"""
import os
import sys
import yaml
import zipfile
import shutil
from pathlib import Path
from datetime import datetime

# ── Configuration ─────────────────────────────────────────────────────────────
APP_DIR  = Path(__file__).parent.resolve()
CFG_PATH = APP_DIR / "config.yaml"

# Dossiers et fichiers a EXCLURE du ZIP de release
EXCLUDE = {
    # Secrets et donnees locales
    ".env",
    "data",
    # Git
    ".git",
    # Build
    "__pycache__",
    ".pyc",
    ".pyo",
    # Temporaires updater
    "_update.zip",
    "_update_tmp",
    "_bk_data",
    "_bk_config.yaml",
    # Outils de dev (pas necessaires pour l utilisateur)
    "debug_update.py",
    "build_release.py",   # ce script lui-meme
    # VS Code
    ".vscode",
    # Distributions precedentes
    "dist",
    "build",
    "*.spec",
}

EXCLUDE_EXTENSIONS = {".pyc", ".pyo", ".db"}


def should_exclude(path: Path) -> bool:
    """Retourne True si le fichier/dossier doit etre exclu du ZIP."""
    name = path.name

    # Extensions exclues
    if path.suffix in EXCLUDE_EXTENSIONS:
        return True

    # Noms exacts exclus
    if name in EXCLUDE:
        return True

    # Patterns (ex: *.spec)
    for pattern in EXCLUDE:
        if pattern.startswith("*") and name.endswith(pattern[1:]):
            return True

    # __pycache__ partout
    if "__pycache__" in path.parts:
        return True

    # .git partout
    if ".git" in path.parts:
        return True

    # Fichiers temporaires updater
    if name.startswith("_bk_") or name.startswith("_update"):
        return True

    return False


def build_zip():
    # ── Lire la version ───────────────────────────────────────────────────────
    if not CFG_PATH.exists():
        print("ERREUR : config.yaml introuvable !")
        sys.exit(1)

    with open(CFG_PATH, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    version    = cfg["app"]["version"]
    app_name   = cfg["app"].get("name", "QuickMind")
    zip_name   = f"{app_name}_v{version}.zip"
    zip_path   = APP_DIR / zip_name

    print(f"")
    print(f"  ⚡ {app_name} — Build Release")
    print(f"  Version  : v{version}")
    print(f"  ZIP      : {zip_name}")
    print(f"  Source   : {APP_DIR}")
    print(f"")

    # ── Verifier que github_token est vide ────────────────────────────────────
    token = cfg.get("updater", {}).get("github_token", "")
    if token and token.startswith("ghp_"):
        print("  ERREUR : github_token non vide dans config.yaml !")
        print("  Videz-le avant de builder : github_token: """)
        print("  Le token doit etre dans .env uniquement.")
        sys.exit(1)

    # ── Supprimer l ancien ZIP si existant ────────────────────────────────────
    if zip_path.exists():
        zip_path.unlink()
        print(f"  Ancien ZIP supprime.")

    # ── Construire le ZIP ─────────────────────────────────────────────────────
    file_count = 0
    skip_count = 0

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in sorted(APP_DIR.rglob("*")):
            # Calculer le chemin relatif
            rel = item.relative_to(APP_DIR)

            # Verifier l exclusion
            if should_exclude(item) or any(
                should_exclude(APP_DIR / part)
                for part in rel.parts
            ):
                skip_count += 1
                continue

            if item.is_file():
                # Chemin dans le ZIP : QuickMind/fichier.py
                arc_name = f"{app_name}/{rel}"
                zf.write(item, arc_name)
                file_count += 1
                print(f"  + {arc_name}")

    # ── Rapport ───────────────────────────────────────────────────────────────
    size_ko = zip_path.stat().st_size // 1024
    print(f"")
    print(f"  ✅ ZIP genere avec succes !")
    print(f"  Fichiers inclus  : {file_count}")
    print(f"  Fichiers ignores : {skip_count}")
    print(f"  Taille           : {size_ko} Ko")
    print(f"  Chemin           : {zip_path}")
    print(f"")
    print(f"  Prochaines etapes :")
    print(f"  1. git tag v{version}")
    print(f"  2. git push origin main && git push origin v{version}")
    print(f"  3. Uploader {zip_name} sur GitHub Releases")
    print(f"     https://github.com/beyp/QuickMind/releases/new")
    print(f"")

    return zip_path


if __name__ == "__main__":
    build_zip()
