# QuickMind Docker — Guide d installation

## Ce que ça fait

QuickMind est dockerisé en mode **API uniquement** (headless).
- L interface graphique Tkinter n'est pas dans Docker
- Seul le serveur FastAPI (port 8765) tourne dans le conteneur
- Les données SQLite sont persistées sur le disque hôte

## Prérequis

- Docker Desktop installé et en cours d exécution
- Port 8765 disponible

## Installation rapide

```powershell
# 1. Aller dans le repo QuickMind
cd C:\code\python\QuickMind

# 2. Copier les fichiers Docker de ce ZIP à la racine
# (Dockerfile, docker-compose.yml, requirements.api.txt, run_api.py)

# 3. Construire et lancer
docker-compose up -d --build

# 4. Vérifier
docker ps
curl http://localhost:8765/health
```

## Intégration avec AION

```powershell
# Créer le réseau partagé AION
docker network create aion-network

# Lancer QuickMind sur le réseau AION
docker-compose -f docker-compose.yml -f docker-compose.aion.yml up -d
```

AION peut alors joindre QuickMind via http://quickmind:8765

## Commandes utiles

```powershell
# Voir les logs
docker logs quickmind -f

# Arrêter
docker-compose down

# Rebuild après modif du code
docker-compose up -d --build

# Accéder à la DB dans le conteneur
docker exec -it quickmind sqlite3 data/quickmind.db
```

## Données persistantes

Les données sont dans ./data/ sur ta machine :
- ./data/quickmind.db     ← Base SQLite
- ./data/attachments/     ← Pièces jointes

## Interface graphique

L interface Tkinter reste sur ton PC en mode normal :
```powershell
python main.py   # Lance l interface desktop
```
Elle se connecte automatiquement à l API (Docker ou locale).

## URLs disponibles

| URL | Description |
|---|---|
| http://localhost:8765 | Interface web basique |
| http://localhost:8765/docs | Swagger UI (toutes les routes) |
| http://localhost:8765/health | Health check |
| http://localhost:8765/tasks | Liste des tâches |

## Notes importantes

- La première fois, le build prend ~2-3 minutes
- Les dépendances GUI (customtkinter, pywin32) ne sont PAS installées dans Docker
- Utilise requirements.api.txt (allégé) au lieu de requirements.txt
- config.yaml est monté depuis le repo local
