# my_TOWT — Guide de Déploiement

## Contenu du package

```
mytowt-deploy/
├── app/                  # Code source de l'application
├── docker-compose.yml    # Configuration Docker
├── Dockerfile            # Image Docker de l'app
├── requirements.txt      # Dépendances Python
├── .env.example          # Modèle de configuration
├── migration.sql         # Migrations SQL à exécuter
├── deploy.sh             # Script de déploiement automatique
├── backup.sh             # Script de sauvegarde DB
├── restore.sh            # Script de restauration DB
└── DEPLOY_README.md      # Ce fichier
```

## Déploiement rapide (Synology NAS)

### 1. Copier le package sur le NAS

```bash
# Depuis votre machine locale
scp mytowt-deploy.tar.gz admin@<IP_NAS>:/volume1/docker/
```

### 2. Extraire et déployer

```bash
# Sur le NAS (via SSH)
cd /volume1/docker
tar xzf mytowt-deploy.tar.gz
cd mytowt-deploy
chmod +x deploy.sh backup.sh restore.sh
./deploy.sh
```

Le script `deploy.sh` effectue automatiquement :
- Vérification de Docker et Docker Compose
- Création du `.env` avec une SECRET_KEY aléatoire
- Construction de l'image Docker
- Démarrage des services (app + PostgreSQL)
- Exécution des migrations SQL
- Configuration des permissions

### 3. Accéder à l'application

- **URL** : `http://<IP_NAS>:8081`
- **Login** : `admin` / `towt2025`

## Déploiement manuel

Si vous préférez ne pas utiliser le script automatique :

```bash
# 1. Configurer l'environnement
cp .env.example .env
nano .env   # Modifier SECRET_KEY et mots de passe

# 2. Construire et démarrer
docker-compose up -d --build

# 3. Exécuter les migrations
docker cp migration.sql towt-db:/tmp/migration.sql
docker exec towt-db psql -U towt_admin -d towt_planning -f /tmp/migration.sql

# 4. Permissions
docker exec towt-app-v2 chmod -R 755 /app/app/static/
```

## Commandes utiles

| Action | Commande |
|--------|----------|
| Voir les logs | `docker logs -f towt-app-v2` |
| Redémarrer l'app | `docker restart towt-app-v2` |
| Arrêter tout | `docker-compose down` |
| Arrêter + supprimer données | `docker-compose down -v` |
| Sauvegarder la DB | `./backup.sh` |
| Restaurer la DB | `./restore.sh backups/towt_backup_XXXXXXXX.sql.gz` |

## Mise à jour de l'application

Pour mettre à jour après des modifications du code :

```bash
# Si le code source est modifié localement
docker-compose up -d --build

# Si seuls les fichiers app/ ont changé (grâce au volume monté)
docker restart towt-app-v2
```

## Ports utilisés

| Service | Port interne | Port exposé |
|---------|-------------|-------------|
| Application (uvicorn) | 8000 | **8081** |
| PostgreSQL | 5432 | **5433** |

## Sauvegarde et restauration

### Sauvegarde automatique (cron)

Pour des sauvegardes quotidiennes sur le NAS :

```bash
# Ajouter au crontab (crontab -e)
0 2 * * * /volume1/docker/mytowt-deploy/backup.sh /volume1/docker/mytowt-deploy/backups >> /var/log/towt-backup.log 2>&1
```

### Restauration

```bash
# Lister les sauvegardes disponibles
ls -la backups/

# Restaurer une sauvegarde spécifique
./restore.sh backups/towt_backup_20260302_020000.sql.gz
```

## Dépannage

### L'application ne démarre pas
```bash
docker logs towt-app-v2
# Vérifier les erreurs de connexion DB ou de configuration
```

### La base de données ne répond pas
```bash
docker logs towt-db
docker exec towt-db pg_isready -U towt_admin
```

### Réinitialisation complète
```bash
docker-compose down -v    # Supprime les volumes (PERTE DE DONNÉES)
./deploy.sh               # Redéployer depuis zéro
```
