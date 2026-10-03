from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Sale
from app.seed_data import make_sample_sales
from app.services.sales_reports import query_sales_summary, render_sales_report


def make_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return Session(engine)


def test_sales_summary_is_one_sql_aggregation_over_requested_dates() -> None:
    with make_session() as session:
        session.add_all(
            [
                Sale(
                    order_id="ORD-001",
                    order_date=date(2026, 9, 1),
                    product="Keyboard",
                    quantity=2,
                    unit_price=Decimal("10.00"),
                ),
                Sale(
                    order_id="ORD-001",
                    order_date=date(2026, 9, 1),
                    product="Mouse",
                    quantity=1,
                    unit_price=Decimal("5.00"),
                ),
                Sale(
                    order_id="ORD-002",
                    order_date=date(2026, 9, 2),
                    product="Keyboard",
                    quantity=1,
                    unit_price=Decimal("10.00"),
                ),
                Sale(
                    order_id="OUTSIDE",
                    order_date=date(2026, 8, 31),
                    product="Out of range",
                    quantity=10,
                    unit_price=Decimal("99.00"),
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

        summary = query_sales_summary(
            session, date(2026, 9, 1), date(2026, 9, 2)
        )

    assert summary == {
        "order_count": 2,
        "units_sold": 4,
        "revenue": Decimal("35.00"),
        "average_order_value": Decimal("17.50"),
        "product_count": 2,
    }
    assert len(statements) == 1
    assert "order_totals" in statements[0]


def test_html_template_renders_to_a_real_pdf() -> None:
    pdf = render_sales_report(
        {
            "order_count": 2,
            "units_sold": 3,
            "revenue": Decimal("25.00"),
            "average_order_value": Decimal("12.50"),
            "product_count": 2,
        },
        date(2026, 9, 1),
        date(2026, 9, 30),
    )

    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 1_000


def test_seed_data_contains_200_lines_across_100_orders() -> None:
    rows = make_sample_sales(date(2026, 9, 30))

    assert len(rows) == 200
    assert len({row.order_id for row in rows}) == 100
    assert len({row.product for row in rows}) == 5
