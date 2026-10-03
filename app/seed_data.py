from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from app.database import Base, SessionLocal, engine
from app.models import Sale

PRODUCTS = [
    ("Wireless headphones", Decimal("79.99")),
    ("USB-C hub", Decimal("49.50")),
    ("Laptop stand", Decimal("34.00")),
    ("Mechanical keyboard", Decimal("119.00")),
    ("Webcam", Decimal("64.95")),
]


def make_sample_sales(today: date | None = None) -> list[Sale]:
    report_date = today or date.today()
    return [
        Sale(
            order_id=f"ORD-{index // 2 + 1:03}",
            order_date=report_date - timedelta(days=(index // 2) % 30),
            product=PRODUCTS[(index * 7) % len(PRODUCTS)][0],
            quantity=index % 4 + 1,
            unit_price=PRODUCTS[(index * 7) % len(PRODUCTS)][1],
        )
        for index in range(200)
    ]


def seed_sales() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        if session.scalar(select(func.count()).select_from(Sale)) == 0:
            session.add_all(make_sample_sales())
            session.commit()


if __name__ == "__main__":
    seed_sales()
