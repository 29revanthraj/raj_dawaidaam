from __future__ import annotations

import time
from typing import Literal, Optional

from pydantic import BaseModel, Field


class Location(BaseModel):
    lat: float
    lng: float


class SearchOptions(BaseModel):
    basket_mode: bool = False
    radius_km: float = 5.0
    travel_cost_per_km: float = 8.0   # shopper's own cost of travelling (fuel/auto/taxi)
    pincode: Optional[str] = None


class Quote(BaseModel):
    id: str
    provider: str
    kind: Literal["online", "store"]
    fulfilment: Literal["delivery", "pickup"]
    source: str                        # where the price came from
    confidence: float = 0.5            # 0..1
    price_known: bool = True
    item_price: float
    delivery_fee: float = 0.0
    platform_fee: float = 0.0
    travel_cost: float = 0.0
    discount: float = 0.0
    total: float = 0.0
    in_stock: Optional[bool] = None
    eta_minutes: Optional[int] = None
    distance_km: Optional[float] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    hours: Optional[str] = None
    url: Optional[str] = None
    delivery_rule: Optional[dict] = None
    observed_at: float = Field(default_factory=time.time)
    notes: list[str] = Field(default_factory=list)


class ConnectorResult(BaseModel):
    connector: str
    ok: bool
    cached: bool = False
    took_ms: int = 0
    error: Optional[str] = None
    quotes: list[Quote] = Field(default_factory=list)


class CrowdReport(BaseModel):
    pharmacy_name: str
    lat: float
    lng: float
    drug_id: str
    pack_price: float
    address: Optional[str] = None
    receipt_ref: Optional[str] = None


class PharmacyPrice(BaseModel):
    pharmacy_name: str
    lat: float
    lng: float
    drug_id: str
    pack_price: float
    in_stock: bool = True
    address: Optional[str] = None
    phone: Optional[str] = None
    hours: Optional[str] = None
    delivers: bool = False
    delivery_base_fee: float = 0.0
    delivery_free_above: Optional[float] = None
    delivery_max_km: Optional[float] = None
