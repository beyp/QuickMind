"""
Système de mise à jour automatique QuickMind.
Vérifie les releases GitHub, télécharge et installe la nouvelle version.
"""
import yaml
import json
import os
import sys
import shutil
import zipfile
import subprocess
import threading
import urllib.request
import urllib.error
from pathlib import Path
from packaging.version import Version


_cfg_path = Path(__file__).parent.parent / "config.yaml"
with open(_cfg_path, "r", encoding="utf-8") as f:
    _cfg = yaml.safe_load(f)

CURRENT_VERSION  = _cfg["app"]["version"]
GITHUB_OWNER     = _cfg["updater"]["github_owner"]
GITHUB_REPO      = _cfg["updater"]["github_repo"]
GITHUB_TOKEN     = _cfg["updater"].get("github_token", "")
API_URL          = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
APP_DIR          = Path(__file__).parent.parent.resolve()


def _get_headers() -> dict:
    headers = {
        "Accept":     "application/vnd.github+json",
        "User-Agent": "QuickMind-Updater",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers


def check_for_update() -> dict | None:
    """
    Vérifie si une nouvelle version est disponible.
    Retourne un dict avec les infos de la release, ou None si à jour / erreur.
    """
    try:
        req = urllib.request.Request(API_URL, headers=_get_headers())
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())

        latest_tag  = data.get("tag_name", "").lstrip("v")
        latest_name = data.get("name", latest_tag)
        body        = data.get("body", "")
        assets      = data.get("assets", [])
        zip_url     = None

        # Cherche un asset .zip dans la release
        for asset in assets:
            if asset["name"].endswith(".zip"):
                zip_url = asset["browser_download_url"]
                break

        # Fallback : archive source GitHub
        if not zip_url:
            zip_url = data.get("zipball_url")

        if not latest_tag:
            return None

        if Version(latest_tag) > Version(CURRENT_VERSION):
            return {
                "version":   latest_tag,
                "name":      latest_name,
                "body":      body,
                "zip_url":   zip_url,
                "tag":       data.get("tag_name"),
                "published": data.get("published_at", "")[:10],
            }
        return None

    except Exception as e:
        print(f"[Updater] Erreur vérification : {e}")
        return None


def download_and_install(zip_url: str,
                         on_progress=None,
                         on_done=None,
                         on_error=None):
    """
    Télécharge le ZIP de la nouvelle version, sauvegarde les données,
    remplace les fichiers et redémarre l app.
    Tout s exécute dans un thread séparé.
    """
    def _run():
        try:
            # ── 1. Téléchargement ─────────────────────────────────────────
            if on_progress: on_progress("Téléchargement en cours...", 10)
            tmp_zip = APP_DIR / "_update.zip"

            req = urllib.request.Request(zip_url, headers=_get_headers())
            with urllib.request.urlopen(req, timeout=60) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                downloaded = 0
                chunk_size = 8192
                with open(tmp_zip, "wb") as f:
                    while True:
                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total and on_progress:
                            pct = int(downloaded / total * 60) + 10
                            on_progress(f"Téléchargement... {downloaded//1024} Ko", pct)

            if on_progress: on_progress("Extraction...", 72)

            # ── 2. Extraction dans un dossier temporaire ──────────────────
            tmp_dir = APP_DIR / "_update_tmp"
            if tmp_dir.exists():
                shutil.rmtree(tmp_dir)
            tmp_dir.mkdir()

            with zipfile.ZipFile(tmp_zip, "r") as zf:
                zf.extractall(tmp_dir)

            # Trouve le dossier racine dans le zip (ex: QuickMind/)
            contents = list(tmp_dir.iterdir())
            src_dir  = contents[0] if len(contents) == 1 and contents[0].is_dir() else tmp_dir

            if on_progress: on_progress("Sauvegarde des données...", 80)

            # ── 3. Protéger les données utilisateur ───────────────────────
            protected = ["data/", "config.yaml"]
            backups   = {}
            for p in protected:
                full = APP_DIR / p
                if full.exists():
                    bk = APP_DIR / f"_backup_{p.replace('/', '_')}"
                    if full.is_dir():
                        shutil.copytree(full, bk, dirs_exist_ok=True)
                    else:
                        shutil.copy2(full, bk)
                    backups[p] = str(bk)

            if on_progress: on_progress("Installation...", 88)

            # ── 4. Remplacer les fichiers (sauf données protégées) ────────
            for item in src_dir.iterdir():
                dest = APP_DIR / item.name
                skip = False
                for p in protected:
                    if item.name == p.rstrip("/"):
                        skip = True
                        break
                if skip:
                    continue
                if item.is_dir():
                    if dest.exists():
                        shutil.rmtree(dest)
                    shutil.copytree(item, dest)
                else:
                    shutil.copy2(item, dest)

            # ── 5. Restaurer les données ──────────────────────────────────
            for p, bk_path in backups.items():
                bk   = Path(bk_path)
                dest = APP_DIR / p
                if bk.is_dir():
                    shutil.copytree(bk, dest, dirs_exist_ok=True)
                    shutil.rmtree(bk)
                else:
                    shutil.copy2(bk, dest)
                    bk.unlink()

            if on_progress: on_progress("Nettoyage...", 96)

            # ── 6. Nettoyage ──────────────────────────────────────────────
            tmp_zip.unlink(missing_ok=True)
            shutil.rmtree(tmp_dir, ignore_errors=True)

            if on_progress: on_progress("Mise à jour terminée !", 100)
            if on_done: on_done()

        except Exception as e:
            if on_error: on_error(str(e))

    threading.Thread(target=_run, daemon=True).start()


def restart_app():
    """Redémarre QuickMind."""
    main_py = APP_DIR / "main.py"
    subprocess.Popen([sys.executable, str(main_py)])
    sys.exit(0)
