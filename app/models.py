from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import CheckConstraint, Date, DateTime, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_orders_amount_nonnegative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    customer: Mapped[str] = mapped_column(String(120), index=True)
    product: Mapped[str] = mapped_column(String(120), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    created_at: Mapped[date] = mapped_column(Date, index=True)


class Report(Base):
    __tablename__ = "reports"
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    path: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
