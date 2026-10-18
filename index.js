// App configuration
const BACKEND_URL = ""; // Empty string calls relative paths on the same host

let map;
let selectedMarker = null;
let alternativeMarker = null;
let routeLine = null;
let currentCoordinates = { lat: 9.9312, lng: 76.2673 }; // Default Kochi
let session_id = 'session_' + Math.random().toString(36).substring(2, 9);
let currentAdvisory = "";
let dangerZoneLayers = []; // Stores dynamic weather and cyclone danger overlays

// Maritime Boundary Coordinates
const SRI_LANKA_IMBL = [
    [8.5, 79.0],
    [9.0, 79.4],
    [9.25, 79.35],
    [9.5, 79.5],
    [9.75, 79.8],
    [10.0, 80.0],
    [10.5, 80.3]
];

// Sri Lanka Territorial Waters Polygon for shading
const SRI_LANKA_POLYGON = [
    [8.5, 79.0],
    [9.0, 79.4],
    [9.25, 79.35],
    [9.5, 79.5],
    [9.75, 79.8],
    [10.0, 80.0],
    [10.5, 80.3],
    [10.5, 82.0],
    [8.5, 82.0]
];

// Gulf of Mannar Restricted Area coordinates
const GULF_OF_MANNAR_BOUNDS = [
    [8.8, 78.1],
    [9.25, 79.25]
];

// Pakistan sir creek line (approximated for visual guide)
const PAKISTAN_BORDER = [
    [22.0, 68.16],
    [24.5, 68.16]
];

// Pakistan territorial waters polygon for shading
const PAKISTAN_POLYGON = [
    [22.0, 68.16],
    [24.5, 68.16],
    [24.5, 65.0],
    [22.0, 65.0]
];

// Language voices mapping for SpeechSynthesis
const VOICE_LANG_MAP = {
    "en": "en-IN",
    "hi": "hi-IN",
    "ta": "ta-IN",
    "mr": "hi-IN", // Fallback to Hindi voice if Marathi is unavailable
    "te": "te-IN",
    "ml": "ml-IN",
    "gu": "gu-IN",
    "bn": "bn-IN"
};

document.addEventListener("DOMContentLoaded", () => {
    initMap();
    initEventListeners();
    // Fetch default coordinate data on load
    fetchAdvisory(currentCoordinates.lat, currentCoordinates.lng);
});

function initMap() {
    // Initialize map centered off southwest coast of India
    map = L.map('map').setView([currentCoordinates.lat, currentCoordinates.lng], 7);

    // Standard OpenStreetMap tiles (which get inverted via CSS for dark-mode look)
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 18,
        attribution: '© OpenStreetMap contributors'
    }).addTo(map);

    // Plot Sri Lanka Boundary Line
    L.polyline(SRI_LANKA_IMBL, {
        color: '#ff1744',
        weight: 3,
        dashArray: '5, 8',
        opacity: 0.8
    }).addTo(map).bindPopup("<b>Sri Lanka Maritime Boundary Line (IMBL)</b><br>Crossings are highly restricted.");

    // Shade Sri Lanka Territorial Waters (Danger Zone)
    L.polygon(SRI_LANKA_POLYGON, {
        fillColor: '#ff1744',
        fillOpacity: 0.12,
        color: 'transparent'
    }).addTo(map).bindPopup("<b>Sri Lanka Territorial Waters</b><br>Danger Zone: Entry restricted.");

    // Plot Pakistan Boundary Line
    L.polyline(PAKISTAN_BORDER, {
        color: '#ff1744',
        weight: 3,
        dashArray: '5, 8',
        opacity: 0.8
    }).addTo(map).bindPopup("<b>Pakistan Maritime Boundary Line</b><br>Approaching this line requires caution.");

    // Shade Pakistan Territorial Waters (Danger Zone)
    L.polygon(PAKISTAN_POLYGON, {
        fillColor: '#ff1744',
        fillOpacity: 0.12,
        color: 'transparent'
    }).addTo(map).bindPopup("<b>Pakistan Territorial Waters</b><br>Danger Zone: Entry restricted.");

    // Plot Gulf of Mannar Restricted Box
    L.rectangle(GULF_OF_MANNAR_BOUNDS, {
        color: '#ffd600',
        weight: 1.5,
        fillColor: '#ffd600',
        fillOpacity: 0.08,
        dashArray: '4, 4'
    }).addTo(map).bindPopup("<b>Gulf of Mannar Biosphere Reserve</b><br>Protected Area: Commercial fishing prohibited.");

    // Plot ORCA Operational Boundary (Indian EEZ / XGBoost training limit)
    L.rectangle([[5.0, 65.0], [25.0, 95.0]], {
        color: '#00e5ff',
        weight: 1.5,
        fill: false,
        dashArray: '6, 12',
        opacity: 0.7
    }).addTo(map).bindPopup("<b>ORCA Operational Boundary (Indian EEZ)</b><br>XGBoost PFZ predictions are only calibrated inside this region.");

    // Click handler for coordinates
    map.on('click', (e) => {
        const { lat, lng } = e.latlng;
        setQueryLocation(lat, lng);
    });

    // Default Kochi Marker
    setQueryMarker(currentCoordinates.lat, currentCoordinates.lng);
}

