"""
build_exe.py — Genere le .exe QuickMind avec PyInstaller.
Usage : python build_exe.py

Le .exe et tous les fichiers necessaires sont dans dist/QuickMind/
"""
import os
import sys
import subprocess
import shutil
from pathlib import Path

APP_DIR   = Path(__file__).parent.resolve()
DIST_DIR  = APP_DIR / "dist"
BUILD_DIR = APP_DIR / "build"

print("=" * 60)
print("  QuickMind — Build .exe")
print("=" * 60)
print()

# ── 1. Verifier/installer PyInstaller ─────────────────────────────────────────
try:
    import PyInstaller
    print(f"OK PyInstaller {PyInstaller.__version__}")
except ImportError:
    print("Installation de PyInstaller...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
    print("OK PyInstaller installe")
print()

# ── 2. Nettoyer les anciens builds ────────────────────────────────────────────
for d in [DIST_DIR, BUILD_DIR]:
    if d.exists():
        shutil.rmtree(d)
        print(f"Nettoye : {d.name}/")

# ── 3. Donnees a embarquer dans le .exe ───────────────────────────────────────
datas_args = []
for src, dst in [
    ("ui",                  "ui"),
    ("agents",              "agents"),
    ("core",                "core"),
    ("config.example.yaml", "."),
    ("requirements.txt",    "."),
]:
    full = APP_DIR / src
    if full.exists():
        sep = ";" if sys.platform == "win32" else ":"
        datas_args.append(f"--add-data={full}{sep}{dst}")

# ── 4. Imports caches ─────────────────────────────────────────────────────────
hidden = [
    "customtkinter",
    "PIL._tkinter_finder",
    "sqlmodel",
    "sqlalchemy.dialects.sqlite",
    "yaml",
    "schedule",
    "plyer.platforms.win.notification",
    "win32com.client",
    "win32com.server",
    "pywintypes",
    "fastapi",
    "uvicorn",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "ollama",
    "packaging",
    "pypdf",
    "docx",
    "openpyxl",
    "windnd",
    "ctypes",
    "ctypes.wintypes",
    "tkinter",
    "tkinter.ttk",
    "tkinter.filedialog",
    "tkinter.colorchooser",
    "tkinter.simpledialog",
]
hidden_args = [f"--hidden-import={h}" for h in hidden]

# ── 5. Icone ──────────────────────────────────────────────────────────────────
icon_arg = []
icon_path = APP_DIR / "icon.ico"
if icon_path.exists():
    icon_arg = [f"--icon={icon_path}"]
    print(f"Icone    : icon.ico")
else:
    print("Icone    : non trouvee (icon.ico manquant)")
print()

# ── 6. Lancer PyInstaller ─────────────────────────────────────────────────────
print("Construction du .exe en cours...")
print("(peut prendre 2-5 minutes)")
print()

cmd = [
    sys.executable, "-m", "PyInstaller",
    "--onefile",              # tout en 1 seul .exe
    "--windowed",             # pas de fenetre console
    "--name", "QuickMind",
    "--clean",
    "--noconfirm",
    f"--distpath={DIST_DIR}",
    f"--workpath={BUILD_DIR}",
    f"--specpath={APP_DIR}",
    *datas_args,
    *hidden_args,
    *icon_arg,
    str(APP_DIR / "main.py"),
]

result_proc = subprocess.run(cmd, cwd=APP_DIR)

print()

if result_proc.returncode != 0:
    print("ERREUR lors de la creation du .exe")
    print("Verifiez les messages ci-dessus.")
    sys.exit(1)

exe_path = DIST_DIR / "QuickMind.exe"
if not exe_path.exists():
    print("ERREUR : QuickMind.exe non trouve dans dist/")
    sys.exit(1)

# ── 7. Copier config.yaml dans dist/ ─────────────────────────────────────────
print("Copie des fichiers de configuration...")

config_src = APP_DIR / "config.yaml"
if config_src.exists():
    shutil.copy2(config_src, DIST_DIR / "config.yaml")
    print(f"  OK config.yaml copie dans dist/")
else:
    # Utiliser config.example.yaml comme base
    example = APP_DIR / "config.example.yaml"
    if example.exists():
        shutil.copy2(example, DIST_DIR / "config.yaml")
        print(f"  OK config.yaml cree depuis config.example.yaml")
    else:
        print(f"  ATTENTION : config.yaml non trouve !")

# ── 8. Copier .env dans dist/ (si existe) ────────────────────────────────────
env_src = APP_DIR / ".env"
if env_src.exists():
    shutil.copy2(env_src, DIST_DIR / ".env")
    print(f"  OK .env copie dans dist/")
else:
    # Creer un .env vide avec instructions
    env_dst = DIST_DIR / ".env"
    with open(env_dst, "w", encoding="utf-8") as f:
        f.write("# QuickMind — Variables d environnement\n")
        f.write("# Remplir avec votre token GitHub pour les mises a jour\n")
        f.write("GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxx\n")
    print(f"  OK .env vide cree dans dist/ (a remplir)")

# ── 9. Copier icon.ico dans dist/ ─────────────────────────────────────────────
if icon_path.exists():
    shutil.copy2(icon_path, DIST_DIR / "icon.ico")
    print(f"  OK icon.ico copie dans dist/")

# ── 10. Creer README_INSTALL.txt dans dist/ ───────────────────────────────────
readme = DIST_DIR / "README_INSTALL.txt"
with open(readme, "w", encoding="utf-8") as f:
    f.write("QuickMind — Installation\n")
    f.write("=" * 40 + "\n\n")
    f.write("Prerequis :\n")
    f.write("  - Ollama installe (https://ollama.ai)\n")
    f.write("  - ollama pull mistral\n\n")
    f.write("Configuration :\n")
    f.write("  1. Editer config.yaml (theme, port API, etc.)\n")
    f.write("  2. Editer .env avec votre token GitHub :\n")
    f.write("     GITHUB_TOKEN=ghp_xxxxx\n\n")
    f.write("Lancement :\n")
    f.write("  Double-clic sur QuickMind.exe\n\n")
    f.write("Acces API depuis telephone :\n")
    f.write("  - Installer Tailscale sur PC et telephone\n")
    f.write("  - Ouvrir : http://100.x.x.x:8765\n")
print(f"  OK README_INSTALL.txt cree dans dist/")

# ── 11. Rapport final ─────────────────────────────────────────────────────────
print()
size_mb = exe_path.stat().st_size / (1024 * 1024)
print("=" * 60)
print(f"OK Build termine avec succes !")
print(f"   .exe     : dist/QuickMind.exe  ({size_mb:.1f} Mo)")
print()
print("Contenu de dist/ :")
for f in sorted(DIST_DIR.iterdir()):
    fsize = f.stat().st_size / 1024
    print(f"   {f.name:<30} {fsize:>8.1f} Ko")
print()
print("Etapes suivantes :")
print("  1. Verifier config.yaml dans dist/")
print("  2. Remplir .env avec votre token GitHub")
print("  3. Double-cliquer sur QuickMind.exe")
print("=" * 60)
