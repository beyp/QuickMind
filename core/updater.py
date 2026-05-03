"""
Systeme de mise a jour automatique QuickMind.
Supporte les repos prives via token GitHub.
Fix : met a jour uniquement le numero de version dans config.yaml.
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
GITHUB_TOKEN    = _cfg["updater"].get("github_token", "")
API_BASE        = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}"
API_LATEST      = f"{API_BASE}/releases/latest"

APP_DIR = Path(sys.argv[0]).parent.resolve()
if not (APP_DIR / "main.py").exists():
    APP_DIR = Path(__file__).parent.parent.resolve()

# Fichiers jamais ecrases (sauf mise a jour partielle pour config.yaml)
NEVER_TOUCH = {
    "data", ".env",
    ".git", ".gitignore", ".vscode",
    "debug_update.py",
    "_update.zip", "_update_tmp",
}


def _get_headers(accept="application/vnd.github+json"):
    h = {"Accept": accept, "User-Agent": "QuickMind-Updater"}
    if GITHUB_TOKEN:
        h["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return h


def _fetch_latest_release() -> dict | None:
    """Appel API GitHub pour recuperer la derniere release (infos fraiches)."""
    req = urllib.request.Request(API_LATEST, headers=_get_headers())
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def _extract_asset(data: dict) -> tuple:
    """Extrait asset_id et zip_url depuis les donnees d une release."""
    assets   = data.get("assets", [])
    asset_id = zip_url = None
    for asset in assets:
        if asset["name"].endswith(".zip"):
            asset_id = asset["id"]
            zip_url  = asset["browser_download_url"]
            break
    if not zip_url:
        zip_url  = data.get("zipball_url")
        asset_id = None
    return asset_id, zip_url


def check_for_update() -> dict | None:
    """Verifie si une nouvelle version est disponible."""
    try:
        data = _fetch_latest_release()
        if not data:
            return None
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
            }
        return None
    except Exception as e:
        print(f"[Updater] Erreur check : {e}")
        return None


def _update_version_in_config(new_version: str):
    """
    Met a jour UNIQUEMENT le champ app.version dans config.yaml.
    Preserve toutes les autres valeurs (token, chemins, etc.).
    """
    cfg_path = APP_DIR / "config.yaml"
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        cfg["app"]["version"] = new_version
        with open(cfg_path, "w", encoding="utf-8") as f:
            yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False,
                      sort_keys=False)
        print(f"[Updater] Version mise a jour dans config.yaml : {new_version}")
    except Exception as e:
        print(f"[Updater] Impossible de mettre a jour config.yaml : {e}")


def _download(asset_id, zip_url, dest_path, on_progress):
    """
    Telecharge l asset.
    Re-fetch l asset_id frais juste avant pour eviter le 404.
    """
    try:
        fresh_data             = _fetch_latest_release()
        fresh_asset_id, fresh_zip_url = _extract_asset(fresh_data)
        if fresh_asset_id:
            asset_id = fresh_asset_id
            print(f"[Updater] Asset ID rafraichi : {asset_id}")
        if fresh_zip_url:
            zip_url = fresh_zip_url
    except Exception as e:
        print(f"[Updater] Re-fetch ignore : {e}")

    if asset_id and GITHUB_TOKEN:
        url    = f"{API_BASE}/releases/assets/{asset_id}"
        accept = "application/octet-stream"
        print(f"[Updater] Mode : API asset prive (id={asset_id})")
    else:
        url    = zip_url
        accept = "application/vnd.github+json"
        print(f"[Updater] Mode : URL directe")

    print(f"[Updater] Download : {url}")
    req = urllib.request.Request(url, headers=_get_headers(accept))
    with urllib.request.urlopen(req, timeout=60) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        done  = 0
        with open(dest_path, "wb") as f:
            while True:
                chunk = resp.read(8192)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if total and on_progress:
                    on_progress(
                        f"Telechargement {done//1024} Ko / {total//1024} Ko",
                        int(done / total * 55) + 10
                    )


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
                raise ValueError(
                    f"Fichier invalide ({size} Ko). "
                    "Verifiez que QuickMind.zip est bien attache a la release GitHub."
                )

            if on_progress: on_progress("Extraction...", 68)
            if tmp_dir.exists():
                shutil.rmtree(tmp_dir, ignore_errors=True)
            tmp_dir.mkdir()

            # Extraire en filtrant .git et proteges
            # config.yaml est INCLUS dans l extraction mais on ne l ecrase PAS
            with zipmodule.ZipFile(tmp_zip, "r") as zf:
                for member in zf.infolist():
                    parts = Path(member.filename).parts
                    if len(parts) < 2:
                        continue
                    rel_parts = parts[1:]
                    top = rel_parts[0] if rel_parts else ""
                    if (top in NEVER_TOUCH
                            or top.startswith("_bk_")
                            or top.startswith("_update")
                            or ".git" in rel_parts):
                        continue
                    zf.extract(member, tmp_dir)

            if on_progress: on_progress("Installation...", 80)
            contents = list(tmp_dir.iterdir())
            src_root = (contents[0]
                        if len(contents) == 1 and contents[0].is_dir()
                        else tmp_dir)
            print(f"[Updater] Source : {src_root}")

            ok = 0
            for item in src_root.rglob("*"):
                if item.is_dir():
                    continue
                rel  = item.relative_to(src_root)
                top  = rel.parts[0] if rel.parts else ""

                # config.yaml : NE PAS ecraser (on fait la mise a jour de version apres)
                if str(rel) == "config.yaml" or top in NEVER_TOUCH or ".git" in rel.parts:
                    continue

                dest = APP_DIR / rel
                try:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item, dest)
                    ok += 1
                except Exception as e:
                    print(f"[Updater] Skip {rel} : {e}")
            print(f"[Updater] {ok} fichier(s) installes.")

            if on_progress: on_progress("Mise a jour de la version...", 94)

            # Mettre a jour SEULEMENT le numero de version dans config.yaml
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
            import traceback
            traceback.print_exc()
            try:
                tmp_zip.unlink(missing_ok=True)
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass
            if on_error: on_error(str(e))

    threading.Thread(target=_run, daemon=True).start()


def restart_app():
    print("[Updater] Redemarrage...")
    subprocess.Popen([sys.executable, str(APP_DIR / "main.py")])
    sys.exit(0)
