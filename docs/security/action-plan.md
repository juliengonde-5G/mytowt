# Plan d'action — Sécurisation my_TOWT

Référence : [`audit-v1.md`](audit-v1.md).

Priorisation par sprints + backlog continu. Chaque action référence le constat audit (`S-XX`).

## Sprint 1 — Critiques (J+7)

### A1.1 Rotation `SECRET_KEY` + refus démarrage si default (S-01)

- Générer : `python3 -c "import secrets; print(secrets.token_hex(32))"` → injecter dans `.env` prod uniquement.
- Modifier `app/main.py:65-73` : `raise RuntimeError(...)` au lieu de `logger.warning(...)` quand `APP_ENV=production` et `SECRET_KEY` par défaut.
- Documenter rotation tous les 12 mois minimum.

### A1.2 Rotation mot de passe Postgres (S-02)

- Choix gestionnaire de secrets : Doppler (SaaS) ou HashiCorp Vault (self-hosted VPS OVH).
- Migration `.env` → secrets manager pour `POSTGRES_PASSWORD`, `SECRET_KEY`, `PIPEDRIVE_API_TOKEN`.
- Renommer compte DB : `towt_admin` → `app_user` (cohérent post-liquidation).

### A1.3 `must_change_password` enforcement (S-05)

Le champ `User.must_change_password` est ajouté en Phase 1 (cette branche). Ajouter :
- Endpoint `POST /admin/my-account/change-password` dans `auth_router.py`.
- Middleware (ou dépendance globale `get_current_user`) qui redirige vers cette route si `must_change_password=True` ET path != `/admin/my-account/change-password` ET path != `/logout`.
- Validation côté serveur : nouveau mot de passe ≥ 12 chars, classes mixées, ≠ password actuel.

### A1.4 Fermeture port DB (S-03)

- Retirer `ports: - "5433:5432"` de `docker-compose.yml`.
- Si accès externe nécessaire (debug ponctuel) : tunnel SSH `ssh -L 5433:db:5432 user@vps`.

### A1.5 Auth API tracking (S-04)

- Ajouter `TRACKING_API_TOKEN` dans `Settings` (`app/config.py`), valeur via `.env`.
- Ajouter dépendance `verify_tracking_token` dans `tracking_router.py` :
  ```python
  def verify_tracking_token(x_api_token: str = Header(...)):
      if not secrets.compare_digest(x_api_token, settings.TRACKING_API_TOKEN):
          raise HTTPException(401, "Invalid token")
  ```
- L'appliquer aux 5 endpoints `/api/tracking/*`.
- Mettre à jour les flows Power Automate pour envoyer le header.
- Rotation trimestrielle du token.

## Sprint 2 — Élevés (J+21)

### A2.1 CSRF form strict (S-06)

- Créer dépendance `verify_csrf_form` dans `app/csrf.py` :
  ```python
  async def verify_csrf_form(request: Request, csrf_token: str = Form(...)):
      cookie = request.cookies.get(CSRF_COOKIE_NAME)
      if not cookie or not secrets.compare_digest(csrf_token, cookie):
          raise HTTPException(403, "CSRF validation failed")
  ```
- L'ajouter à toutes les routes POST/PUT/DELETE non-exemptées (planning, commercial, escale, finance, etc.).
- Test : POST sans champ `csrf_token` → 403.

### A2.2 CSP renforcée (S-07)

- Externaliser les inline scripts critiques (`base.html:12-18` HTMX CSRF injection) en `/static/js/csrf-htmx.js`.
- Pour les inline restants, introduire un nonce CSP par requête :
  ```python
  nonce = secrets.token_urlsafe(16)
  csp = f"... script-src 'self' 'nonce-{nonce}' https://unpkg.com; ..."
  request.state.csp_nonce = nonce
  ```
- Templates : `<script nonce="{{ request.state.csp_nonce }}">...</script>`.
- Supprimer `'unsafe-inline'` de `script-src` puis de `style-src`.

### A2.3 Hash des tokens portail (S-08)

- Migration : `ALTER TABLE portal_access_logs ADD COLUMN token_hash CHAR(64);`
- Backfill : `UPDATE portal_access_logs SET token_hash = encode(sha256(token::bytea), 'hex');`
- `DROP COLUMN token;` après backfill validé.
- Modifier `app/utils/portal_security.py:46` pour stocker `hashlib.sha256(token.encode()).hexdigest()`.

### A2.4 Introduction Alembic (S-09)

