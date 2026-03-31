# my_TOWT 🚢

Maritime operations management platform for [TOWT](https://towt.eu) — Transport à la Voile.

## Features

| Module | Description |
|--------|------------|
| **Planning** | Voyage legs, Gantt chart, distance/ETA calculation, CSV/PDF export |
| **Commercial** | Orders, client management, leg assignment, degressive pricing |
| **Cargo** | Packing lists, Bill of Lading, client portal, Excel import/export |
| **Escale** | Port calls, operations timeline, docker shifts, SOF |
| **On Board** | Statement of Facts, cargo documents, notifications |
| **Passengers** | Bookings, payments, documents, pre-boarding, crossing book |
| **Crew** | Members, leg assignments, annual calendar heatmap |
| **Finance** | OPEX, revenue, port costs, profitability analysis |
| **KPI** | CO₂ emissions, performance indicators |
| **Admin** | Users, roles, vessels, ports, settings |

## Quick Start

```bash
# 1. Clone
git clone https://github.com/juliengonde-5G/mytowt.git
cd mytowt

# 2. Configure
cp .env.example .env
# Edit .env with your values

# 3. Start
docker-compose up -d

# 4. Open
# http://localhost:8081 (dev) or http://51.178.59.174 (prod VPS OVH)
# Login: admin / towt2025
```

## Tech Stack

- **Backend**: FastAPI + SQLAlchemy async + PostgreSQL
- **Frontend**: Jinja2 + HTMX
- **Auth**: Cookie sessions + bcrypt
- **Deploy**: Docker + docker-compose

## Architecture

```
app/
├── models/      # 25 SQLAlchemy models
├── routers/     # 20 FastAPI routers (1 per module)
├── templates/   # 91 Jinja2 templates
├── static/      # CSS design system + logos
└── utils/       # Shared utilities
```

See [CLAUDE.md](CLAUDE.md) for detailed project documentation.

## License

Private — TOWT © 2025-2026
