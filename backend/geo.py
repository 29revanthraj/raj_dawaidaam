import math


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def bounding_box(lat: float, lng: float, radius_km: float):
    dlat = radius_km / 111.0
    dlng = radius_km / (111.0 * max(math.cos(math.radians(lat)), 0.01))
    return lat - dlat, lat + dlat, lng - dlng, lng + dlng
