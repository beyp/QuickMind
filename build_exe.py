"""
build_exe.py — Genere le .exe QuickMind avec PyInstaller (mode onedir).
Architecture style VS Code :
  dist/QuickMind/
    QuickMind.exe     <- lanceur (ne change jamais)
    _internal/        <- code Python (mis a jour sans toucher a l exe)
    config.yaml       <- configuration
    .env              <- secrets
    data/             <- base de donnees (creee au 1er lancement)

Usage : python build_exe.py
"""
import os
import sys
import subprocess
import shutil
from pathlib import Path

APP_DIR   = Path(__file__).parent.resolve()
DIST_DIR  = APP_DIR / "dist"
BUILD_DIR = APP_DIR / "build"
EXE_DIR   = DIST_DIR / "QuickMind"   # dossier final

print("=" * 60)
print("  QuickMind — Build .exe (mode onedir)")
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

# ── 2. Lire la version ────────────────────────────────────────────────────────
try:
    import yaml
    with open(APP_DIR / "config.yaml", "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    version = cfg["app"]["version"]
    print(f"Version  : {version}")
except Exception:
    version = "x.x.x"

# ── 3. Nettoyer les anciens builds ────────────────────────────────────────────
for d in [DIST_DIR, BUILD_DIR]:
    if d.exists():
        shutil.rmtree(d)
        print(f"Nettoye  : {d.name}/")
print()

# ── 4. Donnees embarquees ─────────────────────────────────────────────────────
sep = ";" if sys.platform == "win32" else ":"
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
        datas_args.append(f"--add-data={full}{sep}{dst}")

# ── 5. Imports caches ─────────────────────────────────────────────────────────
hidden_args = [f"--hidden-import={h}" for h in [
    "customtkinter", "PIL._tkinter_finder",
    "sqlmodel", "sqlalchemy.dialects.sqlite",
    "yaml", "schedule",
    "plyer.platforms.win.notification",
    "win32com.client", "win32com.server", "pywintypes",
    "fastapi", "uvicorn", "uvicorn.logging",
    "uvicorn.loops", "uvicorn.loops.auto",
    "uvicorn.protocols", "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.lifespan", "uvicorn.lifespan.on",
    "ollama", "packaging",
    "pypdf", "docx", "openpyxl", "windnd",
    "ctypes", "ctypes.wintypes",
    "tkinter", "tkinter.ttk",
    "tkinter.filedialog", "tkinter.colorchooser",
    "tkinter.simpledialog",
]]

# ── 6. Icone ──────────────────────────────────────────────────────────────────
icon_arg = []
icon_path = APP_DIR / "icon.ico"
if icon_path.exists():
    icon_arg = [f"--icon={icon_path}"]
    print(f"Icone    : icon.ico")
else:
    print("Icone    : non trouvee (optionnel)")
print()

# ── 7. Build PyInstaller onedir ───────────────────────────────────────────────
print("Construction du .exe en cours (2-5 min)...")
print()

cmd = [
    sys.executable, "-m", "PyInstaller",
    "--onedir",               # ← onedir comme VS Code
    "--windowed",
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
    sys.exit(1)

exe_path = EXE_DIR / "QuickMind.exe"
if not exe_path.exists():
    print(f"ERREUR : QuickMind.exe non trouve dans {EXE_DIR}")
    sys.exit(1)

print(f"OK QuickMind.exe : {exe_path.stat().st_size/(1024*1024):.1f} Mo")
print()

# ── 8. Copier config.yaml dans dist/QuickMind/ ───────────────────────────────
print("Copie des fichiers de configuration...")

config_src = APP_DIR / "config.yaml"
if config_src.exists():
    shutil.copy2(config_src, EXE_DIR / "config.yaml")
    print(f"  OK config.yaml")
else:
    example = APP_DIR / "config.example.yaml"
    if example.exists():
        shutil.copy2(example, EXE_DIR / "config.yaml")
        print(f"  OK config.yaml (depuis example)")

# ── 9. Copier .env dans dist/QuickMind/ ──────────────────────────────────────
env_src = APP_DIR / ".env"
if env_src.exists():
    shutil.copy2(env_src, EXE_DIR / ".env")
    print(f"  OK .env")
else:
    env_dst = EXE_DIR / ".env"
    with open(env_dst, "w", encoding="utf-8") as f:
        f.write("# QuickMind — Token GitHub pour les mises a jour\n")
        f.write("GITHUB_TOKEN=\n")
    print(f"  OK .env vide cree (a remplir)")

# ── 10. Copier icon.ico ───────────────────────────────────────────────────────
if icon_path.exists():
    shutil.copy2(icon_path, EXE_DIR / "icon.ico")
    print(f"  OK icon.ico")

# ── 11. Creer dossier data/ ───────────────────────────────────────────────────
(EXE_DIR / "data").mkdir(exist_ok=True)
print(f"  OK data/ cree")

# ── 12. README_INSTALL.txt ────────────────────────────────────────────────────
with open(EXE_DIR / "README_INSTALL.txt", "w", encoding="utf-8") as f:
    f.write(f"QuickMind v{version}\n")
    f.write("=" * 40 + "\n\n")
    f.write("Prerequis :\n")
    f.write("  - Ollama (https://ollama.ai) + ollama pull mistral\n\n")
    f.write("Configuration :\n")
    f.write("  1. Editer config.yaml\n")
    f.write("  2. Editer .env avec votre token GitHub\n\n")
    f.write("Lancement :\n")
    f.write("  Double-clic sur QuickMind.exe\n\n")
    f.write("Mise a jour :\n")
    f.write("  Automatique au demarrage (GitHub Releases)\n")
    f.write("  Seul _internal/ est mis a jour — QuickMind.exe reste intact\n")
print(f"  OK README_INSTALL.txt")

# ── 13. Generer le ZIP de distribution ───────────────────────────────────────
print()
print("Generation du ZIP de distribution...")
zip_name = f"QuickMind_v{version}_exe.zip"
zip_path = DIST_DIR / zip_name
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
    for f in EXE_DIR.rglob("*"):
        if f.is_file() and "data" not in str(f.relative_to(EXE_DIR)):
            arc = f"QuickMind/{f.relative_to(EXE_DIR)}"
            zf.write(f, arc)
zip_mb = zip_path.stat().st_size / (1024*1024)
print(f"  OK {zip_name} ({zip_mb:.1f} Mo)")

# ── 14. Rapport final ─────────────────────────────────────────────────────────
print()
print("=" * 60)
print(f"  BUILD v{version} TERMINE !")
print("=" * 60)
print()
print(f"  dist/QuickMind/")
total = 0
for f in sorted(EXE_DIR.iterdir()):
    if f.is_file():
        sz = f.stat().st_size
        total += sz
        print(f"    {f.name:<35} {sz/1024:>8.1f} Ko")
    elif f.is_dir():
        dir_sz = sum(ff.stat().st_size for ff in f.rglob("*") if ff.is_file())
        total += dir_sz
        print(f"    {f.name+'/':<35} {dir_sz/1024/1024:>7.1f} Mo")
print(f"    {'TOTAL':<35} {total/1024/1024:>7.1f} Mo")
print()
print(f"  ZIP release : dist/{zip_name}")
print()
print("  Architecture (style VS Code) :")
print("    QuickMind.exe   = lanceur (ne change jamais)")
print("    _internal/      = code mis a jour automatiquement")
print("    config.yaml     = configuration locale")
print("    .env            = secrets (token GitHub)")
print("=" * 60)
