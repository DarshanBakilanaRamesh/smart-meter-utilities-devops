from datetime import date
from decimal import Decimal
from pydantic import BaseModel, Field


class CustomerCreate(BaseModel):
    id: str
    name: str
    tariff_code: str = "STANDARD"


class MeterCreate(BaseModel):
    id: str
    customer_id: str
    unit: str = "kWh"


class ReadingCreate(BaseModel):
    meter_id: str
    reading_date: date
    reading_value: Decimal = Field(ge=0)


class ReadingResponse(BaseModel):
    id: int
    meter_id: str
    reading_date: date
    reading_value: Decimal
    status: str


class BillResponse(BaseModel):
    id: int
    meter_id: str
    previous_reading: Decimal
    current_reading: Decimal
    consumption_kwh: Decimal
    energy_amount: Decimal
    basic_charge: Decimal
    vat_amount: Decimal
    total_amount: Decimal
    status: str


class IdocControlRecord(BaseModel):
    document_number: str
    message_type: str
    sender: str
    receiver: str


class IdocSegment(BaseModel):
    segment_type: str
    customer_id: str | None = None
    meter_id: str | None = None
    reading: Decimal | None = None
    reading_date: date | None = None


class IdocMessage(BaseModel):
    control_record: IdocControlRecord
    segments: list[IdocSegment]


class MessageAck(BaseModel):
    transaction_id: str
    status: str
    message: str
