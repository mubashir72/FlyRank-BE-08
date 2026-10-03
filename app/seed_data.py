import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from app.config import settings

CUSTOMERS = (
    "Alex Morgan",
    "Jordan Lee",
    "Sam Taylor",
    "Casey Patel",
    "Riley Chen",
    "Jamie Rivera",
    "Avery Kim",
    "Drew Wilson",
)
PRODUCTS = (
    "Wireless headphones",
    "USB-C hub",
    "Laptop stand",
    "Mechanical keyboard",
    "Webcam",
    "Portable SSD",
)


def seed_orders(database_path: Path | None = None) -> int:
    database_path = database_path or settings.database_path
    database_path = database_path.resolve()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    today = date.today()
    earliest_date = today - timedelta(days=29)
    orders = [
        (
            random.choice(CUSTOMERS),
            random.choice(PRODUCTS),
            round(random.uniform(5, 200), 2),
            (earliest_date + timedelta(days=random.randrange(30))).isoformat(),
        )
        for _ in range(200)
    ]

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer VARCHAR(120) NOT NULL,
                product VARCHAR(120) NOT NULL,
                amount NUMERIC(10, 2) NOT NULL CHECK (amount >= 0),
                created_at DATE NOT NULL
            )
            """
        )
        connection.execute("DELETE FROM orders")
        connection.executemany(
            """
            INSERT INTO orders (customer, product, amount, created_at)
            VALUES (?, ?, ?, ?)
            """,
            orders,
        )
        return connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0]


if __name__ == "__main__":
    print(f"Seeded {seed_orders()} orders into {settings.database_path}.")
