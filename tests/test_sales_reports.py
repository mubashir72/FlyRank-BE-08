import sqlite3
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Order
from app.seed_data import PRODUCTS, seed_orders
from app.services.sales_reports import query_orders_summary, render_sales_report


def make_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return Session(engine)


def test_order_summary_is_one_sql_aggregation_over_requested_dates() -> None:
    with make_session() as session:
        session.add_all(
            [
                Order(
                    customer="Alex",
                    product="Keyboard",
                    amount=Decimal("10.00"),
                    created_at=date(2026, 9, 1),
                ),
                Order(
                    customer="Alex",
                    product="Mouse",
                    amount=Decimal("5.00"),
                    created_at=date(2026, 9, 1),
                ),
                Order(
                    customer="Jordan",
                    product="Keyboard",
                    amount=Decimal("10.00"),
                    created_at=date(2026, 9, 2),
                ),
                Order(
                    customer="Outside",
                    product="Out of range",
                    amount=Decimal("99.00"),
                    created_at=date(2026, 8, 31),
                ),
            ]
        )
        session.commit()
        statements: list[str] = []
        event.listen(
            session.get_bind(),
            "before_cursor_execute",
            lambda _conn, _cursor, statement, _parameters, _context, _many: statements.append(
                statement
            ),
        )

        summary = query_orders_summary(
            session, date(2026, 9, 1), date(2026, 9, 2)
        )

    assert summary["order_count"] == 3
    assert summary["revenue"] == Decimal("25.00")
    assert summary["average_order_value"] == Decimal("8.33")
    assert summary["customer_count"] == 2
    assert summary["product_count"] == 2
    assert len(statements) == 1
    assert "orders" in statements[0]


def test_html_template_renders_to_a_real_pdf() -> None:
    pdf = render_sales_report(
        {
            "order_count": 2,
            "revenue": Decimal("25.00"),
            "average_order_value": Decimal("12.50"),
            "customer_count": 2,
            "product_count": 2,
        },
        date(2026, 9, 1),
        date(2026, 9, 30),
    )

    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 1_000


def test_seed_orders_clears_rows_and_reseeds_200_orders(tmp_path: Path) -> None:
    database_path = tmp_path / "report.db"

    assert seed_orders(database_path) == 200
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO orders (customer, product, amount, created_at)
            VALUES ('Sentinel', 'Removed on reseed', 25, '2026-09-01')
            """
        )
    assert seed_orders(database_path) == 200

    with sqlite3.connect(database_path) as connection:
        table_count = connection.execute(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchone()[0]
        row_count = connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        rows = connection.execute(
            "SELECT customer, product, amount, created_at FROM orders"
        ).fetchall()
        columns = [
            row[1]
            for row in connection.execute("PRAGMA table_info(orders)").fetchall()
        ]

    assert table_count == 1
    assert row_count == 200
    assert columns == ["id", "customer", "product", "amount", "created_at"]
    assert {row[1] for row in rows} <= set(PRODUCTS)
    assert all(5 <= row[2] <= 200 for row in rows)
    assert all(
        date.today() - timedelta(days=29) <= date.fromisoformat(row[3]) <= date.today()
        for row in rows
    )
    assert not any(row[0] == "Sentinel" for row in rows)
