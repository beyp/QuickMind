"""
Systeme de mise a jour automatique QuickMind.
Architecture style VS Code :
  - Mode Python : met a jour les fichiers .py directement
  - Mode .exe   : met a jour _internal/ sans toucher a QuickMind.exe
Token GitHub lu depuis .env > config.yaml > variable OS.
"""
import yaml, json, sys, shutil, subprocess, threading, urllib.request
import zipfile as zipmodule
from pathlib import Path
from packaging.version import Version

_cfg_path = Path(__file__).parent.parent / "config.yaml"
with open(_cfg_path, "r", encoding="utf-8") as f:
    _cfg = yaml.safe_load(f)

CURRENT_VERSION = _cfg["app"]["version"]
GITHUB_OWNER    = _cfg["updater"]["github_owner"]
GITHUB_REPO     = _cfg["updater"]["github_repo"]
API_BASE        = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}"
API_LATEST      = f"{API_BASE}/releases/latest"

# Detecter si on tourne en mode .exe (PyInstaller) ou Python script
IS_EXE = getattr(sys, "frozen", False)

if IS_EXE:
    # Mode .exe : APP_DIR = dossier contenant QuickMind.exe
    APP_DIR      = Path(sys.executable).parent.resolve()
    INTERNAL_DIR = APP_DIR / "_internal"   # code a mettre a jour
    print(f"[Updater] Mode EXE — APP_DIR={APP_DIR}")
else:
    # Mode Python script
    APP_DIR      = Path(sys.argv[0]).parent.resolve()
    if not (APP_DIR / "main.py").exists():
        APP_DIR  = Path(__file__).parent.parent.resolve()
    INTERNAL_DIR = None
    print(f"[Updater] Mode Python — APP_DIR={APP_DIR}")

# Fichiers JAMAIS touches lors d une mise a jour
NEVER_TOUCH = {
    "data", "config.yaml", ".env",
    ".git", ".gitignore", ".vscode",
    "RELEASE.md", "debug_update.py",
    "_update.zip", "_update_tmp",
    # En mode .exe : ne jamais toucher a l exe lui-meme
    "QuickMind.exe",
    "README_INSTALL.txt",
}


def _load_token() -> str:
    """Charge le token depuis .env > config.yaml > variable OS."""
    env_path = APP_DIR / ".env"
    if env_path.exists():
        try:
            with open(env_path, "r", encoding="utf-8-sig") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("GITHUB_TOKEN=") and not line.startswith("#"):
                        token = line.split("=", 1)[1].strip().strip('"\' ')
                        if token and not token.startswith("ghp_xxx"):
                            print("[Updater] Token depuis .env")
                            return token
        except Exception as e:
            print(f"[Updater] Erreur .env : {e}")

    token_cfg = _cfg.get("updater", {}).get("github_token", "")
    if token_cfg:
        print("[Updater] Token depuis config.yaml")
        return token_cfg

    import os
    token_os = os.environ.get("GITHUB_TOKEN", "")
    if token_os:
        print("[Updater] Token depuis variable OS")
        return token_os

    return ""


GITHUB_TOKEN = _load_token()


