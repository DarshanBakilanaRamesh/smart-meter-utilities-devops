from fastapi import Depends, FastAPI, HTTPException, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app import models, schemas, services
from app.database import Base, engine, get_db

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
    db.commit()

    meter_segment = next((s for s in payload.segments if s.segment_type == "ZMETER"), None)
    if not meter_segment or not meter_segment.meter_id or meter_segment.reading is None or not meter_segment.reading_date:
        message.status = "FAILED"
        message.error_message = "Required ZMETER segment fields are missing"
        db.commit()
        MESSAGES.labels("FAILED").inc()
        raise HTTPException(422, message.error_message)

    services.add_reading(
        db,
        schemas.ReadingCreate(
            meter_id=meter_segment.meter_id,
            reading_date=meter_segment.reading_date,
            reading_value=meter_segment.reading,
        ),
    )
    message.status = "COMPLETED"
    db.commit()
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