function initEventListeners() {
    // Geolocation button
    document.getElementById("gps-btn").addEventListener("click", () => {
        if (navigator.geolocation) {
            document.getElementById("gps-btn").innerHTML = "⌛ Finding GPS Position...";
            navigator.geolocation.getCurrentPosition(
                (position) => {
                    const lat = position.coords.latitude;
                    const lng = position.coords.longitude;
                    document.getElementById("gps-btn").innerHTML = "📍 Share My GPS Location";
                    map.setView([lat, lng], 10);
                    setQueryLocation(lat, lng);
                },
                (error) => {
                    document.getElementById("gps-btn").innerHTML = "❌ GPS Lock Failed";
                    setTimeout(() => {
                        document.getElementById("gps-btn").innerHTML = "📍 Share My GPS Location";
                    }, 3000);
                    alert("Unable to retrieve GPS coordinate: " + error.message);
                }
            );
        } else {
            alert("Geolocation is not supported by your browser.");
        }
    });

    // Chat collapsible panel toggle
    document.getElementById("chat-header-bar").addEventListener("click", () => {
        const panel = document.getElementById("chat-panel");
        const btn = document.getElementById("toggle-chat-btn");
        panel.classList.toggle("collapsed");
        btn.innerHTML = panel.classList.contains("collapsed") ? "▲" : "▼";
    });

    // Send chat button
    document.getElementById("send-btn").addEventListener("click", sendChatMessage);
    document.getElementById("chat-input").addEventListener("keypress", (e) => {
        if (e.key === "Enter") sendChatMessage();
    });

    // Text to Speech voice play button
    document.getElementById("tts-btn").addEventListener("click", speakAdvisory);

    // Language dropdown change
    document.getElementById("language-select").addEventListener("change", () => {
        // Re-fetch advisory for the current location in the new language context
        fetchAdvisory(currentCoordinates.lat, currentCoordinates.lng);
    });
}

function setQueryLocation(lat, lng) {
    currentCoordinates = { lat, lng };
    setQueryMarker(lat, lng);
    
    // Clear route visualizations
    if (alternativeMarker) {
        map.removeLayer(alternativeMarker);
        alternativeMarker = null;
    }
    if (routeLine) {
        map.removeLayer(routeLine);
        routeLine = null;
    }
    document.getElementById("routing-card").classList.add("hidden");

    fetchAdvisory(lat, lng);
}

function setQueryMarker(lat, lng) {
    if (selectedMarker) {
        map.removeLayer(selectedMarker);
    }
    
    // Create standard circle marker with pulse styling
    selectedMarker = L.circleMarker([lat, lng], {
        radius: 8,
        color: '#00e5ff',
        fillColor: '#00e5ff',
        fillOpacity: 1,
        weight: 2
    }).addTo(map);

    selectedMarker.bindPopup(`<b>Query Coordinates</b><br>Lat: ${lat.toFixed(4)}<br>Lon: ${lng.toFixed(4)}`).openPopup();
}

