from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import TypedDict

from jinja2 import Environment, FileSystemLoader, select_autoescape
from playwright.sync_api import sync_playwright
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Order


class ProductRevenue(TypedDict):
    product: str
    revenue: Decimal


class DailyOrders(TypedDict):
    date: date
    orders: int


class OrderLine(TypedDict):
    id: int
    customer: str
    product: str
    amount: Decimal
    created_at: date


class ReportData(TypedDict):
    total_orders: int
    total_revenue: Decimal
    top_products: list[ProductRevenue]
    orders_per_day: list[DailyOrders]
    all_orders: list[OrderLine]


template_environment = Environment(
    loader=FileSystemLoader(Path(__file__).parents[2] / "templates"),
    autoescape=select_autoescape(["html", "xml"]),
)


def get_report_data(
    session: Session,
    start_date: date | None = None,
    end_date: date | None = None,
    *,
    today: date | None = None,
) -> ReportData:
    report_date = end_date or today or date.today()
    week_start = report_date - timedelta(days=6)
    period_filter = (
        Order.created_at.between(start_date, end_date)
        if start_date is not None and end_date is not None
        else None
    )

    totals_query = select(
        func.count(Order.id).label("total_orders"),
        func.coalesce(func.sum(Order.amount), 0).label("total_revenue"),
    )
    product_query = (
        select(
            Order.product,
            func.sum(Order.amount).label("revenue"),
        )
        .group_by(Order.product)
        .order_by(func.sum(Order.amount).desc(), Order.product)
        .limit(5)
    )
    if period_filter is not None:
        totals_query = totals_query.where(period_filter)
        product_query = product_query.where(period_filter)

    totals = session.execute(totals_query).one()
    product_rows = session.execute(product_query).all()
    daily_query = (
        select(Order.created_at, func.count(Order.id).label("orders"))
        .where(Order.created_at.between(week_start, report_date))
        .group_by(Order.created_at)
        .order_by(Order.created_at)
    )
    if period_filter is not None:
        daily_query = daily_query.where(period_filter)
    daily_rows = session.execute(daily_query).all()
    orders_by_day = {row.created_at: int(row.orders) for row in daily_rows}
    all_orders_query = select(Order).order_by(Order.created_at, Order.id)
    if period_filter is not None:
        all_orders_query = all_orders_query.where(period_filter)
    all_order_rows = session.scalars(all_orders_query).all()

    return {
        "total_orders": int(totals.total_orders),
        "total_revenue": Decimal(str(totals.total_revenue)).quantize(
            Decimal("0.01")
        ),
        "top_products": [
            {
                "product": row.product,
                "revenue": Decimal(str(row.revenue)).quantize(Decimal("0.01")),
            }
            for row in product_rows
        ],
        "orders_per_day": [
            {
                "date": week_start + timedelta(days=offset),
                "orders": orders_by_day.get(
                    week_start + timedelta(days=offset), 0
                ),
            }
            for offset in range(7)
        ],
        "all_orders": [
            {
                "id": order.id,
                "customer": order.customer,
                "product": order.product,
                "amount": order.amount,
                "created_at": order.created_at,
            }
            for order in all_order_rows
        ],
    }


def render_sales_report(
    report: ReportData,
    start_date: date,
    end_date: date,
    *,
    output_path: Path | None = None,
) -> bytes:
    template = template_environment.get_template("sales_report.html")
    html = template.render(
        start_date=start_date,
        end_date=end_date,
        generated_date=date.today(),
        report=report,
    )
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page()
            page.set_content(html, wait_until="load")
            if output_path is not None:
                output_path.parent.mkdir(parents=True, exist_ok=True)
            return page.pdf(
                path=str(output_path) if output_path is not None else None,
                format="A4",
                print_background=True,
            )
        finally:
            browser.close()
