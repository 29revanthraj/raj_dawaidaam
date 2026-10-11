"""Drug-name normalisation and fuzzy search over the canonical catalogue (list of dicts)."""
import math
import re
from difflib import SequenceMatcher


def compact(s: str) -> str:
    return re.sub(r"[^a-z0-9.]", "", s.lower())


def tokens(s: str) -> list:
    return re.findall(r"[a-z0-9.]+", s.lower())


def packs_needed(qty: int, pack_size: int) -> int:
    return max(1, math.ceil(max(qty, 1) / max(pack_size, 1)))


def parse_pack_size(title: str, unit: str = "tablet"):
    if unit == "bottle":
        m = re.search(r"(?:pack of\s*)?(\d+)\s*bottles?\b", title, re.I)
        return int(m.group(1)) if m else 1
    m = re.search(r"(\d{1,3})\s*(?:tablets?|tabs?|capsules?|caps?)\b", title, re.I)
    if m:
        return int(m.group(1))
    m = re.search(r"strip of (\d{1,3})", title, re.I)
    return int(m.group(1)) if m else None


def title_matches(drug: dict, title: str) -> bool:
    """Strict: strength must appear AND ingredient/alias/brand must appear."""
    t = compact(title)
    if compact(drug["strength"]) not in t:
        return False
    if drug.get("unit") == "bottle":
        if not re.search(r"syrup|suspension|solution|oral liquid", title, re.I):
            return False
        volume = drug.get("pack_volume_ml")
        if volume and not re.search(rf"\b{volume}\s*ml\b", title, re.I):
            return False
    elif re.search(r"syrup|suspension|solution|oral liquid", title, re.I):
        return False
    names = [drug["ingredient"], drug["name"], *drug.get("aliases", []),
             *[b["name"] for b in drug.get("brands", [])]]
    return any(compact(n.split()[0]) in t for n in names if n)


def score(query: str, drug: dict) -> float:
    q = query.lower().strip()
    names = [drug["name"], drug["ingredient"], *drug.get("aliases", []),
             *[b["name"] for b in drug.get("brands", [])]]
    best = 0.0
    for n in names:
        n = n.lower()
        if n.startswith(q):
            best = max(best, 1.0)
        elif q in n:
            best = max(best, 0.9)
        else:
            best = max(best, SequenceMatcher(None, q, n[: len(q) + 3]).ratio() * 0.85)
    for tok in tokens(q):
        if tok.isdigit() and tok in drug["strength"]:
            best += 0.1
    return best


def search_catalogue(query: str, catalogue: list, limit: int = 50) -> list:
    if not query.strip():
        return []
    scored = [(score(query, d), d) for d in catalogue]
    return [d for s, d in sorted(scored, key=lambda x: -x[0]) if s >= 0.55][:limit]