async function fetchAdvisory(lat, lng, question = null) {
    // Show loadings
    document.getElementById("advisory-text").innerHTML = "⌛ Analyzing telemetry from agents...";
    document.getElementById("tts-btn").disabled = true;
    
    const selectedLang = document.getElementById("language-select").value;

    const payload = {
        latitude: lat,
        longitude: lng,
        session_id: session_id,
        language: selectedLang
    };

    if (question) {
        payload.question = question;
    }

    try {
        const response = await fetch(`${BACKEND_URL}/advisory`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            throw new Error(`Server returned status: ${response.status}`);
        }

        const data = await response.json();
        updateDashboard(data);

    } catch (error) {
        document.getElementById("advisory-text").innerHTML = `❌ Error: ${error.message}. Ensure backend is running.`;
        console.error("Advisory fetch failed:", error);
    }
}

function updateDashboard(data) {
    // 1. Set advisory text
    currentAdvisory = data.advisory;
    document.getElementById("advisory-text").innerHTML = currentAdvisory;
    document.getElementById("tts-btn").disabled = false;

    // 2. Set Parameters
    const m = data.metrics || {};
    document.getElementById("param-sst").innerHTML = m.sst_celsius ? `${m.sst_celsius.toFixed(1)} °C` : "N/A";
    document.getElementById("param-wind").innerHTML = m.wind_speed_kmh ? `${m.wind_speed_kmh.toFixed(1)} km/h` : "N/A";
    
    const waves = m.waves || {};
    document.getElementById("param-waves").innerHTML = waves.wave_height_m ? `${waves.wave_height_m.toFixed(2)} m` : "N/A";
    
    const pfz_prob = data.pfz_probability;
    const rating = data.hsi_rating || "--";
    document.getElementById("param-pfz").innerHTML = pfz_prob !== null ? `${(pfz_prob * 100).toFixed(0)}% (${rating})` : "N/A";

    document.getElementById("param-tide").innerHTML = m.tide_height_m ? `${m.tide_height_m.toFixed(2)} m (${m.tide_status})` : "N/A";
    document.getElementById("param-chlor").innerHTML = m.chlorophyll_mg_per_m3 ? `${m.chlorophyll_mg_per_m3.toFixed(3)} mg/m³` : "N/A";

    // 3. Set Safety status card
    const safetyCard = document.getElementById("safety-card");
    const safetyStatus = document.getElementById("safety-status");
    const safetyDesc = document.getElementById("safety-desc");

    safetyCard.className = "status-card"; // Reset
    
    const status = data.safety_status;
    safetyStatus.innerHTML = status;

    if (status === "SAFE") {
        safetyCard.classList.add("status-safe");
        safetyDesc.innerHTML = "Conditions are safe. Favorable winds and waves.";
    } else if (status === "CAUTION") {
        safetyCard.classList.add("status-caution");
        safetyDesc.innerHTML = data.safety_warnings.join(" ") || "Moderate weather. Navigate with awareness.";
    } else if (status === "N/A") {
        safetyCard.classList.add("status-neutral");
        safetyDesc.innerHTML = "ORCA only tracks marine coordinates. Selected point is inland.";
    } else {
        safetyCard.classList.add("status-unsafe");
        safetyDesc.innerHTML = data.safety_warnings.join(" ") || "Dangerous conditions! Do not venture out.";
    }

    // 4. Geofencing alert
    const geo = data.geofencing || {};
    const geoAlert = document.getElementById("geofence-alert");
    const geoMsg = document.getElementById("geofence-msg");

    if (!geo.is_safe_waters && geo.alerts && geo.alerts.length > 0) {
        geoAlert.classList.remove("hidden");
        geoMsg.innerHTML = geo.alerts.map(a => a.message).join("<br>");
    } else {
        geoAlert.classList.add("hidden");
    }

    // Clear and Redraw Dynamic Danger overlays (Waves / Cyclones)
    dangerZoneLayers.forEach(layer => map.removeLayer(layer));
    dangerZoneLayers = [];

    // Redraw Cyclone Alerts (Danger circles)
    const rawData = data.raw_data || {};
    const cyclonesData = rawData.cyclones || {};
    const cyclones = cyclonesData.cyclones || [];
    cyclones.forEach(c => {
        // Red circle of 250km representing cyclone zone
        const circle = L.circle([c.latitude, c.longitude], {
            color: '#ff1744',
            fillColor: '#ff1744',
            fillOpacity: 0.15,
            radius: 250000,
            weight: 2,
            dashArray: '5, 10'
        }).addTo(map);
        circle.bindPopup(`<b>WEATHER DANGER ZONE: Cyclone ${c.name}</b><br>Alert Level: ${c.severity}<br>Keep clear of this zone.`);
        dangerZoneLayers.push(circle);
    });

    // Redraw Local High Waves Caution circle (50km)
    if (waves.wave_height_m && waves.wave_height_m >= 1.8) {
        const rad = waves.wave_height_m >= 2.5 ? 60000 : 40000;
        const color = waves.wave_height_m >= 2.5 ? '#ff1744' : '#ffd600';
        const label = waves.wave_height_m >= 2.5 ? 'CRITICAL SEA STATE' : 'CAUTION ROUGH SEAS';
        const circle = L.circle([currentCoordinates.lat, currentCoordinates.lng], {
            color: color,
            fillColor: color,
            fillOpacity: 0.1,
            radius: rad,
            weight: 1.5,
            dashArray: '4, 4'
        }).addTo(map);
        circle.bindPopup(`<b>LOCAL MARINE ADVISORY: ${label}</b><br>Wave Height: ${waves.wave_height_m}m.`);
        dangerZoneLayers.push(circle);
    }

    // 5. Autonomous Route Overlay
    const alt = data.alternative_route;
    const routingCard = document.getElementById("routing-card");

    if (alt) {
        routingCard.classList.remove("hidden");
        const selectedLang = document.getElementById("language-select").value;
        const headingStr = selectedLang === "hi" ? alt.heading_hi : alt.heading_en;

        document.getElementById("route-dist").innerHTML = `${alt.distance_km} km`;
        document.getElementById("route-dir").innerHTML = `${alt.bearing_deg}° (${headingStr})`;
        document.getElementById("route-pfz").innerHTML = `${(alt.pfz_probability * 100).toFixed(0)}%`;
        
        document.getElementById("route-sst").innerHTML = alt.sst ? `${alt.sst.toFixed(1)} °C` : "N/A";
        document.getElementById("route-chl").innerHTML = alt.chlorophyll ? `${alt.chlorophyll.toFixed(2)} mg/m³` : "N/A";
        document.getElementById("route-wind").innerHTML = alt.wind_speed ? `${alt.wind_speed.toFixed(1)} km/h` : "N/A";
        
        // Remove old handler and bind new one
        const btn = document.getElementById("plot-route-btn");
        const newBtn = btn.cloneNode(true);
        btn.parentNode.replaceChild(newBtn, btn);
        
        newBtn.addEventListener("click", () => {
            plotSafeRoute(currentCoordinates.lat, currentCoordinates.lng, alt.latitude, alt.longitude);
        });
    } else {
        routingCard.classList.add("hidden");
    }

    // 6. Set Source Evidence links
    const evidence = data.source_evidence || {};
    const binds = [
        { id: "link-sst", url: evidence.noaa_sst_url },
        { id: "link-chl", url: evidence.noaa_chlorophyll_url },
        { id: "link-waves", url: evidence.openmeteo_waves_url },
        { id: "link-wind", url: evidence.openmeteo_wind_url },
        { id: "link-cyclones", url: evidence.gdacs_cyclones_url }
    ];

    binds.forEach(b => {
        const el = document.getElementById(b.id);
        if (b.url) {
            el.href = b.url;
            el.style.opacity = "1";
            el.style.pointerEvents = "auto";
        } else {
            el.removeAttribute("href");
            el.style.opacity = "0.4";
            el.style.pointerEvents = "none";
        }
    });
}