- `pip install alembic` + `alembic init migrations`.
- Configurer `alembic.ini` avec `DATABASE_URL` depuis `Settings`.
- `alembic revision --autogenerate -m "0001_initial"` post-reset.
- Convertir `migration.sql` en migrations versionnées.
- Lifecycle : `alembic upgrade head` au démarrage (remplacer `Base.metadata.create_all`).

### A2.5 Rate-limit persistant (S-10)

- Option A (recommandée) : ajouter Redis au `docker-compose.yml`, rate-limit via `redis-py` + sliding window.
- Option B (sans dépendance) : table `rate_limit_attempts(ip, attempted_at)` + cleanup périodique.
- Migrer `_login_attempts` (`auth_router.py:20`) et `_token_attempts` (`portal_security.py:13`).

## Sprint 3 — Moyens (J+60)

### A3.1 Révocation session server-side (S-11)

- Table `user_sessions(id, user_id, jti, created_at, last_seen_at, revoked_at, ip_hash, user_agent)`.
- `create_session_token()` : insert + retourne `jti` dans le payload `itsdangerous`.
- `get_current_user` : vérifie `jti` non-revoqué + non-expiré.
- Endpoint `POST /admin/my-account/logout-all` → set `revoked_at = now()` pour toutes les sessions du user.
- Auto-revoke sur changement mot de passe / rôle.

### A3.2 Maintenance mode en BDD (S-12)

- Table `app_settings(key VARCHAR PRIMARY KEY, value JSONB, updated_at)`.
- Migrer `MAINTENANCE_FLAG` fichier → row `('maintenance', {"enabled": true, "message": "..."})`.
- Cache 5 s in-memory pour éviter une requête DB par hit.

### A3.3 Politique mots de passe (S-14)

- Ajouter `zxcvbn-python` aux requirements.
- Validation côté serveur : `zxcvbn.zxcvbn(password)['score'] >= 3`.
- Blacklist top-1k mots de passe fuités (haveibeenpwned `pwned-passwords-top-1k.txt` embarqué).
- Historique des 5 derniers hashs dans `user_password_history`.

### A3.4 Quota upload (S-15)

- Middleware `BodySizeLimitMiddleware` dans `app/main.py` :
  ```python
  if int(request.headers.get("content-length", 0)) > MAX_UPLOAD_SIZE:
      return JSONResponse({"detail": "Payload too large"}, 413)
  ```
- Limites : 10 MB par défaut, 50 MB pour `/api/tracking/upload` (override par dépendance).

### A3.5 CORS HTTPS-only (S-16)

- Retirer `http://51.178.59.174` de `allow_origins`.
- Forcer redirect HTTP → HTTPS au niveau nginx (déjà fait probablement, à vérifier).

### A3.6 Anonymisation IP (S-17)

- Ajouter `IP_HASH_PEPPER` dans `Settings` (rotatif).
- `hash_ip(ip) = sha256(ip + PEPPER).hexdigest()[:16]`.
- Migrer `portal_access_log.ip_address` (string IP brute) → `ip_hash CHAR(16)`.
- Idem pour `activity_log` si applicable.

## Backlog continu

### B1 Headers COOP/COEP/CORP (S-18)

Ajouter dans `SecurityHeadersMiddleware` (`app/main.py:105`) :
```python
response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
# COEP "require-corp" demande audit images externes (tiles OSM)
```

### B2 Scan secrets pre-commit + CI

- `gitleaks` en pre-commit hook (`pre-commit run --all-files`).
- `gitleaks detect` en CI GitHub Actions sur chaque PR.

### B3 SAST en CI

- `bandit -r app/` (sécurité Python).
- `semgrep --config=p/python --config=p/security-audit`.
- `pip-audit` (CVE deps).
- Bloquant en CI sur findings high-severity.

### B4 Pentest externe annuel

- Premier pentest : 3 mois après go-live V2.
- Société recommandée : Synacktiv, Quarkslab, Devoteam Risk.
- Périmètre : webapp + API tracking + portails token.
- Bug bounty privé HackerOne / YesWeHack en complément.

### B5 RTO/RPO documentés

- RPO cible : 1 h (backup pg_dump horaire au lieu du quotidien actuel).
- RTO cible : 4 h (procédure restore documentée).
- Test restore trimestriel obligatoire.

### B6 Security.txt

`/.well-known/security.txt` déjà en place (`app/main.py:175-181`). À mettre à jour lors du rebrand V2 (nouveau email `security@kairos.app` ou similaire).
