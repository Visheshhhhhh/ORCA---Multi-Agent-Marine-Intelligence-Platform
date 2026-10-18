import math
import json
import requests
from app.model import predict_pfz_score
from app.geofencing import check_boundaries
from app.sources import erddap, gdacs, openmeteo

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "llama3.2"
TIMEOUT_SECONDS = 15

# Session dictionary for multi-turn chat history: {session_id: [messages]}
sessions = {}

class MarineSafetyAgent:
    """
    Analyzes weather (wind, waves) and cyclones to determine safety index.
    Status levels: SAFE, CAUTION, UNSAFE.
    """
    def evaluate_safety(self, weather: dict, cyclones: dict) -> dict:
        warnings = []
        status = "SAFE"
        
        # 1. Evaluate Wave height
        waves = weather.get("waves")
        if waves:
            wave_height = waves.get("wave_height_m")
            if wave_height is not None:
                if wave_height >= 2.5:
                    status = "UNSAFE"
                    warnings.append(f"Dangerous high waves of {wave_height}m detected.")
                elif wave_height >= 1.8 and status != "UNSAFE":
                    status = "CAUTION"
                    warnings.append(f"Moderate rough waves of {wave_height}m. Exercise caution.")

        # 2. Evaluate Wind speed
        wind_speed = weather.get("wind_speed_kmh")
        if wind_speed is not None:
            if wind_speed >= 40.0:
                status = "UNSAFE"
                warnings.append(f"High gale winds of {wind_speed} km/h detected.")
            elif wind_speed >= 25.0 and status != "UNSAFE":
                status = "CAUTION"
                warnings.append(f"Strong winds of {wind_speed} km/h. Keep check of wind shifts.")

        # 3. Evaluate Cyclones
        for cyclone in cyclones.get("cyclones", []):
            if cyclone.get("is_relevant"):
                dist = cyclone.get("distance_km", 0)
                sev = cyclone.get("severity", "unknown")
                status = "UNSAFE"
                warnings.append(f"Active Tropical Cyclone '{cyclone.get('name')}' is within {dist} km (Alert Level: {sev}). DO NOT venture out.")

        return {
            "status": status,
            "warnings": warnings,
            "is_safe": status in ["SAFE", "CAUTION"]
        }


class PFZAgent:
    """
    Evaluates Habitat Suitability Index (HSI) and Potential Fishing Zone probability.
    """
    def evaluate_fishing_potential(self, latitude: float, longitude: float, ocean: dict, marine: dict) -> dict:
        sst = ocean.get("sst")
        chlor = ocean.get("chlorophyll")
        wind = marine.get("wind_speed_kmh")
        
        if sst is None or chlor is None or wind is None:
            return {
                "pfz_probability": 0.0,
                "hsi_rating": "POOR",
                "notes": "Insufficient oceanographic readings to predict fishing zone probability."
            }
            
        prob = predict_pfz_score(latitude, longitude, sst, chlor, wind)
        
        if prob >= 0.75:
            rating = "EXCELLENT"
        elif prob >= 0.5:
            rating = "GOOD"
        elif prob >= 0.3:
            rating = "FAIR"
        else:
            rating = "POOR"
            
        return {
            "pfz_probability": round(prob, 3),
            "hsi_rating": rating,
            "notes": f"PFZ index estimated at {round(prob * 100, 1)}% based on biological and thermal properties."
        }


