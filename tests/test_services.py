from pathlib import Path
from fastapi.testclient import TestClient

db_file = Path("utilities.db")
if db_file.exists():
    db_file.unlink()

from app.main import app  # noqa: E402

client = TestClient(app)


def test_complete_meter_to_bill_flow():
    assert client.post("/customers", json={
        "id": "CUST-501", "name": "Demo Customer", "tariff_code": "STANDARD"
    }).status_code == 201

    assert client.post("/meters", json={
        "id": "MTR-1001", "customer_id": "CUST-501", "unit": "kWh"
    }).status_code == 201

    first = client.post("/readings", json={
        "meter_id": "MTR-1001", "reading_date": "2026-07-01", "reading_value": 12450
    })
    assert first.status_code == 201

    second = client.post("/readings", json={
        "meter_id": "MTR-1001", "reading_date": "2026-07-18", "reading_value": 12820
    })
    assert second.status_code == 201

    bill = client.post("/bills/calculate/MTR-1001")
    assert bill.status_code == 200
    body = bill.json()
    assert float(body["consumption_kwh"]) == 370.0
    assert float(body["total_amount"]) == 168.39


def test_reject_decreasing_reading():
    result = client.post("/readings", json={
        "meter_id": "MTR-1001", "reading_date": "2026-07-20", "reading_value": 12000
    })
    assert result.status_code == 422
