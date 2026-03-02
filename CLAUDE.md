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
│   ├── permissions.py        # Role-based matrix (6 roles × 14 modules)
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
│   │   └── kpi.py            # LegKPI
│   ├── routers/              # One router per module
│   │   ├── planning_router.py    # /planning
│   │   ├── commercial_router.py  # /commercial
│   │   ├── cargo_router.py       # /cargo + /p/{token} (client portal)
│   │   ├── escale_router.py      # /escale
│   │   ├── onboard_router.py     # /onboard
│   │   ├── passenger_router.py   # /passengers
│   │   ├── passenger_ext_router.py  # /boarding/{token} (external)
│   │   ├── crew_router.py        # /crew
│   │   ├── finance_router.py     # /finance
│   │   ├── kpi_router.py         # /kpi
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
│       └── crossing_book.py  # Passenger crossing book PDF
├── CLAUDE.md                 # This file
├── README.md
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
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
- 6 roles: administrateur, operation, armement, technique, data_analyst, marins
- Levels: C (consult), M (modify), S (suppress)
- Route dependency: `Depends(require_permission("module", "C"))`

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
- Keep templates self-contained (inline styles)
- Test on Docker before pushing

**DON'T:**
- Never call `await db.commit()` in routes — the session handles it
- Never modify `routers/__init__.py` — it must stay empty
- Never hardcode credentials in source — use .env
- Don't add heavy JS frameworks — the app uses HTMX
