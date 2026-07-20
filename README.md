# Smart Meter Utilities DevOps Platform

A portfolio project inspired by SAP Utilities meter-to-bill processes.

## Features
- FastAPI REST API
- Meter/customer master data
- Meter reading validation
- Consumption and invoice calculation
- IDoc-inspired inbound messages and acknowledgements
- SQLite persistence
- Prometheus metrics
- Docker and Docker Compose
- Pytest tests
- GitHub Actions CI
- ABAP billing class and ABAP Unit tests

## Quick start

### Local Python
```bash
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open:
- Swagger: http://localhost:8000/docs
- Health: http://localhost:8000/health
- Metrics: http://localhost:8000/metrics

### Docker
```bash
docker compose up --build
```

Open:
- API: http://localhost:8000/docs
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000 (admin/admin)

## Demo sequence
1. POST `/customers`
2. POST `/meters`
3. POST `/readings` for an initial reading
4. POST `/readings` for a later reading
5. POST `/bills/calculate/{meter_id}`
6. POST `/market-messages/idoc`
7. GET `/dashboard/summary`
