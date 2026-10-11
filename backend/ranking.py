from .models import Quote


def finalize(q: Quote) -> Quote:
    q.total = round(q.item_price + q.delivery_fee + q.platform_fee + q.travel_cost - q.discount, 2)
    return q


def sort_quotes(quotes: list, mode: str = "total") -> list:
    big = 10 ** 9
    if mode == "fastest":
        key = lambda q: (not q.price_known, q.eta_minutes if q.eta_minutes is not None else big, q.total)
    elif mode == "nearest":
        key = lambda q: (not q.price_known, q.distance_km if q.distance_km is not None else big, q.total)
    else:  # lowest all-in cost
        key = lambda q: (not q.price_known, q.in_stock is False, q.total)
    return sorted(quotes, key=key)
