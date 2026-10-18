"""
Wraps two free, no-key Open-Meteo endpoints:
  - Marine Weather API (waves/swell)      https://open-meteo.com/en/docs/marine-weather-api
  - Standard Forecast API (wind speed)    https://open-meteo.com/en/docs

Wind speed is NOT available on the marine endpoint -- it lives on the
standard forecast endpoint as 'wind_speed_10m'. We fetch both since your
PFZ model needs a real wind_speed value, not a derived guess.
"""
import requests

MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT_SECONDS = 8


def get_wave_conditions(latitude: float, longitude: float, forecast_days: int = 3) -> dict:
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": "wave_height,wave_direction,wind_wave_height,swell_wave_height",
        "forecast_days": forecast_days,
    }
    resp = requests.get(MARINE_URL, params=params, timeout=TIMEOUT_SECONDS)
    resp.raise_for_status()
    data = resp.json()
    hourly = data.get("hourly", {})
    return {
        "wave_height_m": hourly.get("wave_height", [None])[0],
        "wave_direction_deg": hourly.get("wave_direction", [None])[0],
        "wind_wave_height_m": hourly.get("wind_wave_height", [None])[0],
        "swell_wave_height_m": hourly.get("swell_wave_height", [None])[0],
    }


def get_wind_speed_kmh(latitude: float, longitude: float) -> float:
    """Current wind speed at 10m, km/h (Open-Meteo default unit)."""
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "wind_speed_10m",
    }
    resp = requests.get(FORECAST_URL, params=params, timeout=TIMEOUT_SECONDS)
    resp.raise_for_status()
    data = resp.json()
    return float(data["current"]["wind_speed_10m"])


def get_marine_conditions(latitude: float, longitude: float) -> dict:
    """Combined wave + wind data for a point. Each piece fails independently."""
    result = {
        "waves": None, 
        "wind_speed_kmh": None, 
        "errors": [],
        "waves_url": f"{MARINE_URL}?latitude={latitude}&longitude={longitude}&hourly=wave_height,wave_direction,wind_wave_height,swell_wave_height&forecast_days=3",
        "wind_url": f"{FORECAST_URL}?latitude={latitude}&longitude={longitude}&current=wind_speed_10m"
    }
    try:
        result["waves"] = get_wave_conditions(latitude, longitude)
    except Exception as e:
        result["errors"].append(f"Wave fetch failed: {e}")
    try:
        result["wind_speed_kmh"] = get_wind_speed_kmh(latitude, longitude)
    except Exception as e:
        result["errors"].append(f"Wind fetch failed: {e}")
    return result
