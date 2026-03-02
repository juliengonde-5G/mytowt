# Déploiement my_TOWT sur VPS OVH

## Prérequis

- **VPS OVH** : Starter ou supérieur (2 Go RAM minimum recommandé)
- **OS** : Ubuntu 22.04 ou Debian 12
- **Domaine** : Un nom de domaine pointant vers l'IP du VPS (enregistrement DNS A)

## Étape 1 — Commander le VPS OVH

1. Aller sur [OVH VPS](https://www.ovhcloud.com/fr/vps/)
2. Choisir **VPS Starter** (~3,50€/mois) ou **VPS Value** (~6€/mois)
   - Starter : 1 vCPU, 2 Go RAM, 20 Go SSD — suffisant pour démarrer
   - Value : 2 vCPU, 4 Go RAM, 40 Go SSD — recommandé pour la production
3. Choisir **Ubuntu 22.04** comme système d'exploitation
4. Noter l'adresse IP fournie après installation

## Étape 2 — Configurer le DNS

Dans votre gestionnaire DNS OVH (ou autre registrar) :

```
Type   | Nom      | Valeur
-------|----------|-------------------
A      | towt     | <IP_DU_VPS>
CNAME  | www.towt | towt.votre-domaine.com
```

Attendre la propagation DNS (quelques minutes à quelques heures).

## Étape 3 — Préparer le VPS

Se connecter en SSH :

```bash
ssh root@<IP_DU_VPS>
```

### 3.1 — Mise à jour du système

```bash
apt update && apt upgrade -y
```

### 3.2 — Installer Docker

```bash
# Installer Docker
curl -fsSL https://get.docker.com | sh

# Ajouter votre utilisateur au groupe docker (optionnel)
usermod -aG docker $USER

# Vérifier
docker --version
docker compose version
```

### 3.3 — Installer Git

```bash
apt install -y git
```

### 3.4 — Configurer le pare-feu

```bash
# Installer ufw si nécessaire
apt install -y ufw

# Règles de base
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable
```

### 3.5 — Sécuriser SSH (recommandé)

```bash
# Désactiver l'authentification par mot de passe (après avoir configuré les clés SSH)
# Modifier /etc/ssh/sshd_config :
#   PasswordAuthentication no
#   PermitRootLogin prohibit-password

# Redémarrer SSH
systemctl restart sshd
```

## Étape 4 — Déployer l'application

### 4.1 — Cloner le dépôt

```bash
cd /opt
git clone https://github.com/juliengonde-5G/mytowt.git
cd mytowt
```

### 4.2 — Configurer l'environnement

```bash
cp .env.example .env
nano .env
```

Modifier les valeurs suivantes :

```ini
POSTGRES_PASSWORD=un_mot_de_passe_fort_ici
SECRET_KEY=une_cle_secrete_64_caracteres
DOMAIN=towt.votre-domaine.com
CERTBOT_EMAIL=votre@email.com
```

Générer une clé secrète :

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### 4.3 — Lancer le déploiement

```bash
./scripts/deploy.sh first-run
```

Ce script va :
1. Construire les images Docker (app, nginx, postgres)
2. Démarrer les services
3. Obtenir un certificat SSL Let's Encrypt
4. Configurer le proxy Nginx avec HTTPS

### 4.4 — Vérifier

```bash
./scripts/deploy.sh status
```

L'application est maintenant accessible sur `https://towt.votre-domaine.com`

## Opérations courantes

### Mettre à jour l'application

```bash
cd /opt/mytowt
./scripts/deploy.sh update
```

### Voir les logs

```bash
./scripts/deploy.sh logs
```

### Sauvegarder la base de données

```bash
./scripts/backup.sh
```

### Restaurer une sauvegarde

```bash
gunzip -c backups/towt_planning_YYYYMMDD_HHMMSS.sql.gz | \
  docker exec -i towt-db psql -U towt_admin towt_planning
```

### Renouveler le certificat SSL

Le renouvellement est automatique via le conteneur certbot. Pour forcer :

```bash
./scripts/deploy.sh ssl
```

## Backup automatique (crontab)

```bash
crontab -e
```

Ajouter :

```
# Backup quotidien à 3h du matin
0 3 * * * /opt/mytowt/scripts/backup.sh >> /var/log/towt-backup.log 2>&1

# Renouvellement SSL tous les mois
0 4 1 * * /opt/mytowt/scripts/deploy.sh ssl >> /var/log/towt-ssl.log 2>&1
```

## Migration des données depuis le Synology

Si vous souhaitez migrer les données existantes du Synology :

### Exporter depuis le Synology

```bash
# Sur le Synology
docker exec towt-db pg_dump -U towt_admin towt_planning > towt_backup.sql
```

### Importer sur le VPS

```bash
# Copier le fichier
scp user@synology:/path/towt_backup.sql /tmp/

# Importer
docker exec -i towt-db psql -U towt_admin towt_planning < /tmp/towt_backup.sql
```

## Architecture de production

```
Internet
   │
   ▼
┌─────────────┐
│   Nginx     │ :80 (→ 301 HTTPS)
│  (SSL/TLS)  │ :443
└──────┬──────┘
       │ proxy_pass
       ▼
┌─────────────┐
│   FastAPI    │ :8000 (interne)
│  (uvicorn)  │ 2 workers
└──────┬──────┘
       │ asyncpg
       ▼
┌─────────────┐
│ PostgreSQL  │ :5432 (interne)
│    16       │
└─────────────┘
```

Tous les services communiquent sur un réseau Docker interne (`towt-net`). Seuls les ports 80 et 443 sont exposés.
