import re
import sqlite3
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Order
from app.seed_data import PRODUCTS, seed_orders
from app.services.sales_reports import get_report_data, render_sales_report


def make_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return Session(engine)


def test_report_data_has_four_aggregated_sections() -> None:
    with make_session() as session:
        session.add_all(
            [
                Order(
                    customer="Alex",
                    product="Keyboard",
                    amount=Decimal("50.00"),
                    created_at=date(2026, 9, 30),
                ),
                Order(
                    customer="Jordan",
                    product="Keyboard",
                    amount=Decimal("25.00"),
                    created_at=date(2026, 9, 29),
                ),
                Order(
                    customer="Alex",
                    product="Mouse",
                    amount=Decimal("40.00"),
                    created_at=date(2026, 9, 25),
                ),
                Order(
                    customer="Sam",
                    product="Old product",
                    amount=Decimal("100.00"),
                    created_at=date(2026, 9, 23),
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

        report = get_report_data(
            session, date(2026, 9, 23), date(2026, 9, 30)
        )

    assert report["total_orders"] == 4
    assert report["total_revenue"] == Decimal("215.00")
    assert report["top_products"][:2] == [
        {"product": "Old product", "revenue": Decimal("100.00")},
        {"product": "Keyboard", "revenue": Decimal("75.00")},
    ]
    assert report["orders_per_day"] == [
        {"date": date(2026, 9, 24), "orders": 0},
        {"date": date(2026, 9, 25), "orders": 1},
        {"date": date(2026, 9, 26), "orders": 0},
        {"date": date(2026, 9, 27), "orders": 0},
        {"date": date(2026, 9, 28), "orders": 0},
        {"date": date(2026, 9, 29), "orders": 1},
        {"date": date(2026, 9, 30), "orders": 1},
    ]
    assert [
        (order["product"], order["created_at"])
        for order in report["all_orders"]
    ] == [
        ("Old product", date(2026, 9, 23)),
        ("Mouse", date(2026, 9, 25)),
        ("Keyboard", date(2026, 9, 29)),
        ("Keyboard", date(2026, 9, 30)),
    ]
    assert len(report["top_products"]) <= 5
    assert len(report) == 5
    assert len(report["all_orders"]) == report["total_orders"]
    assert len(statements) == 4
    assert "GROUP BY" in statements[1].upper()
    assert "LIMIT" in statements[1].upper()
    assert "GROUP BY" in statements[2].upper()


def test_html_template_renders_to_a_real_pdf() -> None:
    pdf = render_sales_report(
        {
            "total_orders": 2,
            "total_revenue": Decimal("25.00"),
            "top_products": [
                {"product": "Keyboard", "revenue": Decimal("25.00")}
            ],
            "orders_per_day": [
                {"date": date(2026, 9, day), "orders": 0}
                for day in range(24, 31)
            ],
            "all_orders": [
                {
                    "id": 1,
                    "customer": "Alex",
                    "product": "Keyboard",
                    "amount": Decimal("25.00"),
                    "created_at": date(2026, 9, 24),
                }
            ],
        },
        date(2026, 9, 1),
        date(2026, 9, 30),
    )

    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 1_000


def test_rendered_report_saves_a_multipage_pdf(tmp_path: Path) -> None:
    with make_session() as session:
        session.add_all(
            [
                Order(
                    customer=f"Customer {index:03}",
                    product=f"Product {index % 6}",
                    amount=Decimal("25.00"),
                    created_at=date(2026, 9, 30),
                )
                for index in range(200)
            ]
        )
        session.commit()
        report = get_report_data(
            session, date(2026, 9, 1), date(2026, 9, 30)
        )

    output_path = tmp_path / "reports" / "test.pdf"
    pdf = render_sales_report(
        report,
        date(2026, 9, 1),
        date(2026, 9, 30),
        output_path=output_path,
    )

    assert output_path.is_file()
    assert output_path.read_bytes() == pdf
    assert len(pdf) > 1_000
    assert len(re.findall(rb"/Type\s*/Page\b", pdf)) >= 2
    template = (
        Path(__file__).parents[1] / "templates" / "sales_report.html"
    ).read_text(encoding="utf-8")
    assert ".orders-table thead { display: table-header-group; }" in template
    assert (
        ".orders-table tr { break-inside: avoid; page-break-inside: avoid; }"
        in template
    )


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
