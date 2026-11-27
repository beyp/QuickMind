# QuickMind

Gestionnaire de tâches personnel avec interface web/API, fonctionnalités IA et persistance SQLite.

- IA : **Groq** (texte + vision), appels centralisés dans `agents/ai_client.py` ; plus de dépendance à Ollama pour les parcours IA.
- Déploiement local : Docker via BDS Infrastructure, avec volumes de données persistants.
- Migration et recette : [Guide QM-01 Groq](docs/GROQ_MIGRATION.md).
- API : [README_API.md](README_API.md).

Ne jamais committer les clés API ou les données utilisateurs.
