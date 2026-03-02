# Guide de bascule vers GitHub + Claude Code

## Étape 1 — Préparer ton poste

### Installer Git (si pas déjà fait)
```bash
# macOS
brew install git

# Windows
# Télécharger depuis https://git-scm.com/download/win

# Vérifier
git --version
```

### Installer Claude Code
```bash
# Requiert Node.js 18+
npm install -g @anthropic-ai/claude-code

# Vérifier
claude --version
```

### Configurer Git avec GitHub
```bash
git config --global user.name "juliengonde-5G"
git config --global user.email "ton-email@example.com"
```

---

## Étape 2 — Créer le repo sur GitHub

Le repo existe déjà : https://github.com/juliengonde-5G/mytowt

S'il est vide, parfait. S'il contient déjà du contenu, on fera un force push.

---

## Étape 3 — Pousser le code

### Option A — Depuis ton Mac/PC (recommandé)

```bash
# 1. Télécharge mytowt-github.zip (depuis cette conversation)

# 2. Décompresse dans un dossier
mkdir mytowt && cd mytowt
unzip ../mytowt-github.zip

# 3. Initialise le repo Git
git init
git remote add origin https://github.com/juliengonde-5G/mytowt.git

# 4. Premier commit
git add -A
git commit -m "Initial commit — my_TOWT v2.0.0

Maritime operations platform:
- 10 modules: planning, commercial, cargo, escale, onboard, crew, passengers, finance, KPI, admin
- FastAPI + PostgreSQL + Jinja2 + HTMX
- Docker deployment (VPS OVH)
- Role-based permissions (6 roles, 14 modules)"

# 5. Push
git branch -M main
git push -u origin main
```

### Option B — Depuis le VPS OVH directement

```bash
# Se connecter en SSH au VPS
ssh user@51.178.59.174

# Le code est déjà sur le VPS
cd /home/user/mytowt
git pull origin main
```

---

## Étape 4 — Configurer Claude Code

```bash
# 1. Clone le repo
cd ~/projects  # ou ton dossier de travail
git clone https://github.com/juliengonde-5G/mytowt.git
cd mytowt

# 2. Lance Claude Code
claude

# Claude Code lit automatiquement CLAUDE.md et comprend le projet
```

### Premier test avec Claude Code

```
> claude

# Une fois dans Claude Code, essaie :
> Lis le CLAUDE.md et fais-moi un résumé de l'architecture
> Montre-moi le modèle PackingList et ses relations
> Ajoute un champ description_of_goods au modèle PackingListBatch
```

---

## Étape 5 — Workflow de développement avec Claude Code

### Cycle normal

```bash
# 1. Développer avec Claude Code
cd mytowt
claude
> [ta demande de modification]

# 2. Vérifier les changements
git diff
git status

# 3. Committer
git add -A
git commit -m "feat: description du changement"
git push

# 4. Déployer sur le VPS (voir ci-dessous)
```

### Déploiement depuis GitHub vers VPS OVH

**Option simple — Pull sur le VPS :**
```bash
ssh user@51.178.59.174
cd /home/user/mytowt
git pull origin main
docker restart towt-app-v2
```

**Option avancée — Script de deploy automatique :**
```bash
#!/bin/bash
# deploy.sh — sur le VPS OVH
set -e
cd /home/user/mytowt
git pull origin main
docker restart towt-app-v2
echo "✅ Déployé $(git log --oneline -1)"
```

---

## Étape 6 — Continuer les évolutions prévues

Une fois sur Claude Code, tu pourras demander les évolutions du backlog :

```
> Ajoute un système de journal d'activité global dans le module admin.
  Crée le modèle ActivityLog, un helper log_activity(), instrumente
  tous les routers, et ajoute une page /admin/activity avec filtres
  par module et pagination.
```

Claude Code modifiera directement les fichiers, tu verras les diffs, et tu pourras committer/pousser.

---

## Résumé des fichiers fournis

| Fichier | Rôle |
|---------|------|
| `mytowt-github.zip` | Repo complet prêt à push (93 fichiers) |
| `CLAUDE.md` | Documentation projet pour Claude Code |
| `README.md` | Page d'accueil GitHub |
| `Dockerfile` | Image Docker Python 3.12 |
| `docker-compose.yml` | Stack app + PostgreSQL |
| `requirements.txt` | Dépendances Python pinées |
| `.env.example` | Variables d'environnement |
| `.gitignore` | Exclusions Git |

---

## En cas de problème

### L'app ne démarre pas après deploy
```bash
sudo docker logs towt-app-v2 --tail 30
```

### Revenir à la version précédente
```bash
git log --oneline -5            # Trouver le commit
git checkout <commit-hash> -- app/  # Restaurer les fichiers
sudo docker cp app towt-app-v2:/app/
sudo docker restart towt-app-v2
```

### Migration de base de données nécessaire
Claude Code peut générer le script SQL, mais il faut l'exécuter manuellement :
```bash
sudo docker exec towt-app-v2 python3 -c "
import asyncio
from app.database import engine
from sqlalchemy import text
async def run():
    async with engine.begin() as conn:
        await conn.execute(text('ALTER TABLE ...'))
asyncio.run(run())
"
```