function plotSafeRoute(startLat, startLng, destLat, destLng) {
    // Clear old route layers
    if (alternativeMarker) map.removeLayer(alternativeMarker);
    if (routeLine) map.removeLayer(routeLine);

    // Create alternative marker
    alternativeMarker = L.circleMarker([destLat, destLng], {
        radius: 7,
        color: '#00e676',
        fillColor: '#00e676',
        fillOpacity: 1,
        weight: 2
    }).addTo(map);

    alternativeMarker.bindPopup(`<b>Recommended Safe Alternative Zone</b><br>Lat: ${destLat}<br>Lon: ${destLng}`).openPopup();

    // Draw dashed connection line
    routeLine = L.polyline([[startLat, startLng], [destLat, destLng]], {
        color: '#00e676',
        weight: 3,
        dashArray: '6, 6',
        opacity: 0.9
    }).addTo(map);

    // Zoom out map to show both coordinates
    const bounds = L.latLngBounds([
        [startLat, startLng],
        [destLat, destLng]
    ]);
    map.fitBounds(bounds, { padding: [50, 50] });
}

function speakAdvisory() {
    if (!currentAdvisory) return;

    // Remove fallback bracket tags for TTS cleanliness
    let cleanText = currentAdvisory.replace(/\[.*?\]/g, "").trim();

    if ('speechSynthesis' in window) {
        // Cancel ongoing synthesis
        window.speechSynthesis.cancel();

        const utterance = new SpeechSynthesisUtterance(cleanText);
        
        // Match language voice
        const selectedLang = document.getElementById("language-select").value;
        const requestedLocale = VOICE_LANG_MAP[selectedLang] || "en-IN";
        
        utterance.lang = requestedLocale;

        // Try to bind voice model matching the language
        const voices = window.speechSynthesis.getVoices();
        const voice = voices.find(v => v.lang.startsWith(requestedLocale) || v.lang === requestedLocale);
        if (voice) {
            utterance.voice = voice;
        }

        window.speechSynthesis.speak(utterance);
    } else {
        alert("Text-to-Speech is not supported in this browser.");
    }
}

