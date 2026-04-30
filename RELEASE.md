# Guide de release QuickMind

## Comment publier une nouvelle version

### 1. Mettre à jour le numéro de version
Dans `config.yaml` :
```yaml
app:
  version: "1.1.0"   # ← changer ici
```

### 2. Committer et tagger
```powershell
git add .
git commit -m "QuickMind v1.1.0 — Description des changements"
git tag v1.1.0
git push origin main
git push origin v1.1.0
```

### 3. Créer la Release sur GitHub
- Aller sur https://github.com/beyp/QuickMind/releases
- Cliquer "Draft a new release"
- Choisir le tag `v1.1.0`
- Remplir le titre et les notes de version
- Cliquer "Publish release"

QuickMind détectera automatiquement la nouvelle version
au prochain démarrage et proposera la mise à jour aux utilisateurs.

## Numérotation des versions (SemVer)
- v1.0.0 → v1.0.1 : Correction de bug
- v1.0.0 → v1.1.0 : Nouvelle fonctionnalité
- v1.0.0 → v2.0.0 : Changement majeur
