# CLAUDE.md — my_TOWT Project Guide

## What is this project?

**my_TOWT** is a maritime operations management platform for TOWT (Transport à la Voile), a French sailing cargo company. It manages vessel planning, commercial orders, cargo logistics, port calls, onboard operations, crew scheduling, passenger bookings, and financial tracking.

**Production URL**: http://51.178.59.174 (VPS OVH)
**Default login**: admin / towt2025

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI (Python 3.12), async |
| Database | PostgreSQL 16 via SQLAlchemy async + asyncpg |
| Frontend | Jinja2 templates + HTMX (no JS framework) |
| Auth | Cookie sessions, bcrypt, itsdangerous |
| CSS | Single `app/static/css/app.css` design system |
| Deployment | Docker on VPS OVH, behind nginx reverse proxy |

## Project Structure

```
mytowt/
├── app/
│   ├── main.py              # FastAPI app, router registration
│   ├── config.py             # Settings via pydantic-settings (.env)
│   ├── database.py           # Async engine, session factory, Base
│   ├── auth.py               # Password hashing, session tokens, get_current_user
│   ├── permissions.py        # Role-based matrix (9 roles × 10 modules)
│   ├── templating.py         # Jinja2 config + custom filters (|flag)
│   ├── i18n/                 # Translations (fr, en, es, pt-br, vi)
│   ├── models/               # SQLAlchemy ORM models
│   │   ├── user.py           # User
│   │   ├── vessel.py         # Vessel (fleet: Anemos, Artemis, Atlantis, Atlas)
│   │   ├── port.py           # Port (UN/LOCODE, coordinates)
│   │   ├── leg.py            # Leg (voyage segment: ETD/ETA/ATD/ATA)
│   │   ├── order.py          # Order + OrderAssignment
│   │   ├── operation.py      # EscaleOperation + DockerShift
│   │   ├── packing_list.py   # PackingList + PackingListBatch + PackingListAudit
│   │   ├── onboard.py        # SofEvent, OnboardNotification, CargoDocument
│   │   ├── passenger.py      # Booking, Passenger, Payment, Document, CabinPriceGrid
│   │   ├── crew.py           # CrewMember + CrewAssignment
│   │   ├── finance.py        # PortConfig, OpexParameter, LegFinance
│   │   ├── kpi.py            # LegKPI
│   │   ├── claim.py          # Claim (réclamations cargo)
│   │   ├── mrv.py            # MRV emissions reporting
│   │   ├── commercial.py     # CommClient (Pipedrive sync)
│   │   ├── stowage.py        # StowagePlan, StowageItem
│   │   ├── planning_share.py # PlanningShareLink
│   │   ├── vessel_position.py # VesselPosition (tracking)
│   │   ├── activity_log.py   # ActivityLog (audit trail)
│   │   └── co2_variable.py   # CO2 emission variables
│   ├── routers/              # One router per module
│   │   ├── planning_router.py    # /planning
│   │   ├── planning_ext_router.py # /planning/share/{token} (public)
│   │   ├── commercial_router.py  # /commercial
│   │   ├── cargo_router.py       # /cargo + /p/{token} (client portal)
│   │   ├── escale_router.py      # /escale
│   │   ├── onboard_router.py     # /onboard
│   │   ├── passenger_router.py   # /passengers
│   │   ├── passenger_ext_router.py  # /boarding/{token} (external)
│   │   ├── crew_router.py        # /crew
│   │   ├── finance_router.py     # /finance
│   │   ├── kpi_router.py         # /kpi
│   │   ├── claim_router.py       # /claims (cargo claims)
│   │   ├── mrv_router.py         # /mrv (emissions)
│   │   ├── pricing_router.py     # /pricing (grilles tarifaires)
│   │   ├── stowage_router.py     # /stowage (plan d'arrimage)
│   │   ├── tracking_router.py    # /tracking (API vessel positions)
│   │   ├── admin_router.py       # /admin
│   │   ├── dashboard_router.py   # /
│   │   ├── auth_router.py        # /login, /logout
│   │   └── api_ports.py          # /api/ports (autocomplete)
│   ├── templates/            # Jinja2 templates per module
│   │   ├── base.html         # Layout with sidebar
│   │   └── {module}/         # Module templates
│   ├── static/
│   │   ├── css/app.css       # Full design system
│   │   ├── img/              # Logos (SVG + PNG)
│   │   └── BILL_OF_LADING_TEMPLATE.docx
│   └── utils/
│       ├── crossing_book.py  # Passenger crossing book PDF
│       ├── file_validation.py # File upload validation
│       ├── navigation.py     # Navigation helpers
│       ├── notifications.py  # Notification system
│       ├── passenger_pdfs.py # Passenger document PDFs
│       ├── pipedrive.py      # Pipedrive CRM integration
│       ├── portal_security.py # Portal token security
│       ├── revolut.py        # Revolut payment integration
│       ├── timezones.py      # Timezone utilities
│       └── activity.py       # Activity logging
├── scripts/
│   ├── backup_db.sh          # Database backup (pg_dump + rotation)
│   ├── import_crew.py        # Import 44 crew members
│   ├── import_tonnage.py     # Import vessel tonnage data
│   ├── purge_access_logs.py  # Purge old portal access logs
│   └── seed_demo_data.py     # Seed demo data
├── rapports/                 # Daily audit reports
├── CLAUDE.md                 # This file
├── README.md
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── presentation_mytowt.html  # Seminar slideshow (14 slides, HTML/CSS)
├── .env.example
└── .gitignore
```

## Critical Patterns