class RoutingAgent:
    """
    Autonomously searches neighboring coordinates to recommend an optimized safe route
    if the primary target is geofenced (restricted/IMBL) or weather-cautioned.
    """
    def find_safe_alternative(self, latitude: float, longitude: float, sst: float, chlorophyll: float, wind_speed: float) -> dict | None:
        # Search grid offsets (about 5 km to 20 km offsets)
        offsets = [-0.15, -0.10, -0.05, 0.05, 0.10, 0.15]
        best_candidate = None
        best_score = -1.0
        
        for lat_off in offsets:
            for lon_off in offsets:
                c_lat = latitude + lat_off
                c_lon = longitude + lon_off
                
                # Check boundaries for candidate
                geo = check_boundaries(c_lat, c_lon)
                if not geo["is_safe_waters"]:
                    continue  # Crossed boundary or inside protected park, skip
                    
                # Run the prediction model on candidate
                prob = predict_pfz_score(c_lat, c_lon, sst, chlorophyll, wind_speed)
                
                if prob > best_score:
                    best_score = prob
                    brng_deg, heading_en, heading_hi = self._calculate_bearing(latitude, longitude, c_lat, c_lon)
                    best_candidate = {
                        "latitude": round(c_lat, 4),
                        "longitude": round(c_lon, 4),
                        "pfz_probability": round(prob, 3),
                        "sst": round(sst, 2),
                        "chlorophyll": round(chlorophyll, 4) if chlorophyll else None,
                        "wind_speed": round(wind_speed, 1),
                        "distance_km": round(self._distance_km(latitude, longitude, c_lat, c_lon), 1),
                        "bearing_deg": brng_deg,
                        "heading_en": heading_en,
                        "heading_hi": heading_hi
                    }
                    
        return best_candidate

    def _distance_km(self, lat1, lon1, lat2, lon2):
        r = 6371.0
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dp = math.radians(lat2 - lat1)
        dl = math.radians(lon2 - lon1)
        a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
        return 2 * r * math.asin(math.sqrt(a))

    def _calculate_bearing(self, lat1, lon1, lat2, lon2) -> tuple[float, str, str]:
        dLon = math.radians(lon2 - lon1)
        r_lat1 = math.radians(lat1)
        r_lat2 = math.radians(lat2)
        y = math.sin(dLon) * math.cos(r_lat2)
        x = math.cos(r_lat1) * math.sin(r_lat2) - math.sin(r_lat1) * math.cos(r_lat2) * math.cos(dLon)
        brng = math.atan2(y, x)
        brng = math.degrees(brng)
        brng = (brng + 360) % 360
        
        # Directions in Hindi & English
        directions_en = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
        directions_hi = ["उत्तर", "उत्तर-उत्तर-पूर्व", "उत्तर-पूर्व", "पूर्व-उत्तर-पूर्व", "पूर्व", "पूर्व-दक्षिण-पूर्व", "दक्षिण-पूर्व", "दक्षिण-दक्षिण-पूर्व", "दक्षिण", "दक्षिण-दक्षिण-पश्चिम", "दक्षिण-पश्चिम", "पश्चिम-दक्षिण-पश्चिम", "पश्चिम", "पश्चिम-उत्तर-पश्चिम", "उत्तर-पश्चिम", "उत्तर-उत्तर-पश्चिम"]
        
        idx = int((brng + 11.25) / 22.5) % 16
        return round(brng, 1), directions_en[idx], directions_hi[idx]


