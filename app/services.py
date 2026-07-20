from decimal import Decimal, ROUND_HALF_UP
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app import models, schemas

ENERGY_PRICE = Decimal("0.35")
BASIC_CHARGE = Decimal("12.00")
VAT_RATE = Decimal("0.19")
HIGH_CONSUMPTION_LIMIT = Decimal("5000")


def add_reading(db: Session, payload: schemas.ReadingCreate) -> models.MeterReading:
    meter = db.get(models.Meter, payload.meter_id)
    if meter is None:
        raise HTTPException(status_code=404, detail="Meter does not exist")
    if meter.status != "ACTIVE":
        raise HTTPException(status_code=409, detail="Meter is not active")

    duplicate = db.scalar(
        select(models.MeterReading).where(
            models.MeterReading.meter_id == payload.meter_id,
            models.MeterReading.reading_date == payload.reading_date,
        )
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="Duplicate reading date for meter")

    previous = db.scalar(
        select(models.MeterReading)
        .where(models.MeterReading.meter_id == payload.meter_id)
        .order_by(models.MeterReading.reading_date.desc())
        .limit(1)
    )
    status = "VALIDATED"
    if previous:
        if payload.reading_date <= previous.reading_date:
            raise HTTPException(status_code=422, detail="Reading date must be after previous reading date")
        if payload.reading_value < previous.reading_value:
            raise HTTPException(status_code=422, detail="Current reading cannot be lower than previous reading")
        if payload.reading_value - previous.reading_value > HIGH_CONSUMPTION_LIMIT:
            status = "FLAGGED"

    reading = models.MeterReading(
        meter_id=payload.meter_id,
        reading_date=payload.reading_date,
        reading_value=payload.reading_value,
        status=status,
    )
    db.add(reading)
    db.commit()
    db.refresh(reading)
    return reading


def calculate_bill(db: Session, meter_id: str) -> models.Bill:
    readings = list(
        db.scalars(
            select(models.MeterReading)
            .where(models.MeterReading.meter_id == meter_id)
            .order_by(models.MeterReading.reading_date.desc())
            .limit(2)
        )
    )
    if len(readings) < 2:
        raise HTTPException(status_code=422, detail="At least two readings are required")

    current, previous = readings[0], readings[1]
    consumption = Decimal(current.reading_value) - Decimal(previous.reading_value)
    energy_amount = (consumption * ENERGY_PRICE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    subtotal = energy_amount + BASIC_CHARGE
    vat_amount = (subtotal * VAT_RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    total = (subtotal + vat_amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    bill = models.Bill(
        meter_id=meter_id,
        previous_reading=previous.reading_value,
        current_reading=current.reading_value,
        consumption_kwh=consumption,
        energy_amount=energy_amount,
        basic_charge=BASIC_CHARGE,
        vat_amount=vat_amount,
        total_amount=total,
        status="CREATED",
    )
    db.add(bill)
    db.commit()
    db.refresh(bill)
    return bill
