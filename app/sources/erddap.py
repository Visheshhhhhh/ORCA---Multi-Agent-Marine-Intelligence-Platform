"""
Fetches near-real-time satellite SST and chlorophyll-a from NOAA CoastWatch ERDDAP.
Free, no API key, no login required.

Datasets used:
  - SST: jplMURSST41 (global, ~1km, daily) - variable 'analysed_sst', Kelvin
  - Chlorophyll: noaacwNPPVIIRSchlaDaily (VIIRS, global 4km, daily) - variable 'chlor_a', mg/m^3

ERDDAP griddap snaps a requested (time, lat, lon) to the nearest available
grid point automatically, so we don't need to know exact grid coordinates.

NOTE: this code was written against ERDDAP's documented griddap query syntax
and has NOT been tested against a live network call (this environment's
sandbox can't reach coastwatch.noaa.gov). Run the two curl commands in
README.md to sanity-check before relying on this in a demo.
"""
import csv
import io
import math
import requests
from datetime import datetime, timezone

SST_BASE = "https://coastwatch.pfeg.noaa.gov/erddap/griddap/jplMURSST41.csv"
CHLA_BASE = "https://coastwatch.noaa.gov/erddap/griddap/noaacwNPPVIIRSchlaDaily.csv"

TIMEOUT_SECONDS = 8


def _fetch_griddap_point(base_url: str, variable: str, latitude: float, longitude: float, use_last_time: bool = True) -> float | None:
    """
    Query a single grid point from an ERDDAP griddap dataset.
    ERDDAP CSV responses have 2 header rows (names, units) then data rows.
    """
    time_selector = "(last)" if use_last_time else f"({datetime.now(timezone.utc).strftime('%Y-%m-%dT00:00:00Z')})"
    
    # chlor_a contains 4 dimensions: [time][altitude][latitude][longitude]
    if variable == "chlor_a":
        query = f"{variable}[{time_selector}][(0.0)][({latitude})][({longitude})]"
    else:
        query = f"{variable}[{time_selector}][({latitude})][({longitude})]"
        
    url = f"{base_url}?{query}"

    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(url, headers=headers, timeout=TIMEOUT_SECONDS)
    resp.raise_for_status()

    reader = csv.reader(io.StringIO(resp.text))
    rows = list(reader)
    if len(rows) < 3:
        raise ValueError(f"Unexpected ERDDAP response (too few rows): {resp.text[:300]}")

    header = rows[0]
    data_row = rows[2]  # row 0 = names, row 1 = units, row 2+ = data
    value_index = header.index(variable)
    
    val_str = data_row[value_index]
    if val_str.lower() == "nan" or not val_str:
        return None
        
    val = float(val_str)
    if math.isnan(val):
        return None
        
    return val


def get_sst_celsius(latitude: float, longitude: float) -> float | None:
    """Sea surface temperature in Celsius (jplMURSST41 returns Celsius per its metadata)."""
    return _fetch_griddap_point(SST_BASE, "analysed_sst", latitude, longitude)


def get_chlorophyll_mg_m3(latitude: float, longitude: float) -> float | None:
    """Chlorophyll-a concentration in mg/m^3."""
    return _fetch_griddap_point(CHLA_BASE, "chlor_a", latitude, longitude)


def get_ocean_conditions(latitude: float, longitude: float) -> dict:
    """
    Convenience wrapper: fetches both SST and chlorophyll for a point.
    Each is fetched independently so a failure in one doesn't block the other.
    """
    result = {
        "sst": None, 
        "chlorophyll": None, 
        "errors": [],
        "sst_url": f"{SST_BASE}?analysed_sst[(last)][({latitude})][({longitude})]",
        "chlorophyll_url": f"{CHLA_BASE}?chlor_a[(last)][(0.0)][({latitude})][({longitude})]"
    }

    try:
        result["sst"] = get_sst_celsius(latitude, longitude)
    except Exception as e:
        result["errors"].append(f"SST fetch failed: {e}")

    try:
        result["chlorophyll"] = get_chlorophyll_mg_m3(latitude, longitude)
    except Exception as e:
        result["errors"].append(f"Chlorophyll fetch failed: {e}")

    return result
