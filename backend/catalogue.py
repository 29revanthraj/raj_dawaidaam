import json

from .config import DATA_DIR

_DRUGS = json.loads((DATA_DIR / "drugs.json").read_text())
_BY_ID = {d["id"]: d for d in _DRUGS}


def all_drugs() -> list:
    return _DRUGS


def get_drug(drug_id: str):
    return _BY_ID.get(drug_id)


def alternatives(drug: dict) -> dict:
    same = [b for b in drug["brands"]]
    same.sort(key=lambda b: b["pack_price"])
    other_strengths = [
        {"id": d["id"], "name": d["name"]}
        for d in _DRUGS
        if d["ingredient"] == drug["ingredient"] and d["id"] != drug["id"]
    ]
    return {
        "same_ingredient_and_strength": same,
        "other_strengths": other_strengths,
        "notice": "Ask your doctor or pharmacist before switching brands or strengths.",
    }
