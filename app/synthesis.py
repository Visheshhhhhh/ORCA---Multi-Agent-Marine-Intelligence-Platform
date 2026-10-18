"""
Calls a local Ollama instance (Llama 3.2) to turn structured advisory data
into a plain-language recommendation. This is a SINGLE call per request --
the model does not decide what data to fetch (that's done deterministically
in main.py before this is ever called). See the chat discussion for why:
small local models are unreliable at multi-step tool-calling, so we keep
them to the one job they're good at -- explaining numbers in plain language.
"""
import requests
import json

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "llama3.2"
TIMEOUT_SECONDS = 30

SYSTEM_PROMPT = """You are ORCA, a marine advisory assistant for fishermen and researchers \
along the Indian coast. You are given structured data: a PFZ (Potential Fishing Zone) \
probability score from a trained model, live sea surface temperature, chlorophyll \
concentration, wind speed, wave conditions, and any active cyclone alerts for a location.

Explain this data in plain, conversational language a fisherman without a technical \
background can act on. Be direct and practical:
- State whether this looks like a good fishing zone and why, referencing the actual numbers.
- Flag any safety concerns (high waves, strong wind, nearby cyclone) clearly and first if severe.
- Keep it to 3-5 sentences. No headers, no bullet lists, no markdown -- this is spoken advice.
- Never invent numbers that weren't given to you. If something is missing (None), say it's unavailable, don't guess.
"""


def generate_advisory(location: dict, pfz_score: float, ocean: dict, marine: dict, cyclones: dict, user_question: str | None = None) -> str:
    """
    location: {"latitude": .., "longitude": ..}
    pfz_score: float 0-1 from the XGBoost model
    ocean: {"sst": .., "chlorophyll": .., "errors": [...]}
    marine: {"waves": {...}, "wind_speed_kmh": .., "errors": [...]}
    cyclones: {"cyclones": [...], "errors": [...]}
    """
    data_summary = {
        "location": location,
        "pfz_probability": round(pfz_score, 3),
        "sea_surface_temp_celsius": ocean.get("sst"),
        "chlorophyll_mg_per_m3": ocean.get("chlorophyll"),
        "wind_speed_kmh": marine.get("wind_speed_kmh"),
        "waves": marine.get("waves"),
        "active_nearby_cyclones": [c for c in cyclones.get("cyclones", []) if c.get("is_relevant")],
    }

    prompt = f"Data:\n{json.dumps(data_summary, indent=2)}\n\n"
    if user_question:
        prompt += f"User's question: {user_question}\n\n"
    prompt += "Give the advisory now."

    payload = {
        "model": MODEL_NAME,
        "system": SYSTEM_PROMPT,
        "prompt": prompt,
        "stream": False,
    }

    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=TIMEOUT_SECONDS)
        resp.raise_for_status()
        return resp.json()["response"].strip()
    except Exception as e:
        # Fall back to a deterministic, non-LLM summary so the endpoint never
        # hard-fails just because Ollama isn't running / model isn't pulled.
        return (
            f"[LLM synthesis unavailable: {e}] "
            f"PFZ probability: {data_summary['pfz_probability']}, "
            f"SST: {data_summary['sea_surface_temp_celsius']}°C, "
            f"Chlorophyll: {data_summary['chlorophyll_mg_per_m3']} mg/m³, "
            f"Wind: {data_summary['wind_speed_kmh']} km/h."
        )
