from fastapi import Depends, FastAPI, HTTPException, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import ValidationError
from sqlalchemy import func, inspect, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from app import models, schemas, services
from app.database import Base, engine, get_db

if inspect(engine).has_table("meters") and "current_supplier" not in {
    column["name"] for column in inspect(engine).get_columns("meters")
}:
    raise RuntimeError("Existing database needs migration: run python -m app.migrate_supplier_switches")
Base.metadata.create_all(bind=engine)
app = FastAPI(title="Smart Meter Utilities DevOps Platform", version="1.0.0")

READINGS = Counter("meter_readings_received_total", "Meter readings received", ["status"])
BILLS = Counter("billing_jobs_total", "Billing jobs", ["status"])
MESSAGES = Counter("market_messages_total", "Market messages", ["status"])
LATENCY = Histogram("utility_api_processing_seconds", "Processing latency", ["operation"])


@app.get("/health")
def health():
    return {"status": "UP", "service": "utilities-platform"}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/customers", status_code=201)
def create_customer(payload: schemas.CustomerCreate, db: Session = Depends(get_db)):
    if db.get(models.Customer, payload.id):
        raise HTTPException(409, "Customer already exists")
    customer = models.Customer(**payload.model_dump())
    db.add(customer)
    db.commit()
    return {"id": customer.id, "status": "CREATED"}


@app.post("/meters", status_code=201)
def create_meter(payload: schemas.MeterCreate, db: Session = Depends(get_db)):
    if db.get(models.Meter, payload.id):
        raise HTTPException(409, "Meter already exists")
    if not db.get(models.Customer, payload.customer_id):
        raise HTTPException(404, "Customer does not exist")
    meter = models.Meter(**payload.model_dump())
    db.add(meter)
    db.commit()
    return {"id": meter.id, "status": "CREATED"}


@app.post("/readings", response_model=schemas.ReadingResponse, status_code=201)
def create_reading(payload: schemas.ReadingCreate, db: Session = Depends(get_db)):
    with LATENCY.labels("reading").time():
        try:
            result = services.add_reading(db, payload)
            READINGS.labels(result.status).inc()
            return result
        except HTTPException:
            READINGS.labels("REJECTED").inc()
            raise


@app.post("/supplier-switches", response_model=schemas.SupplierSwitchResponse, status_code=201)
def create_supplier_switch(payload: schemas.SupplierSwitchCreate, db: Session = Depends(get_db)):
    return services.switch_supplier(db, payload)


@app.get("/supplier-switches/{request_id}", response_model=schemas.SupplierSwitchResponse)
def get_supplier_switch(request_id: str, db: Session = Depends(get_db)):
    request = db.get(models.SupplierSwitch, request_id)
    if request is None:
        raise HTTPException(404, "Supplier-switch request does not exist")
    return request


@app.post("/bills/calculate/{meter_id}", response_model=schemas.BillResponse)
def bill(meter_id: str, db: Session = Depends(get_db)):
    with LATENCY.labels("billing").time():
        try:
            result = services.calculate_bill(db, meter_id)
            BILLS.labels("SUCCESS").inc()
            return result
        except HTTPException:
            BILLS.labels("FAILED").inc()
            raise


@app.post("/market-messages/idoc", response_model=schemas.MessageAck)
def process_idoc(payload: schemas.IdocMessage, db: Session = Depends(get_db)):
    control = payload.control_record
    if db.get(models.MarketMessage, control.document_number):
        raise HTTPException(409, "Transaction already processed")

    message = models.MarketMessage(
        transaction_id=control.document_number,
        message_type=control.message_type,
        sender=control.sender,
        receiver=control.receiver,
        status="RECEIVED",
    )
    db.add(message)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if db.get(models.MarketMessage, control.document_number):
            raise HTTPException(409, "Transaction already processed") from None
        raise

    try:
        meter_segment = next((s for s in payload.segments if s.segment_type == "ZMETER"), None)
        if (
            not meter_segment or not meter_segment.meter_id
            or meter_segment.reading is None or not meter_segment.reading_date
        ):
            raise HTTPException(422, "Required ZMETER segment fields are missing")

        reading = schemas.ReadingCreate(
            meter_id=meter_segment.meter_id,
            reading_date=meter_segment.reading_date,
            reading_value=meter_segment.reading,
        )
        services.add_reading(db, reading, commit=False)
        message.status = "COMPLETED"
        db.commit()
    except (HTTPException, ValidationError, SQLAlchemyError) as exc:
        # Undo the reading and reset the session before saving the failure.
        db.rollback()
        if isinstance(exc, HTTPException):
            error = exc
        elif isinstance(exc, ValidationError):
            detail = "; ".join(
                f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
                for item in exc.errors()
            )
            error = HTTPException(422, f"Invalid meter reading: {detail}")
        else:
            error = HTTPException(500, "Database error while processing meter reading")
        message.status = "FAILED"
        message.error_message = str(error.detail)[:255]
        try:
            db.commit()
        except SQLAlchemyError:
            db.rollback()
            raise
        MESSAGES.labels("FAILED").inc()
        if error is exc:
            raise
        raise error from exc
    MESSAGES.labels("COMPLETED").inc()
    return schemas.MessageAck(
        transaction_id=message.transaction_id,
        status=message.status,
        message="IDoc-inspired meter reading processed",
    )


@app.get("/dashboard/summary")
def dashboard(db: Session = Depends(get_db)):
    return {
        "customers": db.scalar(select(func.count()).select_from(models.Customer)),
        "meters": db.scalar(select(func.count()).select_from(models.Meter)),
        "readings": db.scalar(select(func.count()).select_from(models.MeterReading)),
        "bills": db.scalar(select(func.count()).select_from(models.Bill)),
        "market_messages": db.scalar(select(func.count()).select_from(models.MarketMessage)),
    }
