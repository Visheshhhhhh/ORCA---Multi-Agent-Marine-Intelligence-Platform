"""
ORCA backend -- deterministic orchestrator.

Design: this is intentionally NOT an "agentic" router where an LLM decides
which tools to call. For a location query we always fetch PFZ + ocean +
marine + cyclone data in parallel (all four are fast/cheap), assemble it
into structured JSON, then make exactly ONE call to the local LLM to
synthesize a natural-language advisory. See chat history for the reasoning.

Run with: uvicorn app.main:app --reload --port 8000
"""
import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.model import predict_pfz_score
from app.sources import erddap, gdacs
from app.sources import openmeteo
from app.agents import SupervisorAgent

app = FastAPI(title="ORCA - Marine Intelligence Platform", version="0.1.0")
supervisor = SupervisorAgent()


class LocationQuery(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    question: str | None = None  # optional free-text question for the LLM to address
    session_id: str | None = None  # optional session ID for multi-turn conversations
    language: str | None = None  # manual language selection


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/pfz")
async def pfz_endpoint(query: LocationQuery):
    """Fetches live ocean conditions and returns the model's PFZ probability."""
    ocean = await asyncio.to_thread(erddap.get_ocean_conditions, query.latitude, query.longitude)
    marine = await asyncio.to_thread(openmeteo.get_marine_conditions, query.latitude, query.longitude)

    if ocean["sst"] is None or ocean["chlorophyll"] is None or marine["wind_speed_kmh"] is None:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "One or more upstream data sources failed; cannot compute a real PFZ score.",
                "ocean_errors": ocean["errors"],
                "marine_errors": marine["errors"],
            },
        )

    score = predict_pfz_score(
        latitude=query.latitude,
        longitude=query.longitude,
        sst=ocean["sst"],
        chlorophyll=ocean["chlorophyll"],
        wind_speed=marine["wind_speed_kmh"],
    )
    return {
        "pfz_probability": score,
        "sst_celsius": ocean["sst"],
        "chlorophyll_mg_per_m3": ocean["chlorophyll"],
        "wind_speed_kmh": marine["wind_speed_kmh"],
    }


@app.post("/weather")
async def weather_endpoint(query: LocationQuery):
    marine = await asyncio.to_thread(openmeteo.get_marine_conditions, query.latitude, query.longitude)
    return marine


@app.post("/alerts")
async def alerts_endpoint(query: LocationQuery):
    cyclones = await asyncio.to_thread(gdacs.get_nearby_cyclone_alerts, query.latitude, query.longitude)
    return cyclones


@app.post("/advisory")
async def advisory_endpoint(query: LocationQuery):
    """
    Orchestrates the collaborative multi-agent reasoning flow.
    Runs data retrieval, safety, geofencing, routing, and synthesis.
    """
    try:
        response = await asyncio.to_thread(
            supervisor.process_query,
            latitude=query.latitude,
            longitude=query.longitude,
            query=query.question,
            session_id=query.session_id,
            language=query.language
        )
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Serve frontend single-page application at the root
app.mount("/", StaticFiles(directory=".", html=True), name="static")
