# ORCA Backend

Deterministic orchestrator: fetches PFZ (your XGBoost model) + live ocean data (ERDDAP)
+ marine weather (Open-Meteo) + cyclone alerts (GDACS) in parallel, then makes ONE call
to a local Llama 3.2 (via Ollama) to produce a plain-language advisory.

## What's confirmed working (tested in this environment)
- ✅ `pfz_xgboost_model.json` loads and predicts correctly (`app/model.py`)
- ✅ FastAPI app wires together, all routes registered
- ⚠️ ERDDAP, Open-Meteo, and GDACS calls are written against documented API syntax
  but NOT tested live -- this sandbox can't reach those domains. Verify with the
  curl commands below before your demo.

## Setup

```bash
pip install fastapi uvicorn requests xgboost python-multipart

# model file must be here:
# orca/model_files/pfz_xgboost_model.json   (already placed if you got this from Claude)

# Ollama must be running locally with llama3.2 pulled:
ollama pull llama3.2
ollama serve   # usually already running as a service after install

uvicorn app.main:app --reload --port 8000
```

Then open http://localhost:8000/docs for interactive API docs.

## Manual sanity checks (run these BEFORE your demo)

**1. ERDDAP SST** (should return a number around 25-30 for Indian coastal waters):
```bash
curl "https://coastwatch.pfeg.noaa.gov/erddap/griddap/jplMURSST41.csv?analysed_sst[(last)][(16.10)][(72.35)]"
```

**2. ERDDAP chlorophyll**:
```bash
curl "https://coastwatch.noaa.gov/erddap/griddap/noaacwNPPVIIRSchlaDaily.csv?chlor_a[(last)][(16.10)][(72.35)]"
```

**3. Open-Meteo wind speed**:
```bash
curl "https://api.open-meteo.com/v1/forecast?latitude=16.10&longitude=72.35&current=wind_speed_10m"
```

**4. Open-Meteo waves**:
```bash
curl "https://marine-api.open-meteo.com/v1/marine?latitude=16.10&longitude=72.35&hourly=wave_height,wave_direction,wind_wave_height,swell_wave_height&forecast_days=3"
```

**5. GDACS cyclones** -- IMPORTANT: check the actual property key names in the response,
they were not verified live. Look at a `features[0].properties` object and compare
against the guesses in `app/sources/gdacs.py` (`_first_present` calls) -- fix the
key names there if they don't match:
```bash
curl "https://www.gdacs.org/datacoast/geojson/cyclones.geojson" | python3 -m json.tool | head -50
```

If any of these fail or return an unexpected shape, tell Claude the actual response
and the corresponding source file can be patched in one pass.

## API endpoints

- `GET /health` -- liveness check
- `POST /pfz` -- `{"latitude": 16.10, "longitude": 72.35}` -> PFZ probability + raw conditions
- `POST /weather` -- marine wave/wind conditions for a point
- `POST /alerts` -- nearby active cyclones (Indian Ocean filtered)
- `POST /advisory` -- the full pipeline: all of the above + LLM-synthesized natural-language advisory.
  Optionally include `"question": "..."` for the LLM to address a specific question.

## Known gaps / next steps
- No caching layer yet -- every request re-fetches all sources live. Fine for a demo,
  add Redis/simple TTL cache before any real load.
- GDACS property key names need live verification (see check #5 above).
- Frontend (React-Leaflet) isn't in this backend -- point it at these endpoints.
- No navigation/routing endpoint yet -- wire in RouteMaster as a new `/navigate` endpoint
  following the same pattern as the others here.
