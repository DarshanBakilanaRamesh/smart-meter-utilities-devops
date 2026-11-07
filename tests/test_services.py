from datetime import date
from contextlib import closing

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker


@pytest.fixture
def client(tmp_path, monkeypatch):
    database_url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)

    from app import database

    test_engine = create_engine(
        database_url, connect_args={"check_same_thread": False}
    )
    # main creates tables during import, so redirect its engine first.
    monkeypatch.setattr(database, "engine", test_engine)
    try:
        from app.main import app

        database.Base.metadata.create_all(bind=test_engine)
        test_session = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)

        def override_get_db():
            with test_session() as db:
                yield db

        monkeypatch.setitem(app.dependency_overrides, database.get_db, override_get_db)
        with TestClient(app) as test_client:
            yield test_client
    finally:
        test_engine.dispose()


@pytest.fixture
def meter_with_reading(client):
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
    return client


def test_complete_meter_to_bill_flow(meter_with_reading):
    client = meter_with_reading
    second = client.post("/readings", json={
        "meter_id": "MTR-1001", "reading_date": "2026-07-18", "reading_value": 12820
    })
    assert second.status_code == 201

    bill = client.post("/bills/calculate/MTR-1001")
    assert bill.status_code == 200
    body = bill.json()
    assert float(body["consumption_kwh"]) == 370.0
    assert float(body["total_amount"]) == 168.39


def test_reject_decreasing_reading(meter_with_reading):
    client = meter_with_reading
    result = client.post("/readings", json={
        "meter_id": "MTR-1001", "reading_date": "2026-07-20", "reading_value": 12000
    })
    assert result.status_code == 422


@pytest.fixture
def idoc_payload():
    return {
        "control_record": {
            "document_number": "DOC-001", "message_type": "METER_READING",
            "sender": "UTILITY", "receiver": "PLATFORM",
        },
        "segments": [{
            "segment_type": "ZMETER", "meter_id": "MTR-1001",
            "reading_date": "2026-07-18", "reading": 12820,
        }],
    }


def assert_idoc_state(status, error, reading_count):
    from app import database, models

    # A separate session confirms that the changes were committed.
    with Session(database.engine) as db:
        message = db.get(models.MarketMessage, "DOC-001")
        assert message.status == status
        assert message.error_message == error
        assert db.scalar(select(func.count()).select_from(models.MarketMessage)) == 1
        assert db.scalar(select(func.count()).select_from(models.MeterReading)) == reading_count


def test_idoc_success(meter_with_reading, idoc_payload):
    response = meter_with_reading.post("/market-messages/idoc", json=idoc_payload)
    assert response.status_code == 200
    assert response.json() == {
        "transaction_id": "DOC-001", "status": "COMPLETED",
        "message": "IDoc-inspired meter reading processed",
    }
    assert_idoc_state("COMPLETED", None, 2)


@pytest.mark.parametrize("missing", ["segment", "meter_id", "reading_date", "reading"])
def test_idoc_missing_fields(meter_with_reading, idoc_payload, missing):
    if missing == "segment":
        idoc_payload["segments"] = []
    else:
        del idoc_payload["segments"][0][missing]
    response = meter_with_reading.post("/market-messages/idoc", json=idoc_payload)
    assert response.status_code == 422
    detail = "Required ZMETER segment fields are missing"
    assert response.json() == {"detail": detail}
    assert_idoc_state("FAILED", detail, 1)


@pytest.mark.parametrize("changes, status, detail", [
    ({"meter_id": "UNKNOWN"}, 404, "Meter does not exist"),
    ({"reading_date": "2026-07-01"}, 409, "Duplicate reading date for meter"),
    ({"reading": 12000}, 422, "Current reading cannot be lower than previous reading"),
    ({"reading_date": "2026-06-30"}, 422, "Reading date must be after previous reading date"),
    ({"reading": -1}, 422, "Invalid meter reading: reading_value: Input should be greater than or equal to 0"),
])
def test_idoc_invalid_reading(meter_with_reading, idoc_payload, changes, status, detail):
    idoc_payload["segments"][0].update(changes)
    response = meter_with_reading.post("/market-messages/idoc", json=idoc_payload)
    assert response.status_code == status
    assert response.json() == {"detail": detail}
    assert_idoc_state("FAILED", detail, 1)


