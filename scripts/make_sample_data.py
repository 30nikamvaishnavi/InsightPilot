"""Generate the small, fully synthetic sample data set (seeded, reproducible).

Writes three files in three formats so the ingestion pipeline is exercised:
  data/sample/sales.csv      (CSV)
  data/sample/returns.json   (JSON records)
  data/sample/targets.xlsx   (Excel)
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent.parent / "data" / "sample"
REGIONS = ["North", "South", "East", "West"]
CATALOG = {
    "Electronics": [("Laptop", 52000), ("Headphones", 3500), ("Smartphone", 24000)],
    "Furniture": [("Office Chair", 7800), ("Standing Desk", 18500), ("Bookshelf", 6200)],
    "Office Supplies": [("Notebook Pack", 450), ("Printer Paper", 380), ("Marker Set", 260)],
    "Clothing": [("Jacket", 3200), ("Sneakers", 4100), ("T-Shirt", 799)],
}
DISCOUNTS = [0.0, 0.0, 0.05, 0.10, 0.15, 0.20]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.RandomState(42)
    dates = pd.date_range("2025-01-01", "2025-12-31", freq="D")
    rows = []
    for i in range(1, 481):
        category = str(rng.choice(list(CATALOG)))
        product, base = CATALOG[category][rng.randint(0, 3)]
        price = round(base * rng.uniform(0.95, 1.05), 2)
        qty = int(rng.randint(1, 8))
        discount = float(rng.choice(DISCOUNTS))
        revenue = round(qty * price * (1 - discount), 2)
        rows.append({
            "order_id": f"O{1000 + i}",
            "order_date": pd.Timestamp(rng.choice(dates)).strftime("%Y-%m-%d"),
            "region": str(rng.choice(REGIONS)),
            "category": category,
            "product": product,
            "quantity": qty,
            "unit_price": price,
            "discount": discount,
            "revenue": revenue,
        })
    sales = pd.DataFrame(rows).sort_values(["order_date", "order_id"])
    sales.to_csv(OUT / "sales.csv", index=False)

    reasons = ["Damaged", "Wrong item", "Changed mind"]
    returned = sales.sample(n=45, random_state=7)
    records = []
    for _, r in returned.iterrows():
        reason = str(rng.choice(reasons))
        share = 1.0 if reason != "Changed mind" else 0.9
        records.append({
            "Order ID": r["order_id"],
            "Return Date": (pd.Timestamp(r["order_date"]) + pd.Timedelta(days=int(rng.randint(2, 25)))).strftime("%Y-%m-%d"),
            "Reason": reason,
            "Refund Amount": round(float(r["revenue"]) * share, 2),
        })
    (OUT / "returns.json").write_text(json.dumps({"records": records}, indent=2), encoding="utf-8")

    targets = pd.DataFrame(
        [{"Region": reg, "Quarter": f"Q{q}", "Target": int(rng.randint(8, 16)) * 100000}
         for reg in REGIONS for q in range(1, 5)]
    )
    targets.to_excel(OUT / "targets.xlsx", index=False)
    print("Wrote", [p.name for p in sorted(OUT.iterdir())])


if __name__ == "__main__":
    main()
