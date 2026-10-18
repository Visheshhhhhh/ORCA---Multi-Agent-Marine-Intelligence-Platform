import math

# India-Sri Lanka IMBL boundary points (lat, lon)
IMBL_SRI_LANKA = [
    (8.5, 79.0),
    (9.0, 79.4),
    (9.25, 79.35),  # Near Dhanushkodi / Rameshwaram
    (9.5, 79.5),
    (9.75, 79.8),
    (10.0, 80.0),
    (10.5, 80.3)
]

# India-Pakistan boundary near Sir Creek, Gujarat
# If latitude is above 22.0, and longitude is west of 68.16 E, they approach Pakistan waters.
PAK_BORDER_LON = 68.16
PAK_BORDER_MIN_LAT = 22.0
PAK_BORDER_MAX_LAT = 24.5

# Gulf of Mannar Biosphere Reserve (Marine Protected Area where commercial fishing is restricted)
GULF_OF_MANNAR = {
    "min_lat": 8.8,
    "max_lat": 9.25,
    "min_lon": 78.1,
    "max_lon": 79.25
}

def _haversine_distance_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))

def check_boundaries(latitude: float, longitude: float) -> dict:
    """
    Checks if the given coordinate approaches or crosses international maritime boundaries
    or restricted marine protected areas.
    """
    alerts = []
    
    # 1. India - Sri Lanka IMBL Check (Palk Strait)
    # We find if the coordinate is to the East (crossed) of the boundary line
    if 8.5 <= latitude <= 10.5:
        # Interpolate the boundary longitude for the given latitude
        boundary_lon = None
        for i in range(len(IMBL_SRI_LANKA) - 1):
            lat_a, lon_a = IMBL_SRI_LANKA[i]
            lat_b, lon_b = IMBL_SRI_LANKA[i+1]
            if lat_a <= latitude <= lat_b:
                # Linear interpolation
                t = (latitude - lat_a) / (lat_b - lat_a)
                boundary_lon = lon_a + t * (lon_b - lon_a)
                break
        
        if boundary_lon is not None:
            diff_lon = longitude - boundary_lon
            # Sri Lanka is to the East (larger longitude)
            if diff_lon >= 0:
                alerts.append({
                    "zone": "India-Sri Lanka IMBL (Palk Strait)",
                    "status": "CRITICAL",
                    "message": "WARNING: You have CROSSED the International Maritime Boundary Line into Sri Lankan waters! Turn back immediately.",
                    "distance_km": 0.0
                })
            else:
                # Compute distance to the interpolated boundary point
                dist_km = _haversine_distance_km(latitude, longitude, latitude, boundary_lon)
                if dist_km <= 15.0:  # Warning if within 15 km
                    alerts.append({
                        "zone": "India-Sri Lanka IMBL (Palk Strait)",
                        "status": "WARNING",
                        "message": f"CAUTION: Approaching the Sri Lankan Maritime Boundary. You are {round(dist_km, 1)} km away. Navigate carefully.",
                        "distance_km": round(dist_km, 1)
                    })

    # 2. India - Pakistan Border Check (Sir Creek, Gujarat)
    if PAK_BORDER_MIN_LAT <= latitude <= PAK_BORDER_MAX_LAT:
        if longitude <= PAK_BORDER_LON:
            alerts.append({
                "zone": "India-Pakistan Maritime Boundary (Sir Creek)",
                "status": "CRITICAL",
                "message": "CRITICAL WARNING: You have crossed the maritime boundary into Pakistani territorial waters! Turn back immediately.",
                "distance_km": 0.0
            })
        else:
            # Distance to the boundary meridian
            dist_km = _haversine_distance_km(latitude, longitude, latitude, PAK_BORDER_LON)
            if dist_km <= 20.0:  # Warning if within 20 km
                alerts.append({
                    "zone": "India-Pakistan Maritime Boundary (Sir Creek)",
                    "status": "WARNING",
                    "message": f"CAUTION: Approaching the Pakistan Maritime Boundary. You are {round(dist_km, 1)} km away. Navigate carefully.",
                    "distance_km": round(dist_km, 1)
                })

    # 3. Gulf of Mannar Protected Area Check
    if GULF_OF_MANNAR["min_lat"] <= latitude <= GULF_OF_MANNAR["max_lat"] and \
       GULF_OF_MANNAR["min_lon"] <= longitude <= GULF_OF_MANNAR["max_lon"]:
        alerts.append({
            "zone": "Gulf of Mannar Marine National Park",
            "status": "RESTRICTED",
            "message": "RESTRICTED ZONE: You are inside the Gulf of Mannar Protected Biosphere. Commercial fishing is prohibited here.",
            "distance_km": 0.0
        })

    is_safe = True
    for alert in alerts:
        if alert["status"] in ["CRITICAL", "RESTRICTED"]:
            is_safe = False
            break

    return {
        "is_safe_waters": is_safe,
        "alerts": alerts
    }