def _get_headers(accept="application/vnd.github+json"):
    h = {"Accept": accept, "User-Agent": "QuickMind-Updater"}
    if GITHUB_TOKEN:
        h["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return h


def _fetch_latest_release():
    req = urllib.request.Request(API_LATEST, headers=_get_headers())
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def _extract_asset(data):
    assets = data.get("assets", [])
    asset_id = zip_url = None

    if IS_EXE:
        # Mode .exe : chercher le ZIP _exe (contient _internal/)
        for asset in assets:
            if "_exe" in asset["name"] and asset["name"].endswith(".zip"):
                asset_id = asset["id"]
                zip_url  = asset["browser_download_url"]
                break

    if not zip_url:
        # Fallback : ZIP standard (scripts Python)
        for asset in assets:
            if asset["name"].endswith(".zip") and "_exe" not in asset["name"]:
                asset_id = asset["id"]
                zip_url  = asset["browser_download_url"]
                break

    if not zip_url:
        zip_url  = data.get("zipball_url")
        asset_id = None

    return asset_id, zip_url


def check_for_update():
    try:
        data       = _fetch_latest_release()
        latest_tag = data.get("tag_name", "").lstrip("v")
        if not latest_tag:
            return None
        asset_id, zip_url = _extract_asset(data)
        if Version(latest_tag) > Version(CURRENT_VERSION):
            return {
                "version":   latest_tag,
                "name":      data.get("name", latest_tag),
                "body":      data.get("body", ""),
                "zip_url":   zip_url,
                "asset_id":  asset_id,
                "tag":       data.get("tag_name"),
                "published": data.get("published_at", "")[:10],
                "is_exe":    IS_EXE,
            }
        return None
    except Exception as e:
        print(f"[Updater] Erreur check : {e}")
        return None


def _update_version_in_config(new_version):
    cfg_path = APP_DIR / "config.yaml"
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        cfg["app"]["version"] = new_version
        with open(cfg_path, "w", encoding="utf-8") as f:
            yaml.dump(cfg, f, allow_unicode=True,
                      default_flow_style=False, sort_keys=False)
        print(f"[Updater] Version -> {new_version}")
    except Exception as e:
        print(f"[Updater] Erreur version : {e}")


def _download(asset_id, zip_url, dest_path, on_progress):
    """Telecharge avec re-fetch asset_id pour eviter 404."""
    try:
        fresh       = _fetch_latest_release()
        fid, furl   = _extract_asset(fresh)
        if fid:   asset_id = fid
        if furl:  zip_url  = furl
    except Exception as e:
        print(f"[Updater] Re-fetch ignore : {e}")

    if asset_id and GITHUB_TOKEN:
        url    = f"{API_BASE}/releases/assets/{asset_id}"
        accept = "application/octet-stream"
    else:
        url    = zip_url
        accept = "application/vnd.github+json"

    print(f"[Updater] Download : {url}")
    req = urllib.request.Request(url, headers=_get_headers(accept))
    with urllib.request.urlopen(req, timeout=60) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        done  = 0
        with open(dest_path, "wb") as f:
            while True:
                chunk = resp.read(8192)
                if not chunk: break
                f.write(chunk)
                done += len(chunk)
                if total and on_progress:
                    on_progress(
                        f"Telechargement {done//1024} Ko / {total//1024} Ko",
                        int(done/total*55)+10)


def _install_exe_update(tmp_dir, new_version, on_progress):
    """
    Mode EXE — Met a jour _internal/ sans toucher a QuickMind.exe.
    Exactement comme VS Code met a jour resources/app/.
    """
    if on_progress: on_progress("Recherche des fichiers...", 72)

    # Trouver le dossier source dans le ZIP extrait
    contents = list(tmp_dir.iterdir())
    src_root = contents[0] if len(contents)==1 and contents[0].is_dir() else tmp_dir

    # Chercher le dossier _internal dans le ZIP
    src_internal = src_root / "_internal"
    if not src_internal.exists():
        # Fallback : le ZIP contient directement les fichiers Python
        src_internal = src_root

    if on_progress: on_progress("Mise a jour _internal/...", 80)

    # Backup de l ancien _internal
    bk_internal = APP_DIR / "_internal_backup"
    if INTERNAL_DIR.exists():
        if bk_internal.exists():
            shutil.rmtree(bk_internal, ignore_errors=True)
        shutil.copytree(INTERNAL_DIR, bk_internal)
        print(f"[Updater] Backup _internal/ -> _internal_backup/")

    try:
        # Remplacer _internal/ (QuickMind.exe reste intact !)
        if INTERNAL_DIR.exists():
            shutil.rmtree(INTERNAL_DIR)
        if src_internal != src_root:
            shutil.copytree(src_internal, INTERNAL_DIR)
        else:
            # Copier les fichiers Python directement
            INTERNAL_DIR.mkdir(exist_ok=True)
            ok = 0
            for item in src_root.rglob("*"):
                if item.is_dir(): continue
                rel  = item.relative_to(src_root)
                top  = rel.parts[0] if rel.parts else ""
                if top in NEVER_TOUCH or ".git" in rel.parts: continue
                dest = INTERNAL_DIR / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, dest)
                ok += 1
            print(f"[Updater EXE] {ok} fichiers installes dans _internal/")

        # Supprimer le backup si succes
        if bk_internal.exists():
            shutil.rmtree(bk_internal, ignore_errors=True)

        print("[Updater EXE] _internal/ mis a jour avec succes !")

    except Exception as e:
        # Restaurer le backup en cas d erreur
        print(f"[Updater EXE] ERREUR, restauration backup : {e}")
        if bk_internal.exists() and INTERNAL_DIR:
            if INTERNAL_DIR.exists():
                shutil.rmtree(INTERNAL_DIR, ignore_errors=True)
            shutil.copytree(bk_internal, INTERNAL_DIR)
        raise


