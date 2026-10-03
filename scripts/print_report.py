import json
from datetime import date
from decimal import Decimal

from app.database import SessionLocal
from app.services.sales_reports import get_report_data


def json_default(value: object) -> float | str:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, date):
        return value.isoformat()
    raise TypeError(f"Cannot serialize {type(value).__name__} to JSON")


def main() -> None:
    with SessionLocal() as session:
        report = get_report_data(session)
    print(json.dumps(report, default=json_default, indent=2))


if __name__ == "__main__":
    main()
