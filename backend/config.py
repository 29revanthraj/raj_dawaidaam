import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
FRONTEND_DIR = BASE_DIR / "frontend"


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


CURRENCY = os.getenv("CURRENCY", "INR")
CACHE_TTL = int(os.getenv("CACHE_TTL_SECONDS", "300"))
CONNECTOR_TIMEOUT = float(os.getenv("CONNECTOR_TIMEOUT", "8"))
USER_AGENT = os.getenv("USER_AGENT", "DawaiDaamBot/0.1 (+mailto:you@example.com)")
ENABLE_DEMO = _bool("ENABLE_DEMO", True)
ENABLE_OSM = _bool("ENABLE_OSM", True)
ROAD_FACTOR = float(os.getenv("ROAD_FACTOR", "1.3"))
PHARMACY_API_KEY = os.getenv("PHARMACY_API_KEY", "")
DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "rx.db"))
STALE_AFTER_HOURS = int(os.getenv("STALE_AFTER_HOURS", "168"))  # 7 days