def _install_python_update(tmp_dir, new_version, on_progress):
    """Mode Python — Met a jour les fichiers .py directement."""
    if on_progress: on_progress("Installation...", 80)

    contents = list(tmp_dir.iterdir())
    src_root = contents[0] if len(contents)==1 and contents[0].is_dir() else tmp_dir

    ok = 0
    for item in src_root.rglob("*"):
        if item.is_dir(): continue
        rel  = item.relative_to(src_root)
        top  = rel.parts[0] if rel.parts else ""
        if (str(rel) == "config.yaml" or top in NEVER_TOUCH
                or ".git" in rel.parts):
            continue
        dest = APP_DIR / rel
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, dest)
            ok += 1
        except Exception as e:
            print(f"[Updater] Skip {rel} : {e}")
    print(f"[Updater Python] {ok} fichiers installes.")


def download_and_install(zip_url, asset_id=None, new_version=None,
                         on_progress=None, on_done=None, on_error=None):
    def _run():
        tmp_zip = APP_DIR / "_update.zip"
        tmp_dir = APP_DIR / "_update_tmp"
        try:
            if on_progress: on_progress("Connexion a GitHub...", 5)
            _download(asset_id, zip_url, tmp_zip, on_progress)
            size = tmp_zip.stat().st_size // 1024
            print(f"[Updater] Telecharge : {size} Ko")

            if not zipmodule.is_zipfile(tmp_zip):
                raise ValueError(f"Fichier invalide ({size} Ko).")

            if on_progress: on_progress("Extraction...", 68)
            if tmp_dir.exists():
                shutil.rmtree(tmp_dir, ignore_errors=True)
            tmp_dir.mkdir()

            with zipmodule.ZipFile(tmp_zip, "r") as zf:
                for member in zf.infolist():
                    parts = Path(member.filename).parts
                    if len(parts) < 2: continue
                    rel_parts = parts[1:]
                    top = rel_parts[0] if rel_parts else ""
                    if (top in NEVER_TOUCH or top.startswith("_bk_")
                            or top.startswith("_update")
                            or ".git" in rel_parts):
                        continue
                    zf.extract(member, tmp_dir)

            # Choisir la strategie selon le mode
            if IS_EXE:
                _install_exe_update(tmp_dir, new_version, on_progress)
            else:
                _install_python_update(tmp_dir, new_version, on_progress)

            if on_progress: on_progress("Mise a jour version...", 94)
            if new_version:
                _update_version_in_config(new_version)

            if on_progress: on_progress("Nettoyage...", 97)
            try:
                tmp_zip.unlink(missing_ok=True)
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass

            if on_progress: on_progress("Mise a jour terminee !", 100)
            print("[Updater] Installation complete !")
            if on_done: on_done()

        except Exception as e:
            import traceback; traceback.print_exc()
            try:
                tmp_zip.unlink(missing_ok=True)
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass
            if on_error: on_error(str(e))

    threading.Thread(target=_run, daemon=True).start()


def restart_app():
    print("[Updater] Redemarrage...")
    if IS_EXE:
        # Mode exe : relancer QuickMind.exe
        exe = Path(sys.executable)
        subprocess.Popen([str(exe)])
    else:
        # Mode Python : relancer main.py
        subprocess.Popen([sys.executable, str(APP_DIR / "main.py")])
    sys.exit(0)