async function sendChatMessage() {
    const inputEl = document.getElementById("chat-input");
    const queryText = inputEl.value.trim();
    if (!queryText) return;

    appendChatMessage("user", queryText);
    inputEl.value = "";

    // Show processing indicator
    const bubbleId = "bubble_" + Date.now();
    appendChatMessage("assistant", "⌛ Thinking...", bubbleId);

    try {
        const selectedLang = document.getElementById("language-select").value;
        const payload = {
            latitude: currentCoordinates.lat,
            longitude: currentCoordinates.lng,
            question: queryText,
            session_id: session_id,
            language: selectedLang
        };

        const response = await fetch(`${BACKEND_URL}/advisory`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        const data = await response.json();
        
        // Update bubble text
        document.getElementById(bubbleId).innerHTML = data.advisory;
        
        // Update general cards if coordinate metrics updated
        updateDashboard(data);

    } catch (error) {
        document.getElementById(bubbleId).innerHTML = `❌ Error: ${error.message}`;
    }
}

function appendChatMessage(sender, text, id = null) {
    const history = document.getElementById("chat-history");
    const bubble = document.createElement("div");
    bubble.className = `chat-msg ${sender}`;
    if (id) bubble.id = id;
    bubble.innerHTML = text;
    history.appendChild(bubble);
    history.scrollTop = history.scrollHeight;
}

// Support browser SpeechSynthesis loading triggers (some browsers lazy-load voices)
if ('speechSynthesis' in window) {
    window.speechSynthesis.getVoices();
}
