# QuickMind API — Guide d'utilisation

## Démarrage
QuickMind lance automatiquement l'API au démarrage.
Regardez le terminal pour voir les URLs :

```
[API] Serveur demarre :
[API]   Local  : http://localhost:8765
[API]   Reseau : http://192.168.1.x:8765
[API]   Docs   : http://localhost:8765/docs
```

---

## PowerShell — qm.ps1

```powershell
# Créer une tâche simple
.\qm.ps1 "Rappeler Jean Martin"

# Avec priorité et catégorie
.\qm.ps1 "Rapport Q2" -p urgent -c Travail

# Avec rappel
.\qm.ps1 "Réunion" -r "25/05/2026 09:00" -c Travail

# Via IA (Mistral analyse)
.\qm.ps1 ai "Préparer la démo client vendredi 14h"

# Lister les tâches
.\qm.ps1 list
.\qm.ps1 list -p urgent

# Marquer terminée
.\qm.ps1 done 5

# Vérifier que QuickMind tourne
.\qm.ps1 health
```

---

## Web / Téléphone

Ouvre dans n'importe quel navigateur :
```
http://localhost:8765          (PC)
http://192.168.1.x:8765       (Téléphone sur le même WiFi)
```

---

## Outlook → Tâche automatique

```powershell
# Installer la règle Outlook (une seule fois)
.\outlook_rule.ps1
```

Ensuite, envoie-toi un mail avec ce format de sujet :
```
QUICKMIND: Titre de la tache [priorite] [Categorie]

Exemples :
QUICKMIND: Rappeler Paul [urgent] [Travail]
QUICKMIND: Préparer rapport Q2 [high]
QUICKMIND: Acheter cadeau anniversaire [Perso]
```

---

## API REST directe

```powershell
# Créer une tâche
Invoke-RestMethod -Uri "http://localhost:8765/task" -Method POST \
  -Body '{"title":"Ma tache","priority":"high","category":"Travail"}' \
  -ContentType "application/json"

# Lister les tâches
Invoke-RestMethod -Uri "http://localhost:8765/tasks"

# Marquer terminée
Invoke-RestMethod -Uri "http://localhost:8765/task/5/done" -Method POST

# Via IA
Invoke-RestMethod -Uri "http://localhost:8765/task/ai" -Method POST \
  -Body '{"text":"Réunion équipe lundi 10h salle B"}' \
  -ContentType "application/json"
```

---

## Documentation interactive

```
http://localhost:8765/docs
```
Interface Swagger complète avec tous les endpoints.
