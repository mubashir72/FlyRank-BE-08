from datetime import date
from decimal import Decimal
from typing import TypedDict

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.models import Sale


class SalesSummary(TypedDict):
    order_count: int
    units_sold: int
    revenue: Decimal
    average_order_value: Decimal
    product_count: int


def query_sales_summary(
    session: Session, start_date: date, end_date: date
) -> SalesSummary:
    order_totals = (
        select(
            Sale.order_id.label("order_id"),
            func.sum(Sale.quantity * Sale.unit_price).label("order_total"),
        )
        .where(Sale.order_date.between(start_date, end_date))
        .group_by(Sale.order_id)
        .cte("order_totals")
    )
    statement = select(
        func.count(distinct(Sale.order_id)).label("order_count"),
        func.coalesce(func.sum(Sale.quantity), 0).label("units_sold"),
        func.coalesce(func.sum(Sale.quantity * Sale.unit_price), 0).label("revenue"),
        func.coalesce(
            select(func.avg(order_totals.c.order_total)).scalar_subquery(), 0
        ).label("average_order_value"),
        func.count(distinct(Sale.product)).label("product_count"),
    ).where(Sale.order_date.between(start_date, end_date))
    totals = session.execute(statement).one()

    return {
        "order_count": int(totals.order_count),
        "units_sold": int(totals.units_sold),
        "revenue": Decimal(totals.revenue),
        "average_order_value": Decimal(totals.average_order_value),
        "product_count": int(totals.product_count),
    }