def test_idoc_inactive_meter(meter_with_reading, idoc_payload):
    from app import database, models

    with Session(database.engine) as db:
        db.get(models.Meter, "MTR-1001").status = "INACTIVE"
        db.commit()
    response = meter_with_reading.post("/market-messages/idoc", json=idoc_payload)
    assert response.status_code == 409
    assert response.json() == {"detail": "Meter is not active"}
    assert_idoc_state("FAILED", "Meter is not active", 1)


@pytest.mark.parametrize("failed", [False, True])
def test_idoc_duplicate_transaction(meter_with_reading, idoc_payload, failed):
    if failed:
        idoc_payload["segments"][0]["meter_id"] = "UNKNOWN"
    first = meter_with_reading.post("/market-messages/idoc", json=idoc_payload)
    assert first.status_code == (404 if failed else 200)
    response = meter_with_reading.post("/market-messages/idoc", json=idoc_payload)
    assert response.status_code == 409
    assert response.json() == {"detail": "Transaction already processed"}
    assert_idoc_state(
        "FAILED" if failed else "COMPLETED",
        "Meter does not exist" if failed else None,
        1 if failed else 2,
    )


def test_idoc_database_failure_rolls_back_reading(meter_with_reading, idoc_payload, monkeypatch):
    from app import models, services

    add_reading = services.add_reading

    def fail_after_reading(db, payload, *, commit=True):
        add_reading(db, payload, commit=commit)
        # Trigger a real flush failure after the new reading has been flushed.
        db.add(models.MeterReading(
            meter_id=payload.meter_id, reading_date=payload.reading_date,
            reading_value=payload.reading_value,
        ))
        db.flush()

    with monkeypatch.context() as patch:
        patch.setattr(services, "add_reading", fail_after_reading)
        response = meter_with_reading.post("/market-messages/idoc", json=idoc_payload)
    detail = "Database error while processing meter reading"
    assert response.status_code == 500
    assert response.json() == {"detail": detail}
    assert_idoc_state("FAILED", detail, 1)

    # The rolled-back reading can be submitted successfully under a new ID.
    idoc_payload["control_record"]["document_number"] = "DOC-002"
    assert meter_with_reading.post("/market-messages/idoc", json=idoc_payload).status_code == 200


@pytest.fixture
def switch_payload(meter_with_reading, monkeypatch):
    from app import services

    monkeypatch.setattr(services, "simulation_today", lambda: date(2026, 11, 7))
    return {
        "request_id": "SW-001", "customer_id": "CUST-501", "meter_id": "MTR-1001",
        "old_supplier": "DEFAULT", "new_supplier": "DEMO-ENERGY",
        "requested_date": "2026-11-07",
    }


def assert_supplier_state(supplier, count):
    from app import database, models

    with Session(database.engine) as db:
        assert db.get(models.Meter, "MTR-1001").current_supplier == supplier
        assert db.scalar(select(func.count()).select_from(models.SupplierSwitch)) == count


def test_supplier_switch_success_and_history(client, switch_payload):
    response = client.post("/supplier-switches", json=switch_payload)
    assert response.status_code == 201
    first = response.json()
    assert first.items() >= switch_payload.items()
    assert first["status"] == "COMPLETED"
    assert first["rejection_reason"] is None
    assert first["created_at"]
    assert_supplier_state("DEMO-ENERGY", 1)
    switch_payload.update(request_id="SW-002", old_supplier="DEMO-ENERGY", new_supplier="SECOND-ENERGY")
    assert client.post("/supplier-switches", json=switch_payload).status_code == 201
    assert_supplier_state("SECOND-ENERGY", 2)
    assert client.get("/supplier-switches/SW-001").json() == first
    assert client.get("/supplier-switches/UNKNOWN").status_code == 404


@pytest.mark.parametrize("changes, reason", [
    ({"customer_id": "UNKNOWN"}, "Customer does not exist"),
    ({"meter_id": "UNKNOWN"}, "Meter does not exist"),
    ({"old_supplier": "WRONG"}, "Old supplier does not match current supplier"),
    ({"new_supplier": "DEFAULT"}, "New supplier must differ from old supplier"),
    ({"requested_date": "2026-11-06"}, "Requested date must be today (UTC) in this simulation"),
    ({"requested_date": "2026-11-08"}, "Requested date must be today (UTC) in this simulation"),
])
def test_supplier_switch_rejection(client, switch_payload, changes, reason):
    switch_payload.update(changes)
    response = client.post("/supplier-switches", json=switch_payload)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "REJECTED"
    assert body["rejection_reason"] == reason
    assert client.get("/supplier-switches/SW-001").json() == body
    assert_supplier_state("DEFAULT", 1)


