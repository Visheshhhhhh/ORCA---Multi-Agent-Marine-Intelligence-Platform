# Three-Minute Project Introduction

## Spoken Script

"Hi, I’m excited to share my project, **ORCA** (Ocean Resource & Coastal Analytics), which is a real-time marine intelligence and safety advisory platform designed primarily for coastal fishermen and maritime operators in India.

The **problem** we are solving is two-fold: safety and productivity. Fishermen venture into the sea every day with very little visibility into wave forecasts, changing weather, or restricted zones, and they often cross international maritime boundaries like the India-Sri Lanka IMBL, resulting in vessel seizures. At the same time, finding high-yield fishing zones requires reading complex satellite remote sensing data (like sea surface temperature and chlorophyll concentrations) which is published in formats that are impossible to consume on a boat.

To solve this, I designed a **collaborative multi-agent system** built on FastAPI, Leaflet.js, and a local machine learning stack. 

Here is how the system works:
When a user clicks on the map or asks a query, the **Supervisor Agent** coordinates a series of data fetches. It queries the live **NOAA ERDDAP satellite feeds** to pull Sea Surface Temperature and Chlorophyll-a data. It also calls **Open-Meteo's Marine API** to retrieve wave height, direction, and wind speed, and the **UN/EU GDACS feed** to check for active cyclones.

All this data is run through two engines:
First, a **rules-based Safety Engine** evaluates weather hazards and checks geofencing boundaries using a ray-casting algorithm to ensure the vessel isn't crossing international borders.
Second, an **XGBoost machine learning model** processes the oceanographic parameters to calculate the Potential Fishing Zone probability.

If the selected location is unsafe or has low fishing potential, the **Routing Agent** autonomously takes over. It performs a concentric grid search, calculates spherical bearings using the Haversine formula, and determines the exact compass heading to steer the vessel to the nearest safe, high-yield alternative. 

Finally, the **Synthesis Agent** uses a local **Ollama** instance running Llama 3.2 to generate a natural, structured advisory in the user's chosen language—English, Hindi, or Tamil. To ensure reliability, if the local LLM is offline, the agent automatically falls back to pre-translated deterministic templates.

A key engineering trade-off I made was choosing a **stateless architecture** over local database replication. Because satellite ocean data updates hourly, replicating global grids would take terabytes of space. By querying space agency servers directly via REST, we keep the backend lightweight, though it introduces a network latency dependency which we manage with strict timeout rules.

Right now, ORCA is a fully functioning MVP. The next step is converting the backend fetches into asynchronous concurrent requests to reduce API latency, and deploying a local Redis cache to store coordinate telemetry.

I’d love to dive deeper into the agent orchestration or the ML model integration if you'd like!"

---

## Thirty-Second Version

"I built **ORCA**, a real-time marine intelligence platform designed to improve fishermen's safety and catch yield. The system uses a collaborative multi-agent architecture: a **Supervisor Agent** retrieves live satellite data from NOAA and weather models from Open-Meteo, evaluates restricted borders via geofencing, and estimates fishing potential using an XGBoost model. If a zone is unsafe or low-yield, a **Routing Agent** calculates navigation headings to the nearest safe alternative. Finally, a **Synthesis Agent** uses local Llama 3.2 via Ollama to generate structured, multilingual advisories in English, Hindi, or Tamil, falling back to deterministic templates if offline."

---

## Key Points to Remember

* **Product Purpose:** Real-time safety alerting, geofencing border checks, and Potential Fishing Zone (PFZ) classification.
* **Agent Coordination:** Supervisor (orchestrator), Routing (geographic calculations & alternative search), and Synthesis (natural language output).
* **Live Telemetry:** Real-time integration with NOAA ERDDAP satellites, Open-Meteo Marine, and UN GDACS databases.
* **ML Model:** XGBoost classifier predicting fishing suitability from chlorophyll-a and sea surface temperature.
* **Resilience:** Deterministic fallback templates in English, Hindi, and Tamil if the local Ollama instance is offline or slow.
* **Performance Challenge:** Synchronous external API calls are the primary bottleneck; moving to async requests is the immediate roadmap priority.
* **Geofencing Safety:** Ray-casting checks for Indo-Pakistani borders, Indo-Sri Lankan borders, and the protected Gulf of Mannar region.
