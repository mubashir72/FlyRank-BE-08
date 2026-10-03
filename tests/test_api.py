from collections.abc import Generator
from datetime import date
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Report


@pytest.fixture
def session_factory() -> Generator[sessionmaker[Session], None, None]:
    test_engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=test_engine)
    test_session = sessionmaker(bind=test_engine, expire_on_commit=False)

    def override_get_db() -> Generator[Session, None, None]:
        with test_session() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    yield test_session
    app.dependency_overrides.clear()
    test_engine.dispose()


@pytest.fixture
def client(session_factory: sessionmaker[Session]) -> TestClient:
    return TestClient(app)


@pytest.fixture
def report_dir() -> Generator[Path, None, None]:
    with TemporaryDirectory(prefix=".test-reports-", dir=Path.cwd()) as directory:
        yield Path(directory)


def test_health_endpoint(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_generate_store_and_download_report(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
    report_dir: Path,
) -> None:
    from app.models import Order

    monkeypatch.setattr("app.main.settings.artifact_dir", str(report_dir))
    with session_factory() as session:
        session.add_all(
            [
                Order(
                    customer="Alex",
                    product="Keyboard",
                    amount=Decimal("25.00"),
                    created_at=date(2026, 9, 10),
                ),
                Order(
                    customer="Alex",
                    product="Mouse",
                    amount=Decimal("15.00"),
                    created_at=date(2026, 9, 10),
                ),
            ]
        )
        session.commit()
    body = {"start_date": "2026-09-01", "end_date": "2026-09-30"}

    response = client.post("/reports", json=body)

    assert response.status_code == 201
    report = response.json()
    assert report == {
        "id": report["id"],
        "file": f"/reports/{report['id']}/file",
    }
    generated_path = report_dir / f"{report['id']}.pdf"
    assert generated_path.read_bytes().startswith(b"%PDF-")

    status_response = client.get(f"/reports/{report['id']}")
    assert status_response.status_code == 200
    assert status_response.json()["id"] == report["id"]
    assert status_response.json()["path"] == generated_path.name
    assert status_response.json()["file"] == report["file"]
    assert status_response.json()["created_at"]

    download = client.get(report["file"])
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/pdf"
    assert download.content.startswith(b"%PDF-")

    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Report)) == 1
    assert client.get("/reports").json()[0]["id"] == report["id"]


def test_same_day_requests_reuse_report_unless_forced(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
    report_dir: Path,
) -> None:
    renders: list[bool] = []
    monkeypatch.setattr("app.main.settings.artifact_dir", str(report_dir))
    monkeypatch.setattr(
        "app.main.get_report_data",
        lambda *_args: {
            "total_orders": 0,
            "total_revenue": Decimal("0"),
            "top_products": [],
            "orders_per_day": [],
            "all_orders": [],
        },
    )

    def render(*_args: object, output_path: Path) -> bytes:
        renders.append(True)
        output_path.write_bytes(b"%PDF-report")
        return b"%PDF-report"

    monkeypatch.setattr("app.main.render_sales_report", render)

    first = client.post("/reports")
    second = client.post("/reports")
    forced = client.post("/reports", json={"force": True})

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["file"] == first.json()["file"]
    assert forced.status_code == 201
    assert forced.json()["id"] != first.json()["id"]
    assert first.json()["file"] == f"/reports/{first.json()['id']}/file"
    assert forced.json()["file"] == f"/reports/{forced.json()['id']}/file"
    assert renders == [True, True]
    assert len(list(report_dir.glob("*.pdf"))) == 2
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Report)) == 2


def test_report_rejects_inverted_date_range(client: TestClient) -> None:
    response = client.post(
        "/reports",
        json={"start_date": "2026-09-30", "end_date": "2026-09-01"},
    )

    assert response.status_code == 422


def test_unknown_report_and_file_return_not_found(client: TestClient) -> None:
    report_response = client.get("/reports/unknown")
    response = client.get("/reports/unknown/file")

    assert report_response.status_code == 404
    assert response.status_code == 404


def test_missing_report_file_returns_gone(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        report = Report(path="missing.pdf")
        session.add(report)
        session.commit()
        report_id = report.id

    response = client.get(f"/reports/{report_id}/file")

    assert response.status_code == 410