@pytest.mark.parametrize("inactive", [False, True])
def test_supplier_switch_meter_eligibility(client, switch_payload, inactive):
    from app import database, models

    if inactive:
        with Session(database.engine) as db:
            db.get(models.Meter, "MTR-1001").status = "INACTIVE"
            db.commit()
        reason = "Meter is not active"
    else:
        assert client.post("/customers", json={"id": "OTHER", "name": "Other"}).status_code == 201
        switch_payload["customer_id"] = "OTHER"
        reason = "Meter does not belong to customer"
    body = client.post("/supplier-switches", json=switch_payload).json()
    assert body["status"] == "REJECTED"
    assert body["rejection_reason"] == reason
    assert_supplier_state("DEFAULT", 1)


@pytest.mark.parametrize("rejected", [False, True])
def test_supplier_switch_duplicate_id(client, switch_payload, rejected):
    if rejected:
        switch_payload["new_supplier"] = "DEFAULT"
    first = client.post("/supplier-switches", json=switch_payload)
    assert first.status_code == 201
    switch_payload["new_supplier"] = "ANOTHER"
    duplicate = client.post("/supplier-switches", json=switch_payload)
    assert duplicate.status_code == 409
    assert client.get("/supplier-switches/SW-001").json() == first.json()
    assert_supplier_state("DEFAULT" if rejected else "DEMO-ENERGY", 1)


@pytest.mark.parametrize("changes", [
    {"requested_date": "not-a-date"}, {"new_supplier": "   "}, {"request_id": ""},
])
def test_supplier_switch_malformed_input(client, switch_payload, changes):
    switch_payload.update(changes)
    assert client.post("/supplier-switches", json=switch_payload).status_code == 422
    assert_supplier_state("DEFAULT", 0)


