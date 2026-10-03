from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import TypedDict

from jinja2 import Environment, FileSystemLoader, select_autoescape
from playwright.sync_api import sync_playwright
from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.models import Order


class OrdersSummary(TypedDict):
    order_count: int
    revenue: Decimal
    average_order_value: Decimal
    customer_count: int
    product_count: int


template_environment = Environment(
    loader=FileSystemLoader(Path(__file__).parents[2] / "templates"),
    autoescape=select_autoescape(["html", "xml"]),
)


def query_orders_summary(
    session: Session, start_date: date, end_date: date
) -> OrdersSummary:
    date_filter = Order.created_at.between(start_date, end_date)
    statement = select(
        func.count(Order.id).label("order_count"),
        func.coalesce(func.sum(Order.amount), 0).label("revenue"),
        func.coalesce(func.round(func.avg(Order.amount), 2), 0).label(
            "average_order_value"
        ),
        func.count(distinct(Order.customer)).label("customer_count"),
        func.count(distinct(Order.product)).label("product_count"),
    ).where(date_filter)
    totals = session.execute(statement).one()

    return {
        "order_count": int(totals.order_count),
        "revenue": Decimal(str(totals.revenue)).quantize(Decimal("0.01")),
        "average_order_value": Decimal(str(totals.average_order_value)).quantize(
            Decimal("0.01")
        ),
        "customer_count": int(totals.customer_count),
        "product_count": int(totals.product_count),
    }


def render_sales_report(
    summary: OrdersSummary, start_date: date, end_date: date
) -> bytes:
    template = template_environment.get_template("sales_report.html")
    html = template.render(
        start_date=start_date,
        end_date=end_date,
        summary=summary,
    )
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page()
            page.set_content(html, wait_until="load")
            return page.pdf(format="A4", print_background=True)
        finally:
            browser.close()
