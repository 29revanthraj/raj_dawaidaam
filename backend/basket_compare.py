"""Compare one whole basket at each source/location, never summing per-item shipping."""
import asyncio

from .aggregator import run_connector
from .delivery import DeliveryRule, compute_delivery, travel_cost


async def compare_basket(connectors, items, loc, opts):
    opts = opts.model_copy(update={"basket_mode": True})
    # Limit concurrent network work for large baskets.
    semaphore = asyncio.Semaphore(8)

    async def fetch(connector, item):
        async with semaphore:
            result = await run_connector(connector, item["drug"], item["qty"], loc, opts)
            return connector, item, result

    skipped = [c for c in connectors if loc is None and getattr(c, "requires_coordinates", True)]
    results = await asyncio.gather(*(fetch(c, item) for c in connectors if c not in skipped for item in items))
    groups, sources = {}, []
    for connector, item, result in results:
        sources.append({"connector": connector.id, "drug_id": item["drug"]["id"], "ok": result.ok,
                        "cached": result.cached, "error": result.error})
        for quote in result.quotes:
            # Quote IDs encode physical branch and fulfilment; connector prevents source collisions.
            key = (connector.id, quote.id)
            group = groups.setdefault(key, {"quote": quote, "items": {}})
            group["items"][item["drug"]["id"]] = quote

    offers = []
    for (connector_id, quote_id), group in groups.items():
        q, quotes = group["quote"], group["items"]
        lines = []
        for item in items:
            drug = item["drug"]
            quote = quotes.get(drug["id"])
            status = ("missing" if quote is None else "out_of_stock" if quote.in_stock is False
                      else "unconfirmed" if quote.in_stock is None or not quote.price_known
                      or "Price may be stale" in quote.notes else "available")
            lines.append({"drug_id": drug["id"], "name": drug["name"], "qty": item["qty"],
                          "unit": drug["unit"],
                          "status": status, "item_price": quote.item_price if quote and quote.price_known else None,
                          "url": quote.url if quote else None,
                          "observed_at": quote.observed_at if quote else None})
        complete = all(line["status"] == "available" for line in lines)
        demo = any(quote.source == "demo" for quote in quotes.values())
        subtotal = round(sum(line["item_price"] or 0 for line in lines), 2)
        delivery_fee, platform_fee, travel, eta, total = None, None, None, None, None
        notes = []
        eligible = complete
        if complete:
            travel = travel_cost(q.distance_km or 0, opts.travel_cost_per_km) if q.fulfilment == "pickup" else 0
            delivery_fee, platform_fee = 0, 0
            if q.fulfilment == "delivery":
                if not q.delivery_rule:
                    eligible = False
                    notes.append("Basket delivery charge unavailable; confirm with provider")
                else:
                    delivery = compute_delivery(DeliveryRule.from_dict(q.delivery_rule), subtotal, q.distance_km)
                    eligible = delivery.eligible
                    notes += delivery.notes
                    delivery_fee, platform_fee, eta = delivery.fee, delivery.platform_fee, delivery.eta_minutes
                    notes.append("Delivery charge and ETA estimated from configured rules; not a live checkout quote")
            if eligible:
                total = round(subtotal + delivery_fee + platform_fee + travel, 2)
        if demo:
            notes.append("Synthetic demo prices and availability; not a real offer")
        offers.append({"id": f"{connector_id}:{quote_id}", "provider": q.provider, "kind": q.kind,
                       "fulfilment": q.fulfilment, "source": q.source, "demo": demo,
                       "complete": complete, "confirmed": complete and not demo, "eligible": eligible,
                       "items": lines, "subtotal": subtotal if complete else None,
                       "delivery_fee": delivery_fee, "platform_fee": platform_fee, "travel_cost": travel,
                       "total": total, "eta_minutes": eta, "distance_km": q.distance_km,
                       "lat": q.lat, "lng": q.lng, "address": q.address, "phone": q.phone,
                       "hours": q.hours, "notes": notes})
    offers.sort(key=lambda offer: (offer["total"] is None, offer["demo"], offer["total"] or 0, offer["provider"]))
    return {"offers": offers, "sources": sources,
            "skipped_sources": [{"connector": c.id, "reason": "Coordinates needed for nearby stores or location-dependent delivery"} for c in skipped]}