class SynthesisAgent:
    """
    Converts metrics, boundaries warnings, and alternative routing calculations
    into a multilingual plain-language advisory.
    """
    SYSTEM_PROMPT = """You are ORCA, a marine advisory agent for fishermen and researchers. \
You are given structured telemetry: PFZ probability, weather safety, geofencing boundary alerts, tide states, \
and any autonomous alternative safe route calculated by the Routing Agent.

Provide a highly structured response using the following format:
- **STATUS**: [Safe, Caution, or Danger]
- **SAFETY ALERT**: [Highlight any active cyclones, high waves, or geofence boundary crossings, or state 'None']
- **ADVISORY**: [Actionable steering heading, bearing, distance, and safe zones]
- **CONDITIONS**: [SST, Chlorophyll, Wind Speed, and Tide height]

Keep the tone practical, concise, and professional.
"""

    def generate(self, data_summary: dict, user_query: str | None = None, language: str | None = None) -> str:
        lang = language if language else self._guess_language(user_query)
        prompt = f"Data:\n{json.dumps(data_summary, indent=2)}\n\n"
        if user_query:
            prompt += f"User Query: {user_query}\n\n"
        prompt += f"Give the advisory now in the requested language code: '{lang}' (e.g. 'en' for English, 'hi' for Hindi in Devanagari script, 'ta' for Tamil)."

        payload = {
            "model": MODEL_NAME,
            "system": self.SYSTEM_PROMPT,
            "prompt": prompt,
            "stream": False
        }

        try:
            resp = requests.post(OLLAMA_URL, json=payload, timeout=TIMEOUT_SECONDS)
            resp.raise_for_status()
            return resp.json()["response"].strip()
        except Exception as e:
            # Multi-lingual fallback if Ollama/LLM is not running
            return self._get_fallback_advisory(data_summary, lang)

    def _guess_language(self, query: str | None) -> str:
        if not query:
            return "en"
        q = query.lower()
        # Hindi & Hinglish keywords
        if any(w in q for w in ["मछली", "सुरक्षित", "क्या", "आज", "सागर", "हवा", "तूफान", "aaj", "kahan", "nazdeek", "paas", "sabse", "jaha", "sakta", "hu", "hai", "liye", "fishing"]):
            return "hi"
        # Tamil keywords
        if any(w in q for w in ["மீன்", "பாதுகாப்பு", "இன்று", "கடல்", "காற்று", "புயல்"]):
            return "ta"
        # Marathi keywords
        if any(w in q for w in ["सुरक्षित", "मासे", "आज", "वारा", "समुद्र", "वादळ"]):
            return "mr"
        return "en"

    def _get_fallback_advisory(self, data: dict, lang: str) -> str:
        safety = data.get("safety", {})
        pfz = data.get("pfz", {})
        geo = data.get("geofencing", {})
        alt = data.get("alternative_route")
        tide = data.get("tide", {})
        ocean = data.get("metrics", {})  # contains sst and chlorophyll in dict
        
        status = safety.get("status")
        prob_percent = round(pfz.get("pfz_probability", 0.0) * 100, 1)
        
        # English fallback
        if lang == "en":
            if pfz.get("hsi_rating") == "OUT OF BOUNDS":
                return "[Out of Bounds] Selected location is outside ORCA's operational boundary (Indian EEZ). Please select a location in the Indian Ocean, Arabian Sea, or Bay of Bengal."
            if pfz.get("hsi_rating") == "LAND":
                return "**STATUS**: LAND\n**SAFETY ALERT**: Selected location is on land.\n**ADVISORY**: ORCA provides marine advisories only. Please click on a location in the sea."
            
            alert = "None"
            if not safety.get("is_safe"):
                alert = "UNSAFE: High winds/waves or active cyclone. Stay in port."
            elif not geo.get("is_safe_waters"):
                alert = "RESTRICTED/BORDER WARNING: " + " ".join([a['message'] for a in geo.get("alerts", [])])
            
            advisory = "Safe to venture out."
            if not safety.get("is_safe"):
                advisory = "Do not venture into the sea."
            elif not geo.get("is_safe_waters"):
                if alt:
                    advisory = f"Steer {alt['bearing_deg']}° ({alt['heading_en']}) for {alt['distance_km']} km to reach safe zone (Lat {alt['latitude']}, Lon {alt['longitude']})."
                else:
                    advisory = "Turn back immediately to safe waters."
            elif alt and alt["pfz_probability"] > pfz.get("pfz_probability", 0.0):
                advisory = f"High-yield PFZ located nearby. Steer {alt['bearing_deg']}° ({alt['heading_en']}) for {alt['distance_km']} km (PFZ probability: {round(alt['pfz_probability']*100)}%)."
                
            return f"**STATUS**: {status}\n" \
                   f"**SAFETY ALERT**: {alert}\n" \
                   f"**ADVISORY**: {advisory}\n" \
                   f"**CONDITIONS**: SST: {ocean.get('sst_celsius') or 'N/A'}°C, Chlorophyll: {ocean.get('chlorophyll_mg_per_m3') or 'N/A'} mg/m³, Tide: {tide.get('status')} ({tide.get('tide_height_m')}m)"

        # Hindi fallback
        elif lang == "hi":
            if pfz.get("hsi_rating") == "OUT OF BOUNDS":
                return "[सीमा के बाहर] चुना गया स्थान ओआरसीए की परिचालन सीमा (भारतीय ईईजेड) से बाहर है। कृपया हिंद महासागर, अरब सागर या बंगाल की खाड़ी में किसी स्थान का चयन करें।"
            if pfz.get("hsi_rating") == "LAND":
                return "**स्थिति**: भूमि (जमीन)\n**सुरक्षा चेतावनी**: चुना गया स्थान जमीन पर है।\n**सलाह**: ओआरसीए केवल समुद्री सलाह प्रदान करता है। कृपया समुद्र में किसी स्थान पर क्लिक करें।"
            
            alert = "कोई नहीं"
            if not safety.get("is_safe"):
                alert = "असुरक्षित: तेज हवाएं/लहरें या सक्रिय चक्रवात। कृपया बंदरगाह पर रहें।"
            elif not geo.get("is_safe_waters"):
                alert = "सीमा चेतावनी: " + " ".join(["आपने अंतर्राष्ट्रीय समुद्री सीमा पार कर ली है! तुरंत वापस लौटें।" if "IMBL" in a["zone"] else "प्रतिबंधित क्षेत्र में प्रवेश!" for a in geo.get("alerts", [])])
            
            advisory = "समुद्र में जाने के लिए सुरक्षित।"
            if not safety.get("is_safe"):
                advisory = "समुद्र में न जाएं।"
            elif not geo.get("is_safe_waters"):
                if alt:
                    advisory = f"सुरक्षित वैकल्पिक स्थान पर जाने के लिए {alt['bearing_deg']}° ({alt['heading_hi']}) दिशा में {alt['distance_km']} किमी चलें (अक्षांश {alt['latitude']}, रेखांश {alt['longitude']})।"
                else:
                    advisory = "तुरंत सुरक्षित पानी की ओर वापस लौटें।"
            elif alt and alt["pfz_probability"] > pfz.get("pfz_probability", 0.0):
                advisory = f"पास में अच्छा मछली पकड़ने का क्षेत्र उपलब्ध है। वहां जाने के लिए {alt['bearing_deg']}° ({alt['heading_hi']}) दिशा में {alt['distance_km']} किमी चलें (मछली संभावना: {round(alt['pfz_probability']*100)}%)।"
                
            return f"**स्थिति**: {status}\n" \
                   f"**सुरक्षा चेतावनी**: {alert}\n" \
                   f"**सलाह**: {advisory}\n" \
                   f"**समुद्र की स्थिति**: तापमान: {ocean.get('sst_celsius') or 'N/A'}°C, क्लोरोफिल: {ocean.get('chlorophyll_mg_per_m3') or 'N/A'} mg/m³, ज्वार: {tide.get('status')} ({tide.get('tide_height_m')}m)"

        # Tamil fallback
        elif lang == "ta":
            if pfz.get("hsi_rating") == "OUT OF BOUNDS":
                return "[எல்லைக்கு வெளியே] தேர்ந்தெடுக்கப்பட்ட இடம் ஓர்காவின் செயல்பாட்டு எல்லைக்கு (இந்திய EEZ) வெளியே உள்ளது. தயவுசெய்து இந்தியப் பெருங்கடல், அரபிக்கடல் அல்லது வங்காள விரிகுடாவில் ஒரு இடத்தை தேர்வு செய்யவும்."
            if pfz.get("hsi_rating") == "LAND":
                return "**நிலை**: நிலம்\n**பாதுகாப்பு எச்சரிக்கை**: தேர்ந்தெடுக்கப்பட்ட இடம் நிலத்தில் உள்ளது.\n**ஆலோசனை**: ஓர்கா கடல்சார் ஆலோசனைகளை மட்டுமே வழங்குகிறது. தயவுசெய்து கடலில் ஒரு இடத்தை கிளிக் செய்யவும்."
            
            alert = "ஏதுமில்லை"
            if not safety.get("is_safe"):
                alert = "ஆபத்தானது: பலத்த காற்று/அலைகள் அல்லது புயல். துறைமுகத்தில் இருக்கவும்."
            elif not geo.get("is_safe_waters"):
                alert = "எல்லை எச்சரிக்கை: " + " ".join(["நீங்கள் சர்வதேச எல்லை கோட்டை தாண்டினீர்கள்! உடனே திரும்புங்கள்." if "IMBL" in a["zone"] else "தடைசெய்யப்பட்ட பகுதி!" for a in geo.get("alerts", [])])
            
            advisory = "கடலுக்குச் செல்ல பாதுகாப்பானது."
            if not safety.get("is_safe"):
                advisory = "கடலுக்குச் செல்ல வேண்டாம்."
            elif not geo.get("is_safe_waters"):
                if alt:
                    advisory = f"பாதுகாப்பான மாற்று பகுதிக்கு செல்ல {alt['bearing_deg']}° ({alt['heading_en']}) திசையில் {alt['distance_km']} கிமீ செல்லவும் (அட்சரேகை {alt['latitude']}, தீர்க்கரேகை {alt['longitude']})."
                else:
                    advisory = "உடனே பாதுகாப்பான கடல் பகுதிக்கு திரும்புங்கள்."
            elif alt and alt["pfz_probability"] > pfz.get("pfz_probability", 0.0):
                advisory = f"அருகிலுள்ள நல்ல மீன்பிடி பகுதி உள்ளது. அங்கு செல்ல {alt['bearing_deg']}° ({alt['heading_en']}) திசையில் {alt['distance_km']} கிமீ செல்லவும் (வாய்ப்பு {round(alt['pfz_probability']*100)}%)."
                
            return f"**நிலை**: {status}\n" \
                   f"**பாதுகாப்பு எச்சரிக்கை**: {alert}\n" \
                   f"**ஆலோசனை**: {advisory}\n" \
                   f"**கடல் நிலைமைகள்**: கடல் வெப்பநிலை: {ocean.get('sst_celsius') or 'N/A'}°C, குளோரோபில்: {ocean.get('chlorophyll_mg_per_m3') or 'N/A'} mg/m³, அலை ஏற்றம்: {tide.get('status')} ({tide.get('tide_height_m')}m)"

        return f"Sea state is {status}. Fishing probability: {prob_percent}%. Boundaries: {'Safe' if geo.get('is_safe_waters') else 'Alert'}"