### Database
- Session via `get_db()` dependency — auto-commit on success, rollback on error
- **Use `await db.flush()`** inside routes, NEVER `await db.commit()` (handled by middleware)
- Schema init via `Base.metadata.create_all` at startup
- Migrations: raw SQL `ALTER TABLE` (no Alembic yet)

### Routing
- Write endpoints: validate → modify → `await db.flush()` → redirect
- HTMX detection: `request.headers.get("HX-Request")` → return `HX-Redirect` header
- Non-HTMX: standard `RedirectResponse(status_code=303)`

### Templates
- Extend `base.html`, use `{% block topbar_actions %}` and `{% block content %}`
- Inline `<style>` per template (no separate CSS per page)
- Custom filter `|flag` converts country code → emoji flag

### Permissions
- 9 roles: administrateur, operation, armement, technique, data_analyst, marins, gestionnaire_passagers, commercial, manager_maritime
- 10 modules: planning, commercial, escale, finance, kpi, captain, crew, cargo, mrv, passengers
- Levels: C (consult), M (modify), S (suppress)
- Route dependency: `Depends(require_permission("module", "C"))` — enforced on ALL routes (GET=C, POST=M, DELETE=S)
- Sidebar visibility: `has_any_access(user, 'module')` in base.html
- Admin access: roles administrateur + data_analyst can access /admin/settings

### Security
- **SQL injection prevention**: `admin_router.py` uses `ALLOWED_TABLES` whitelist + parameterized queries (`.bindparams()`) for all dynamic table references
- **Route-level permissions**: ALL endpoints in planning, commercial, escale, cargo, passengers, crew, finance, kpi routers enforce `require_permission()` — GET requires C, POST requires M, DELETE requires S
- **External routes** (`/p/{token}`, `/boarding/{token}`) are excluded from permission checks (public access via token)
- **CORS**: Configured in `main.py` — restrict `allow_origins` in production

### CSS Design System
- Font: **Poppins** everywhere (templates, PDF exports, popups)
- CSS variables: `--towt-blue`, `--towt-green`, `--towt-sky`, `--towt-sky-dark`, `--warning`, etc.
- Utility classes in `app.css`: `.card`, `.card-title`, `.alert`, `.alert-success`, `.alert-error`, `.field-label`, `.field-value`, `.btn-outline`, `.leg-code`, `.account-grid`
- Prefer CSS classes over inline styles for consistency

### Forms
- Standard HTML `<form method="POST">`
- Helpers `pf()` (parse float), `pi()` (parse int) in cargo_router for form values

### External (no-auth) routes
- `/p/{token}` — client cargo packing list portal
- `/boarding/{token}` — passenger pre-boarding form

## Deployment

### Current (VPS OVH)
```bash
docker-compose up -d          # Start
docker restart towt-app-v2    # Restart after changes
```

### Database migrations
```bash
docker exec towt-app-v2 python3 -c "
import asyncio
from app.database import engine
from sqlalchemy import text
async def migrate():
    async with engine.begin() as conn:
        await conn.execute(text('ALTER TABLE x ADD COLUMN y TYPE'))
asyncio.run(migrate())
"
```

### Static files permissions
```bash
docker exec towt-app-v2 chmod -R 755 /app/app/static/
```

### Database backup
```bash
./scripts/backup_db.sh        # Manual backup
# Or via cron (daily at 2am):
# 0 2 * * * /path/to/mytowt/scripts/backup_db.sh >> /var/log/towt-backup.log 2>&1
```

## Maritime Glossary

| Term | Meaning |
|------|---------|
| Leg | Voyage segment (port A → port B) |
| leg_code | `{seq}{vessel_code}{dep_country}{arr_country}{year_digit}` e.g. `1AFRUS6` |
| ETD/ETA | Estimated Time of Departure/Arrival |
| ATD/ATA | Actual Time of Departure/Arrival |
| Escale | Port call (period vessel is in port) |
| SOF | Statement of Facts (port operations log) |
| BL/BOL | Bill of Lading (cargo document) |
| POL/POD | Port of Loading / Discharge |
| LOCODE | UN port code (e.g. FRFEC = Fécamp) |
| OPEX | Operating expenditure (daily vessel cost) |
| Docker shift | Stevedore work shift |
| Palette | Pallet: EPAL 120×80, USPAL 120×100 |

## Planned Enhancements (backlog)

1. Global activity logging system (journal d'activité admin)
2. Cargo: structured addresses (shipper/notify/consignee split into name/address/postal/city/country)
3. Cargo: description_of_goods field for Bill of Lading
4. Cargo: mandatory dimensions with helptexts
5. BL format: `TUAW_{voyage_id}_{bl_no}`, packages format, Number of OBL: 3
6. Arrival Notice generation from packing list
7. Packing List Excel template system (download/upload/auto-import)
8. Escale timeline split into 2 flows (operational + parallel activities)

## Do / Don't

**DO:**
- Run `docker restart towt-app-v2` after any Python file change
- Provide migration SQL when adding/modifying DB columns
- Use CSS utility classes (`.card`, `.alert`, `.field-label`, etc.) instead of inline styles
- Use parameterized queries (`.bindparams()`) for any dynamic SQL
- Add `require_permission("module", "C"/"M"/"S")` to every new endpoint
- Test on Docker before pushing

**DON'T:**
- Never call `await db.commit()` in routes — the session handles it
- Never modify `routers/__init__.py` — it must stay empty
- Never hardcode credentials in source — use .env
- Don't add heavy JS frameworks — the app uses HTMX
- Never use f-strings to interpolate table/column names in SQL — use `ALLOWED_TABLES` whitelist
- Don't use `Segoe UI` or `Inter` fonts — always use `Poppins` with `system-ui` fallback
