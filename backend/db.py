"""SQLite store for pharmacy-portal prices and crowd reports. Use PostgreSQL+PostGIS in production."""
import sqlite3
import time
from contextlib import contextmanager

from .config import DB_PATH
from .geo import bounding_box, haversine_km

SCHEMA = """
CREATE TABLE IF NOT EXISTS pharmacies(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, lat REAL NOT NULL, lng REAL NOT NULL,
  address TEXT, phone TEXT, hours TEXT, delivers INTEGER DEFAULT 0,
  delivery_base_fee REAL DEFAULT 0, delivery_free_above REAL, delivery_max_km REAL,
  UNIQUE(name, lat, lng));
CREATE INDEX IF NOT EXISTS ix_ph_geo ON pharmacies(lat, lng);
CREATE TABLE IF NOT EXISTS store_prices(
  pharmacy_id INTEGER NOT NULL, drug_id TEXT NOT NULL, pack_price REAL NOT NULL,
  in_stock INTEGER DEFAULT 1, source TEXT NOT NULL, confidence REAL DEFAULT 0.7,
  observed_at REAL NOT NULL, PRIMARY KEY(pharmacy_id, drug_id));
CREATE TABLE IF NOT EXISTS crowd_reports(
  id INTEGER PRIMARY KEY, pharmacy_id INTEGER, drug_id TEXT, pack_price REAL,
  receipt_ref TEXT, status TEXT DEFAULT 'pending', created_at REAL);
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, salt TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(
  token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, expires_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS login_attempts(attempt_key TEXT NOT NULL, attempted_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS search_history(
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, drug_id TEXT NOT NULL,
  qty INTEGER NOT NULL, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS basket(
  user_id INTEGER NOT NULL, drug_id TEXT NOT NULL, qty INTEGER NOT NULL,
  PRIMARY KEY(user_id, drug_id));
CREATE TABLE IF NOT EXISTS home_addresses(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
  label TEXT NOT NULL, recipient TEXT NOT NULL, line1 TEXT NOT NULL, line2 TEXT NOT NULL,
  city TEXT NOT NULL, state TEXT NOT NULL, pincode TEXT NOT NULL,
  lat REAL, lng REAL);
CREATE INDEX IF NOT EXISTS ix_address_user ON home_addresses(user_id);
"""


@contextmanager
def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init():
    with conn() as c:
        c.executescript(SCHEMA)
        # Upgrade the initial address table without losing saved addresses.
        columns = c.execute("PRAGMA table_info(home_addresses)").fetchall()
        if any(row["name"] in {"lat", "lng"} and row["notnull"] for row in columns):
            c.execute("ALTER TABLE home_addresses RENAME TO home_addresses_required_coords")
            c.execute("DROP INDEX IF EXISTS ix_address_user")
            c.executescript(SCHEMA)
            c.execute("INSERT INTO home_addresses SELECT * FROM home_addresses_required_coords")
            c.execute("DROP TABLE home_addresses_required_coords")


def _upsert_pharmacy(c, p: dict) -> int:
    c.execute(
        """INSERT INTO pharmacies(name,lat,lng,address,phone,hours,delivers,delivery_base_fee,delivery_free_above,delivery_max_km)
           VALUES(:name,:lat,:lng,:address,:phone,:hours,:delivers,:base,:free,:maxkm)
           ON CONFLICT(name,lat,lng) DO UPDATE SET address=excluded.address, phone=excluded.phone,
             hours=excluded.hours, delivers=excluded.delivers, delivery_base_fee=excluded.delivery_base_fee,
             delivery_free_above=excluded.delivery_free_above, delivery_max_km=excluded.delivery_max_km""",
        p,
    )
    return c.execute("SELECT id FROM pharmacies WHERE name=? AND lat=? AND lng=?",
                     (p["name"], p["lat"], p["lng"])).fetchone()["id"]


def upsert_price(item, source: str, confidence: float):
    with conn() as c:
        pid = _upsert_pharmacy(c, dict(
            name=item.pharmacy_name, lat=item.lat, lng=item.lng, address=item.address, phone=item.phone,
            hours=item.hours, delivers=int(item.delivers), base=item.delivery_base_fee,
            free=item.delivery_free_above, maxkm=item.delivery_max_km))
        c.execute(
            """INSERT INTO store_prices(pharmacy_id,drug_id,pack_price,in_stock,source,confidence,observed_at)
               VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(pharmacy_id,drug_id) DO UPDATE SET pack_price=excluded.pack_price,
                 in_stock=excluded.in_stock, source=excluded.source, confidence=excluded.confidence,
                 observed_at=excluded.observed_at""",
            (pid, item.drug_id, item.pack_price, int(item.in_stock), source, confidence, time.time()))


def add_report(r) -> None:
    with conn() as c:
        pid = _upsert_pharmacy(c, dict(name=r.pharmacy_name, lat=r.lat, lng=r.lng, address=r.address,
                                       phone=None, hours=None, delivers=0, base=0, free=None, maxkm=None))
        c.execute("INSERT INTO crowd_reports(pharmacy_id,drug_id,pack_price,receipt_ref,created_at) VALUES(?,?,?,?,?)",
                  (pid, r.drug_id, r.pack_price, r.receipt_ref, time.time()))


def nearby_prices(drug_id: str, lat: float, lng: float, radius_km: float) -> list:
    la1, la2, lo1, lo2 = bounding_box(lat, lng, radius_km)
    with conn() as c:
        rows = c.execute(
            """SELECT p.*, sp.pack_price, sp.in_stock, sp.source, sp.confidence, sp.observed_at
               FROM store_prices sp JOIN pharmacies p ON p.id = sp.pharmacy_id
               WHERE sp.drug_id=? AND p.lat BETWEEN ? AND ? AND p.lng BETWEEN ? AND ?""",
            (drug_id, la1, la2, lo1, lo2)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["straight_km"] = haversine_km(lat, lng, d["lat"], d["lng"])
        if d["straight_km"] <= radius_km:
            out.append(d)
    return out