def calculate_tide_conditions(latitude: float, longitude: float) -> dict:
    import time
    # Tides fluctuate semi-diurnally (every 12 hours and 25 minutes = 44712 seconds)
    current_time = time.time()
    phase_shift = (longitude + latitude) * 0.2
    cycle_position = (current_time / 44712.0 + phase_shift) % 1.0
    tide_rad = cycle_position * 2.0 * math.pi
    
    height = 1.0 + 0.8 * math.sin(tide_rad)
    derivative = math.cos(tide_rad)
    
    if abs(derivative) < 0.15:
        status = "HIGH TIDE" if height > 1.0 else "LOW TIDE"
    else:
        status = "FLOOD TIDE" if derivative > 0.0 else "EBB TIDE"
        
    return {
        "tide_height_m": round(height, 2),
        "status": status,
        "description": f"Currently in {status.lower()} phase with a tide height of {round(height, 2)}m."
    }


class SupervisorAgent:
    """
    Autonomous coordinator of the ORCA multi-agent system.
    Determines flow execution, handles session memory, and aggregates outputs.
    """
    def __init__(self):
        self.safety_agent = MarineSafetyAgent()
        self.pfz_agent = PFZAgent()
        self.routing_agent = RoutingAgent()
        self.synthesis_agent = SynthesisAgent()

    def process_query(self, latitude: float, longitude: float, query: str | None = None, session_id: str | None = None, language: str | None = None) -> dict:
        # Load conversation memory
        history = []
        if session_id:
            if session_id not in sessions:
                sessions[session_id] = []
            history = sessions[session_id]
            
        # 1. Fetch live telemetry (in parallel)
        # Fetching data using standard source modules
        ocean = erddap.get_ocean_conditions(latitude, longitude)
        marine = openmeteo.get_marine_conditions(latitude, longitude)
        cyclones = gdacs.get_nearby_cyclone_alerts(latitude, longitude)

        # 2. Run domain agents
        safety_eval = self.safety_agent.evaluate_safety(marine, cyclones)
        pfz_eval = self.pfz_agent.evaluate_fishing_potential(latitude, longitude, ocean, marine)
        geo_eval = check_boundaries(latitude, longitude)

        # Detect inland / land coordinates
        # Both ERDDAP SST and OpenMeteo Wave Heights are ocean-only, returning None for land
        is_on_land = (ocean.get("sst") is None) and (marine.get("waves") is None or marine.get("waves", {}).get("wave_height_m") is None)

        # Detect operational boundaries (Lat 5-25 N, Lon 65-95 E)
        is_out_of_bounds = not (5.0 <= latitude <= 25.0 and 65.0 <= longitude <= 95.0)

        # Compute Tide Conditions
        tide_eval = calculate_tide_conditions(latitude, longitude)

        if is_out_of_bounds:
            tide_eval = {
                "tide_height_m": 0.0,
                "status": "N/A",
                "description": "Location is outside operational boundary."
            }
            safety_eval = {
                "status": "N/A",
                "warnings": ["Location is outside Indian Operational Boundary."],
                "is_safe": False
            }
            pfz_eval = {
                "pfz_probability": 0.0,
                "hsi_rating": "OUT OF BOUNDS",
                "notes": "Coordinates are outside ORCA's regional operational area (Lat 5-25 N, Lon 65-95 E)."
            }
            geo_eval = {
                "is_safe_waters": False,
                "alerts": [{
                    "zone": "Global",
                    "status": "OUT_OF_BOUNDS",
                    "message": "Selected coordinate is outside the Indian EEZ operational boundary.",
                    "distance_km": 0.0
                }]
            }
        elif is_on_land:
            tide_eval = {
                "tide_height_m": 0.0,
                "status": "N/A",
                "description": "Location is on land."
            }
            # Overwrite domain agents outputs to mark land query
            safety_eval = {
                "status": "N/A",
                "warnings": ["Selected location is on land."],
                "is_safe": False
            }
            pfz_eval = {
                "pfz_probability": 0.0,
                "hsi_rating": "LAND",
                "notes": "ORCA provides marine intelligence only. Selected coordinate is inland."
            }
            geo_eval = {
                "is_safe_waters": False,
                "alerts": [{
                    "zone": "Inland",
                    "status": "LAND",
                    "message": "Selected coordinate is on land.",
                    "distance_km": 0.0
                }]
            }

        # 3. Autonomous routing decisions
        alternative_route = None
        
        # Only check alternatives if we are in the water and inside boundaries
        if not is_on_land and not is_out_of_bounds:
            is_restricted = not geo_eval["is_safe_waters"]
            is_weather_caution = safety_eval["status"] in ["CAUTION", "UNSAFE"]
            
            # Check if the user is asking for the nearest/best zone, or if the current spot has low fishing potential
            is_asking_nearest = False
            if query:
                q = query.lower()
                nearest_keywords = ["nearest", "where", "best", "nazdeek", "kahan", "paas", "achha", "அருகில்", "எங்கே"]
                is_asking_nearest = any(kw in q for kw in nearest_keywords)
                
            low_fishing_potential = pfz_eval["pfz_probability"] < 0.5
            
            # Trigger alternative routing if:
            # - Target is restricted (crossed IMBL/protected area)
            # - Weather is cautioned
            # - Current spot is poor/fair and user asks or we want to proactively recommend a better spot
            if is_restricted or (is_weather_caution and safety_eval["status"] == "CAUTION") or (low_fishing_potential and is_asking_nearest) or (low_fishing_potential and query is not None):
                sst = ocean.get("sst") or 28.0
                chlor = ocean.get("chlorophyll") or 0.15
                wind = marine.get("wind_speed_kmh") or 15.0
                alternative_route = self.routing_agent.find_safe_alternative(latitude, longitude, sst, chlor, wind)

        # 4. Generate explainable natural-language recommendations
        data_summary = {
            "coordinates": {"latitude": latitude, "longitude": longitude},
            "safety": safety_eval,
            "pfz": pfz_eval,
            "geofencing": geo_eval,
            "tide": tide_eval,
            "alternative_route": alternative_route
        }

        # Include chat history context in the LLM query if present
        if history:
            data_summary["conversation_history"] = history[-4:] # Keep last 4 turns for context

        advisory_text = self.synthesis_agent.generate(data_summary, query, language)

        # Update conversation history
        if session_id:
            sessions[session_id].append({"role": "user", "content": query or f"Check coordinates {latitude}, {longitude}"})
            sessions[session_id].append({"role": "assistant", "content": advisory_text})

        return {
            "advisory": advisory_text,
            "session_id": session_id,
            "metrics": {
                "sst_celsius": ocean.get("sst"),
                "chlorophyll_mg_per_m3": ocean.get("chlorophyll"),
                "wind_speed_kmh": marine.get("wind_speed_kmh"),
                "waves": marine.get("waves"),
                "tide_height_m": tide_eval["tide_height_m"],
                "tide_status": tide_eval["status"]
            },
            "safety_status": safety_eval["status"],
            "safety_warnings": safety_eval["warnings"],
            "geofencing": geo_eval,
            "alternative_route": alternative_route,
            "pfz_probability": pfz_eval["pfz_probability"],
            "hsi_rating": pfz_eval["hsi_rating"],
            "source_evidence": {
                "noaa_sst_url": ocean.get("sst_url"),
                "noaa_chlorophyll_url": ocean.get("chlorophyll_url"),
                "openmeteo_waves_url": marine.get("waves_url"),
                "openmeteo_wind_url": marine.get("wind_url"),
                "gdacs_cyclones_url": "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH?eventtype=TC&iscurrent=true"
            }
        }
