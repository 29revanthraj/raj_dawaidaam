import json
import time
from typing import Optional
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import accounts, addresses, catalogue, config, db, medicine_info
from .aggregator import build_connectors, stream_results
from .basket_compare import compare_basket
from .models import CrowdReport, Location, PharmacyPrice, SearchOptions
from .normalize import search_catalogue
from .ranking import sort_quotes

app = FastAPI(title="DawaiDaam", version="0.1.0")
app.include_router(addresses.router)
CONNECTORS = build_connectors()
db.init()


@app.middleware("http")
async def protect_account_requests(request: Request, call_next):
    if request.method in {"POST", "PUT", "DELETE", "PATCH"} and request.url.path.startswith(("/api/auth", "/api/history", "/api/basket", "/api/addresses")):
        origin = request.headers.get("origin")
        if origin and (urlsplit(origin).scheme, urlsplit(origin).netloc) != (request.url.scheme, request.url.netloc):
            return JSONResponse({"detail": "Cross-origin request rejected"}, status_code=403)
    response = await call_next(request)
    if request.url.path.startswith(("/api/auth", "/api/history", "/api/basket", "/api/addresses")):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.post("/api/auth/register", status_code=201)
def register(credentials: accounts.Credentials, request: Request, response: Response):
    return accounts.register(credentials, request, response)


@app.post("/api/auth/login")
def login(credentials: accounts.Credentials, request: Request, response: Response):
    return accounts.login(credentials, request, response)


@app.post("/api/auth/logout")
def logout(request: Request, response: Response):
    return accounts.logout(request, response)


@app.get("/api/auth/me")
def me(user=Depends(accounts.current_user)):
    return user


class SavedMedicine(BaseModel):
    drug_id: str = Field(min_length=1, max_length=100)
    qty: int = Field(ge=1, le=1000)


@app.post("/api/history", status_code=201)
def save_history(item: SavedMedicine, user=Depends(accounts.current_user)):
    _drug_or_404(item.drug_id)
    with db.conn() as c:
        c.execute("INSERT INTO search_history(user_id,drug_id,qty,created_at) VALUES(?,?,?,?)",
                  (user["id"], item.drug_id, item.qty, time.time()))
        c.execute("DELETE FROM search_history WHERE user_id=? AND id NOT IN "
                  "(SELECT id FROM search_history WHERE user_id=? ORDER BY id DESC LIMIT 100)",
                  (user["id"], user["id"]))
    return {"ok": True}


@app.get("/api/history")
def history(user=Depends(accounts.current_user)):
    with db.conn() as c:
        rows = c.execute("SELECT id,drug_id,qty,created_at FROM search_history WHERE user_id=? ORDER BY id DESC",
                         (user["id"],)).fetchall()
    return [{**dict(row), "drug": catalogue.get_drug(row["drug_id"])} for row in rows]


@app.delete("/api/history")
def clear_history(user=Depends(accounts.current_user)):
    with db.conn() as c:
        c.execute("DELETE FROM search_history WHERE user_id=?", (user["id"],))
    return {"ok": True}


@app.get("/api/basket")
def basket(user=Depends(accounts.current_user)):
    with db.conn() as c:
        rows = c.execute("SELECT drug_id,qty FROM basket WHERE user_id=? ORDER BY drug_id", (user["id"],)).fetchall()
    return [{**dict(row), "drug": catalogue.get_drug(row["drug_id"]),
             "online_searches": medicine_info.online_searches(_drug_or_404(row["drug_id"]))} for row in rows]


@app.put("/api/basket")
def save_basket(item: SavedMedicine, user=Depends(accounts.current_user)):
    _drug_or_404(item.drug_id)
    with db.conn() as c:
        c.execute("INSERT INTO basket(user_id,drug_id,qty) VALUES(?,?,?) "
                  "ON CONFLICT(user_id,drug_id) DO UPDATE SET qty=excluded.qty",
                  (user["id"], item.drug_id, item.qty))
    return {"ok": True}


@app.get("/api/basket/compare")
async def basket_prices(lat: Optional[float] = Query(None, ge=-90, le=90), lng: Optional[float] = Query(None, ge=-180, le=180),
                        radius_km: float = Query(5, gt=0, le=25),
                        travel_cost_per_km: float = Query(0, ge=0, le=500),
                        pincode: Optional[str] = Query(None, max_length=20),
                        address_id: Optional[int] = Query(None, ge=1),
                        user=Depends(accounts.current_user)):
    selected_address = addresses.get_address(address_id, user["id"]) if address_id is not None else None
    if selected_address:
        pincode = selected_address["pincode"]
        if selected_address["lat"] is not None and selected_address["lng"] is not None:
            lat, lng = selected_address["lat"], selected_address["lng"]
    if (lat is None) != (lng is None):
        raise HTTPException(422, "Provide both coordinates or leave both empty")
    if lat is None and not selected_address:
        raise HTTPException(422, "Select a saved address or provide latitude and longitude")
    loc = Location(lat=lat, lng=lng) if lat is not None else None
    with db.conn() as c:
        rows = c.execute("SELECT drug_id,qty FROM basket WHERE user_id=? ORDER BY drug_id", (user["id"],)).fetchall()
    items = [{"drug": _drug_or_404(row["drug_id"]), "qty": row["qty"]} for row in rows]
    result = await compare_basket(CONNECTORS, items, loc,
                                  SearchOptions(radius_km=radius_km, travel_cost_per_km=travel_cost_per_km,
                                                pincode=pincode)) if items else {"offers": [], "sources": [], "skipped_sources": []}
    return {**result, "currency": config.CURRENCY, "item_count": len(items),
            "selected_address": selected_address, "location": {"lat": lat, "lng": lng, "pincode": pincode}}


