"""Bulk-load pharmacy prices:  python -m backend.import_csv prices.csv
Columns: pharmacy_name,lat,lng,drug_id,pack_price,in_stock,address,phone,hours,delivers,delivery_base_fee,delivery_free_above,delivery_max_km
"""
import csv
import sys

from . import db
from .models import PharmacyPrice


def _f(v):
    return float(v) if v not in (None, "") else None


def main(path: str):
    db.init()
    n = 0
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            db.upsert_price(PharmacyPrice(
                pharmacy_name=row["pharmacy_name"], lat=float(row["lat"]), lng=float(row["lng"]),
                drug_id=row["drug_id"], pack_price=float(row["pack_price"]),
                in_stock=row.get("in_stock", "1") in ("1", "true", "True", "yes"),
                address=row.get("address") or None, phone=row.get("phone") or None, hours=row.get("hours") or None,
                delivers=row.get("delivers", "0") in ("1", "true", "True", "yes"),
                delivery_base_fee=_f(row.get("delivery_base_fee")) or 0.0,
                delivery_free_above=_f(row.get("delivery_free_above")),
                delivery_max_km=_f(row.get("delivery_max_km"))), source="csv-import", confidence=0.8)
            n += 1
    print(f"Imported {n} price rows")


if __name__ == "__main__":
    main(sys.argv[1])
