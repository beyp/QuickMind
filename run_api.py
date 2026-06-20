"""
QuickMind API — Point d entree pour Docker / mode headless.
Lance uniquement le serveur FastAPI sur le port 8765, sans interface graphique.
"""
import logging
import os
from pathlib import Path

import uvicorn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("quickmind.api")

if __name__ == "__main__":
    # Créer les dossiers nécessaires
    Path("data").mkdir(exist_ok=True)
    Path("data/attachments").mkdir(exist_ok=True)
    Path("logs").mkdir(exist_ok=True)

    # Initialiser la base de données
    from core.database import init_db
    init_db()
    logger.info("Base de données initialisée")

    host = os.getenv("QUICKMIND_HOST", "0.0.0.0")
    port = int(os.getenv("QUICKMIND_PORT", "8765"))

    logger.info(f"QuickMind API → http://{host}:{port}")
    logger.info(f"Docs → http://localhost:{port}/docs")

    uvicorn.run(
        "core.api_server:app",
        host=host,
        port=port,
        log_level="info",
        reload=False,
    )
