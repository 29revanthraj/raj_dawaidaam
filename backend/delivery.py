"""Delivery / travel cost rules. Pure Python, no framework imports."""
from dataclasses import dataclass, field, fields
from typing import Optional


@dataclass
class DeliveryRule:
    base_fee: float = 0.0               # flat delivery fee
    free_above: Optional[float] = None  # free delivery when item subtotal >= this
    per_km: float = 0.0                 # added per km (hyperlocal / courier)
    max_km: Optional[float] = None      # not deliverable beyond this distance
    min_order: float = 0.0              # minimum item subtotal
    platform_fee: float = 0.0           # always charged (handling / convenience)
    eta_minutes: int = 1440             # base ETA
    eta_per_km: float = 0.0             # extra minutes per km

    @classmethod
    def from_dict(cls, d: Optional[dict]) -> "DeliveryRule":
        d = d or {}
        allowed = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in allowed})


@dataclass
class DeliveryResult:
    eligible: bool
    fee: float = 0.0
    platform_fee: float = 0.0
    eta_minutes: Optional[int] = None
    notes: list = field(default_factory=list)


def compute_delivery(rule: DeliveryRule, subtotal: float, distance_km: Optional[float] = None) -> DeliveryResult:
    d = distance_km or 0.0
    if rule.max_km is not None and distance_km is not None and distance_km > rule.max_km:
        return DeliveryResult(False, notes=[f"Beyond {rule.max_km:g} km delivery range"])
    if subtotal < rule.min_order:
        return DeliveryResult(False, notes=[f"Minimum order {rule.min_order:g}"])

    fee = rule.base_fee + rule.per_km * d
    notes = []
    if rule.free_above is not None and subtotal >= rule.free_above:
        fee = 0.0
        notes.append("Free delivery")
    elif rule.free_above is not None:
        notes.append(f"Free delivery above {rule.free_above:g}")
    eta = int(rule.eta_minutes + rule.eta_per_km * d)
    return DeliveryResult(True, round(fee, 2), round(rule.platform_fee, 2), eta, notes)


def travel_cost(distance_km: float, cost_per_km: float, round_trip: bool = True) -> float:
    """What it costs the shopper to go to a store themselves."""
    return round(distance_km * (2 if round_trip else 1) * cost_per_km, 2)