@app.delete("/api/basket/{drug_id}")
def remove_basket(drug_id: str, user=Depends(accounts.current_user)):
    with db.conn() as c:
        c.execute("DELETE FROM basket WHERE user_id=? AND drug_id=?", (user["id"], drug_id))
    return {"ok": True}


def _drug_or_404(drug_id: str) -> dict:
    d = catalogue.get_drug(drug_id)
    if not d:
        raise HTTPException(404, "Unknown drug")
    return d


@app.get("/api/health")
def health():
    return {"ok": True, "connectors": [c.id for c in CONNECTORS], "currency": config.CURRENCY}


@app.get("/api/drugs/search")
def drug_search(q: str = Query(..., min_length=1)):
    return [{"id": d["id"], "name": d["name"], "strength": d["strength"], "form": d["form"],
             "pack_size": d["pack_size"], "unit": d["unit"], "pack_volume_ml": d.get("pack_volume_ml"), "rx_required": d["rx_required"]}
            for d in search_catalogue(q, catalogue.all_drugs())]


@app.get("/api/drugs")
def drug_catalogue(liquids_only: bool = False):
    return [{"id": d["id"], "name": d["name"], "pack_size": d["pack_size"],
             "unit": d["unit"], "pack_volume_ml": d.get("pack_volume_ml"), "rx_required": d["rx_required"]}
            for d in catalogue.all_drugs() if not liquids_only or d["unit"] == "bottle"]


@app.get("/api/drugs/{drug_id}")
def drug_detail(drug_id: str):
    d = _drug_or_404(drug_id)
    return {**d, "alternatives": catalogue.alternatives(d), "medicine_info": medicine_info.details(d),
            "online_searches": medicine_info.online_searches(d)}


@app.get("/api/prices")
async def prices(drug_id: str, qty: int = Query(10, ge=1, le=1000), lat: float = Query(..., ge=-90, le=90),
                 lng: float = Query(..., ge=-180, le=180), radius_km: float = Query(5, gt=0, le=25),
                 travel_cost_per_km: float = Query(8, ge=0, le=500), pincode: Optional[str] = None,
                 sort: str = "total"):
    """One-shot: waits for all sources, returns a ranked list."""
    drug, loc = _drug_or_404(drug_id), Location(lat=lat, lng=lng)
    opts = SearchOptions(radius_km=radius_km, travel_cost_per_km=travel_cost_per_km, pincode=pincode)
    quotes, status = [], []
    async for res in stream_results(CONNECTORS, drug, qty, loc, opts):
        quotes += res.quotes
        status.append({"connector": res.connector, "ok": res.ok, "cached": res.cached,
                       "took_ms": res.took_ms, "error": res.error, "count": len(res.quotes)})
    return {"drug": drug["name"], "qty": qty, "currency": config.CURRENCY,
            "quotes": [q.model_dump() for q in sort_quotes(quotes, sort)], "sources": status}


@app.get("/api/prices/stream")
async def prices_stream(drug_id: str, qty: int = Query(10, ge=1, le=1000), lat: float = Query(..., ge=-90, le=90),
                        lng: float = Query(..., ge=-180, le=180), radius_km: float = Query(5, gt=0, le=25),
                        travel_cost_per_km: float = Query(8, ge=0, le=500), pincode: Optional[str] = None):
    """Server-Sent Events: each source's results are pushed the moment it responds."""
    drug, loc = _drug_or_404(drug_id), Location(lat=lat, lng=lng)
    opts = SearchOptions(radius_km=radius_km, travel_cost_per_km=travel_cost_per_km, pincode=pincode)

    async def gen():
        yield f"event: meta\ndata: {json.dumps({'total_sources': len(CONNECTORS), 'currency': config.CURRENCY})}\n\n"
        async for res in stream_results(CONNECTORS, drug, qty, loc, opts):
            yield f"event: result\ndata: {res.model_dump_json()}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/reports", status_code=202)
def crowd_report(r: CrowdReport):
    _drug_or_404(r.drug_id)
    db.add_report(r)   # stored as 'pending'; moderate before it affects prices
    return {"status": "pending_review"}


@app.post("/api/pharmacy/prices")
def pharmacy_price(p: PharmacyPrice, x_api_key: str = Header(default="")):
    if not config.PHARMACY_API_KEY or x_api_key != config.PHARMACY_API_KEY:
        raise HTTPException(401, "Invalid API key")
    _drug_or_404(p.drug_id)
    db.upsert_price(p, source="pharmacy-portal", confidence=0.85)
    return {"status": "ok"}


app.mount("/", StaticFiles(directory=config.FRONTEND_DIR, html=True), name="web")
