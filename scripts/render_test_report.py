from datetime import date, timedelta
from pathlib import Path

from app.database import SessionLocal
from app.services.sales_reports import get_report_data, render_sales_report


def main() -> None:
    end_date = date.today()
    start_date = end_date - timedelta(days=29)
    output_path = Path("reports") / "test.pdf"

    with SessionLocal() as session:
        report = get_report_data(session, start_date, end_date)
    render_sales_report(report, start_date, end_date, output_path=output_path)
    print(f"PDF report saved to {output_path.resolve()}")


if __name__ == "__main__":
    main()