def test_supplier_switch_rollback(client, switch_payload, monkeypatch):
    from sqlalchemy import event
    from sqlalchemy.exc import OperationalError
    from app import database, models, schemas, services

    def fail_history_insert(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO supplier_switches"):
            raise OperationalError(statement, parameters, Exception("Simulated write failure"))

    event.listen(database.engine, "before_cursor_execute", fail_history_insert)
    try:
        with Session(database.engine) as db:
            with pytest.raises(OperationalError):
                services.switch_supplier(db, schemas.SupplierSwitchCreate(**switch_payload))
            # The same session is usable after rollback.
            assert db.get(models.Meter, "MTR-1001").current_supplier == "DEFAULT"
    finally:
        event.remove(database.engine, "before_cursor_execute", fail_history_insert)
    assert_supplier_state("DEFAULT", 0)
    assert client.post("/supplier-switches", json=switch_payload).status_code == 201


def test_meter_explicit_supplier(client):
    from app import database, models

    assert client.post("/customers", json={"id": "C", "name": "Customer"}).status_code == 201
    response = client.post("/meters", json={
        "id": "M", "customer_id": "C", "current_supplier": "ORIGINAL",
    })
    assert response.status_code == 201
    assert response.json() == {"id": "M", "status": "CREATED"}
    with Session(database.engine) as db:
        assert db.get(models.Meter, "M").current_supplier == "ORIGINAL"


def test_sqlite_supplier_migration_preserves_data(client, tmp_path):
    import sqlite3
    from sqlalchemy import inspect
    from app.migrate_supplier_switches import migrate
    from app import models

    legacy_path = tmp_path / "legacy.db"
    with closing(sqlite3.connect(legacy_path)) as connection:
        connection.executescript("""
            CREATE TABLE customers (id VARCHAR(40) PRIMARY KEY, name VARCHAR(120), tariff_code VARCHAR(30));
            INSERT INTO customers VALUES ('C', 'Legacy Customer', 'STANDARD');
            CREATE TABLE meters (id VARCHAR(40) PRIMARY KEY, customer_id VARCHAR(40), unit VARCHAR(10), status VARCHAR(20));
            INSERT INTO meters VALUES ('M', 'C', 'kWh', 'ACTIVE');
            CREATE TABLE legacy_notes (note TEXT);
            INSERT INTO legacy_notes VALUES ('preserve me');
        """)
    legacy_engine = create_engine(f"sqlite:///{legacy_path.as_posix()}")
    try:
        # Populate the unchanged legacy tables as well as the old meters table.
        for table in (models.MeterReading.__table__, models.Bill.__table__, models.MarketMessage.__table__):
            table.create(legacy_engine)
        with legacy_engine.begin() as connection:
            connection.execute(models.MeterReading.__table__.insert(), {
                "meter_id": "M", "reading_date": date(2026, 1, 1), "reading_value": 100,
            })
            connection.execute(models.Bill.__table__.insert(), {
                "meter_id": "M", "previous_reading": 0, "current_reading": 100,
                "consumption_kwh": 100, "energy_amount": 35, "basic_charge": 12,
                "vat_amount": 8.93, "total_amount": 55.93,
            })
            connection.execute(models.MarketMessage.__table__.insert(), {
                "transaction_id": "LEGACY", "message_type": "READING",
                "sender": "S", "receiver": "R", "status": "FAILED", "error_message": "preserve reason",
            })
            snapshots = {
                table: connection.exec_driver_sql(f"SELECT * FROM {table}").all()
                for table in ("customers", "meter_readings", "bills", "market_messages", "legacy_notes")
            }
        backup = migrate(legacy_engine)
        with closing(sqlite3.connect(backup)) as connection:
            assert connection.execute("SELECT * FROM meters").fetchone() == ("M", "C", "kWh", "ACTIVE")
        with legacy_engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT * FROM meters").one() == ("M", "C", "kWh", "ACTIVE", "DEFAULT")
            assert inspect(connection).has_table("supplier_switches")
        with legacy_engine.begin() as connection:
            connection.exec_driver_sql("UPDATE meters SET current_supplier = 'MIGRATED-SUPPLIER'")
            connection.execute(models.SupplierSwitch.__table__.insert(), {
                "request_id": "HISTORY", "customer_id": "C", "meter_id": "M",
                "old_supplier": "DEFAULT", "new_supplier": "MIGRATED-SUPPLIER",
                "requested_date": date(2026, 1, 1), "status": "COMPLETED",
            })
        migrate(legacy_engine)  # Also preserves suppliers/history on subsequent runs.
        with legacy_engine.connect() as connection:
            for table, rows in snapshots.items():
                assert connection.exec_driver_sql(f"SELECT * FROM {table}").all() == rows
            assert connection.exec_driver_sql("SELECT current_supplier FROM meters").scalar() == "MIGRATED-SUPPLIER"
            assert connection.exec_driver_sql("SELECT request_id FROM supplier_switches").scalar() == "HISTORY"
    finally:
        legacy_engine.dispose()


def test_sqlite_migration_rolls_back_schema_failure(client, tmp_path):
    from sqlalchemy import event, inspect
    from sqlalchemy.exc import OperationalError
    from app.migrate_supplier_switches import migrate

    legacy_engine = create_engine(f"sqlite:///{(tmp_path / 'rollback.db').as_posix()}")
    with legacy_engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE meters (id TEXT PRIMARY KEY)")
        connection.exec_driver_sql("INSERT INTO meters VALUES ('KEEP')")

    def fail_create(conn, cursor, statement, parameters, context, executemany):
        if "CREATE TABLE supplier_switches" in statement:
            raise OperationalError(statement, parameters, Exception("Simulated schema failure"))

    event.listen(legacy_engine, "before_cursor_execute", fail_create)
    try:
        with pytest.raises(OperationalError):
            migrate(legacy_engine)
        with legacy_engine.connect() as connection:
            assert [column["name"] for column in inspect(connection).get_columns("meters")] == ["id"]
            assert connection.exec_driver_sql("SELECT id FROM meters").scalar() == "KEEP"
            assert not inspect(connection).has_table("supplier_switches")
        assert len(list(tmp_path.glob("rollback.db.*.bak"))) == 1
    finally:
        event.remove(legacy_engine, "before_cursor_execute", fail_create)
        legacy_engine.dispose()
