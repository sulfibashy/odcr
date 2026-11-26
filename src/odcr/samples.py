"""Sample `orders` dataset used by `odcr seed`, the scaffolded projects and the test-suite.

batch-001 is clean; batch-002 breaks the contract on purpose (NULL customer, unknown status,
duplicate order id, negative amount) so you can see a failing run straight away.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

COLUMNS: list[tuple[str, str]] = [
    ("order_id", "integer"),
    ("customer_id", "integer"),
    ("status", "string"),
    ("amount", "decimal"),
    ("order_date", "date"),
    ("load_id", "string"),
]

GOOD = [
    (1, 101, "NEW", Decimal("10.50"), dt.date(2026, 11, 1), "batch-001"),
    (2, 102, "PAID", Decimal("20.00"), dt.date(2026, 11, 1), "batch-001"),
    (3, 103, "SHIPPED", Decimal("30.25"), dt.date(2026, 11, 2), "batch-001"),
    (4, 101, "CANCELLED", Decimal("5.00"), dt.date(2026, 11, 2), "batch-001"),
]

BAD = [
    (10, None, "NEW", Decimal("10.00"), dt.date(2026, 11, 3), "batch-002"),
    (11, 105, "LOST", Decimal("15.00"), dt.date(2026, 11, 3), "batch-002"),
    (11, 106, "PAID", Decimal("-3.00"), dt.date(2026, 11, 3), "batch-002"),
    (12, 107, "PAID", Decimal("8.00"), dt.date(2026, 11, 3), "batch-002"),
]

ROWS = GOOD + BAD


def csv_text() -> str:
    lines = [",".join(c for c, _ in COLUMNS)]
    for r in ROWS:
        lines.append(",".join("" if v is None else str(v) for v in r))
    return "\n".join(lines) + "\n"
