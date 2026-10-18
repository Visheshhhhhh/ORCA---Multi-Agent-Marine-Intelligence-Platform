"""
Fetches active tropical cyclone alerts from GDACS (Global Disaster Alert and
Coordination System) and filters to the Arabian Sea / Bay of Bengal region,
then further to a radius around the query point.

GDACS is global -- without the bounding-box filter you'd surface cyclones
near Japan or the Caribbean as "active alerts" for a fisherman off Kochi.
"""
import math
import requests

CYCLONE_GEOJSON_URL = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"
TIMEOUT_SECONDS = 8

# Rough bounding box covering the Arabian Sea + Bay of Bengal + Indian Ocean approach.
INDIAN_OCEAN_BBOX = {"min_lat": -10.0, "max_lat": 30.0, "min_lon": 40.0, "max_lon": 100.0}

# How close (km) a cyclone needs to be to the query point to be flagged as relevant.
RELEVANCE_RADIUS_KM = 500


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _in_bbox(lat: float, lon: float) -> bool:
    b = INDIAN_OCEAN_BBOX
    return b["min_lat"] <= lat <= b["max_lat"] and b["min_lon"] <= lon <= b["max_lon"]


def _first_present(d: dict, keys: list):
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None


def get_nearby_cyclone_alerts(latitude: float, longitude: float) -> dict:
    """
    Returns active cyclones in the Indian Ocean region, flagged with distance
    from the query point. Cyclones outside the region are dropped entirely;
    ones inside it but far from the query point are still returned (so the
    caller/LLM can mention "no immediate threat, but X is active in the Bay
    of Bengal") with an `is_relevant` flag for anything within RELEVANCE_RADIUS_KM.
    """
    result = {"cyclones": [], "errors": []}
    try:
        resp = requests.get(CYCLONE_GEOJSON_URL, timeout=TIMEOUT_SECONDS)
        resp.raise_for_status()
        geojson = resp.json()
    except Exception as e:
        result["errors"].append(f"GDACS fetch failed: {e}")
        return result

    for feature in geojson.get("features", []):
        geom = feature.get("geometry", {})
        props = feature.get("properties", {})
        
        # Only keep tropical cyclones that are currently active
        if props.get("eventtype") != "TC":
            continue
        if str(props.get("iscurrent", "")).lower() != "true":
            continue

        coords = geom.get("coordinates")
        if not coords or geom.get("type") != "Point":
            continue  # skip track lines/polygons, keep it simple: point events only
        lon, lat = coords[0], coords[1]
        if not _in_bbox(lat, lon):
            continue

        distance_km = _haversine_km(latitude, longitude, lat, lon)
        result["cyclones"].append({
            "name": _first_present(props, ["name", "eventname", "title"]),
            "severity": _first_present(props, ["alertlevel", "alertLevel", "severitydata", "severity"]),
            "latitude": lat,
            "longitude": lon,
            "distance_km": round(distance_km, 1),
            "is_relevant": distance_km <= RELEVANCE_RADIUS_KM,
            "raw_properties": props,
        })

    return result
