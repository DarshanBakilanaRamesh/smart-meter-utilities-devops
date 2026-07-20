from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    tariff_code: Mapped[str] = mapped_column(String(30), default="STANDARD")


class Meter(Base):
    __tablename__ = "meters"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"))
    unit: Mapped[str] = mapped_column(String(10), default="kWh")
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")


class MeterReading(Base):
    __tablename__ = "meter_readings"
    __table_args__ = (UniqueConstraint("meter_id", "reading_date"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    meter_id: Mapped[str] = mapped_column(ForeignKey("meters.id"))
    reading_date: Mapped[date] = mapped_column(Date)
    reading_value: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    status: Mapped[str] = mapped_column(String(20), default="VALIDATED")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Bill(Base):
    __tablename__ = "bills"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    meter_id: Mapped[str] = mapped_column(ForeignKey("meters.id"))
    previous_reading: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    current_reading: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    consumption_kwh: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    energy_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    basic_charge: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    vat_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    status: Mapped[str] = mapped_column(String(20), default="CREATED")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MarketMessage(Base):
    __tablename__ = "market_messages"
    transaction_id: Mapped[str] = mapped_column(String(60), primary_key=True)
    message_type: Mapped[str] = mapped_column(String(40))
    sender: Mapped[str] = mapped_column(String(60))
    receiver: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(20))
    error_message: Mapped[str | None] = mapped_column(String(255), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
