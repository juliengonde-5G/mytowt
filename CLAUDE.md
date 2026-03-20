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
│   │   ├── order.py          # Order (preferred_holds, rate_grid) + OrderAssignment
│   │   ├── commercial.py     # Client (ClientType: FREIGHT_FORWARDER, SHIPPER)
│   │   ├── hold.py           # Hold capacities + assignments (6 holds: 3 levels × 2 positions)
│   │   ├── operation.py      # EscaleOperation + DockerShift
│   │   ├── packing_list.py   # PackingList + PackingListBatch + PackingListAudit
│   │   ├── onboard.py        # SofEvent, OnboardNotification, CargoDocument
│   │   ├── passenger.py      # Booking, Passenger, Payment, Document, CabinPriceGrid
│   │   ├── crew.py           # CrewMember + CrewAssignment
│   │   ├── claim.py          # Claim (insurance: cargo, crew, hull — P&I / Hull / War Risk)
│   │   ├── finance.py        # PortConfig, OpexParameter, LegFinance
│   │   ├── kpi.py            # LegKPI
│   │   ├── mrv.py            # MrvParameter (MRV fuel reporting, SOF→MRV event mapping)
│   │   ├── co2_variable.py   # Co2Variable (decarbonation calculation with history)
│   │   ├── emission_parameter.py # EmissionParameter (global CO2 emission params)
│   │   ├── notification.py   # Notification (dashboard alerts: orders, messages, ETA shifts…)
│   │   ├── activity_log.py   # ActivityLog (user action tracking per module)
│   │   ├── portal_message.py # PortalMessage (threaded client/passenger ↔ company messaging)
│   │   ├── vessel_position.py # VesselPosition (GPS from satcom CSV: lat, lon, SOG, COG)
│   │   └── shared_link.py    # SharedLink (planning shared links with view tracking)
│   ├── routers/              # One router per module
│   │   ├── planning_router.py    # /planning
│   │   ├── commercial_router.py  # /commercial
│   │   ├── pricing_router.py     # /commercial/pricing (rate grids, clients, offers)
│   │   ├── cargo_router.py       # /cargo + /p/{token} (client portal)
│   │   ├── escale_router.py      # /escale
│   │   ├── onboard_router.py     # /onboard
│   │   ├── passenger_router.py   # /passengers
│   │   ├── passenger_ext_router.py  # /boarding/{token} (external)
│   │   ├── crew_router.py        # /crew
│   │   ├── claim_router.py       # /claims (insurance declarations, timeline, PDF)
│   │   ├── finance_router.py     # /finance
│   │   ├── kpi_router.py         # /kpi
│   │   ├── mrv_router.py         # /mrv (MRV fuel reporting)
│   │   ├── tracking_router.py    # /api/tracking (satcom CSV vessel positions)
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
│       ├── activity.py       # Activity logging helper (log_activity from any router)
│       ├── navigation.py     # Haversine distance calc (port-to-port in nautical miles)
│       ├── pipedrive.py      # Pipedrive CRM integration (org search, deal create/update)
│       ├── revolut.py        # Revolut Merchant API (passenger payment checkout + webhooks)
│       └── notifications.py  # Centralized notification creation (OnboardNotification)
├── CLAUDE.md                 # This file
├── README.md
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── presentation_mytowt.html  # Seminar slideshow (14 slides, HTML/CSS)
├── purge_commercial.py       # One-shot script to purge commercial data (grids + offers)
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
- Shared filter classes in `app.css`: `.planning-filters`, `.vessel-tabs`, `.vessel-tab`, `.year-selector`, `.year-btn`, `.leg-selector`, `.leg-chip` — reused across escale, cargo, commercial, passengers pages
- Prefer CSS classes over inline styles for consistency

### Forms
- Standard HTML `<form method="POST">`
- Helpers `pf()` (parse float), `pi()` (parse int) in cargo_router for form values

### External (no-auth) routes
- `/p/{token}` — client cargo packing list portal
- `/boarding/{token}` — passenger pre-boarding form

### List Filtering Pattern
- Escale, cargo, commercial (orders tab), and passengers pages share the same cascading filter: **vessel tabs → year selector → leg chips**
- CSS classes: `.planning-filters`, `.vessel-tabs`, `.vessel-tab`, `.year-selector`, `.year-btn`, `.leg-selector`, `.leg-chip` (all in `app.css`)
- Router pattern: query params `vessel`, `year`, `leg_id` — default to first active vessel + current year
- When no specific leg is selected, all legs for the vessel+year are shown
- Map tiles use CARTO (not OSM) to avoid 403 referer blocks: `https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png`

### External Integrations
- **Pipedrive CRM** (`utils/pipedrive.py`): org search, deal creation/update for commercial offers and transport orders
- **Revolut Merchant** (`utils/revolut.py`): passenger payment via Hosted Checkout Page → webhook callback updates `PassengerPayment`
- **Satcom CSV** (`tracking_router.py`): vessel position ingestion from satellite communication files

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
| Hold / Cale | Cargo compartment (6 holds: SUP_AV, SUP_AR, MIL_AV, MIL_AR, INF_AV, INF_AR) |
| MRV | Monitoring, Reporting and Verification (EU fuel emissions regulation) |
| P&I | Protection & Indemnity (maritime insurance) |
| Satcom | Satellite communication (vessel GPS tracking) |
| SOG/COG | Speed Over Ground / Course Over Ground |
| Rate Grid | Tariff grid per route (freight forwarder / shipper pricing) |

## Planned Enhancements (backlog)

1. ~~Global activity logging system~~ ✓ (implemented: `activity_log.py` + `utils/activity.py`)
2. Cargo: structured addresses (shipper/notify/consignee split into name/address/postal/city/country)
3. Cargo: description_of_goods field for Bill of Lading
4. Cargo: mandatory dimensions with helptexts
5. BL format: `TUAW_{voyage_id}_{bl_no}`, packages format, Number of OBL: 3
6. Arrival Notice generation from packing list
7. Packing List Excel template system (download/upload/auto-import)
8. Escale timeline split into 2 flows (operational + parallel activities)
9. ~~Shared links with view tracking~~ ✓ (implemented: `shared_link.py` + `planning/shared_links.html`)
10. ~~Escale-style vessel/year/leg filter across modules~~ ✓ (cargo, commercial, passengers)
11. ~~Client portal improvements~~ ✓ (YouTube videos, document upload, map fixes, favicon)
12. ~~Multi-cabin passenger bookings~~ ✓ (multiple cabins per booking)
13. ~~Commercial offer → order generation~~ ✓ (`order_from_offer.html`)
14. ~~Rate grid palette format (EPAL/USPAL)~~ ✓ (`palette_format` column on RateGrid)

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
