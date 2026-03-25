"""
app.py
------
Flask backend for the IoT-Based Smart Irrigation System.

Endpoints
---------
POST /sensor-data      – receives JSON payload from NodeMCU, stores it,
                          runs decision logic, and returns pump command.
GET  /dashboard-data   – returns the latest reading + decision as JSON.
GET  /                 – serves the HTML dashboard.

Decision Logic
--------------
  IF soil_moisture_pct < MOISTURE_THRESHOLD AND no rain predicted
      → Pump ON
  IF rain predicted (or heavy rain)
      → Pump OFF
  ELSE
      → Maintain current pump state
"""

import logging
import os
from datetime import datetime

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

import database as db

# Load secrets from .env file
load_dotenv()

# ─────────────────────────────────────────────
# CONFIGURATION  (values loaded from .env)
# ─────────────────────────────────────────────
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "")
CITY_NAME           = os.getenv("CITY_NAME", "Hyderabad")
COUNTRY_CODE        = os.getenv("COUNTRY_CODE", "IN")

# Moisture thresholds (percentage)
MOISTURE_THRESHOLD          = 40    # below this → consider irrigating
MOISTURE_CRITICAL_THRESHOLD = 20    # below this → SMS alert

# Soil-moisture sensor calibration (raw ADC values from NodeMCU)
MOISTURE_AIR_VALUE   = 1023   # sensor reading in dry air (0% moisture)
MOISTURE_WATER_VALUE = 300    # sensor reading submerged in water (100% moisture)

# Rain-prediction keywords from OpenWeatherMap weather descriptions
RAIN_KEYWORDS        = ["rain", "drizzle", "thunderstorm", "shower"]
HEAVY_RAIN_KEYWORDS  = ["heavy rain", "thunderstorm", "extreme"]

# ─────────────────────────────────────────────
# APP SETUP
# ─────────────────────────────────────────────
app = Flask(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Initialise database tables on startup
db.init_db()

# In-memory pump state (acts as the "current state" memory)
_current_pump_status = "OFF"


# ─────────────────────────────────────────────
# HELPER: RAW → PERCENTAGE CONVERSION
# ─────────────────────────────────────────────
def raw_to_percent(raw_value: int) -> float:
    """
    Map the raw ADC reading from the capacitive/resistive moisture sensor
    to a 0–100 % value using the calibration constants above.

    A higher raw ADC value typically means DRIER soil (less capacitance).
    """
    pct = (MOISTURE_AIR_VALUE - raw_value) / (MOISTURE_AIR_VALUE - MOISTURE_WATER_VALUE) * 100
    return round(max(0.0, min(100.0, pct)), 2)   # clamp to [0, 100]


# ─────────────────────────────────────────────
# HELPER: WEATHER FETCH
# ─────────────────────────────────────────────
def fetch_weather() -> dict:
    """
    Call the OpenWeatherMap current-weather API.

    Returns a dict with keys:
        description  – short weather text (e.g. "light rain")
        rain_predicted  – bool
        heavy_rain      – bool
        temp_c          – float (°C)
        humidity        – float (%)
        error           – str or None
    """
    result = {
        "description"   : "unavailable",
        "rain_predicted": False,
        "heavy_rain"    : False,
        "temp_c"        : None,
        "humidity"      : None,
        "error"         : None,
    }

    api_key = (OPENWEATHER_API_KEY or "").strip()
    if not api_key or "your_openweathermap_api_key" in api_key.lower():
        result["error"] = "API key not configured - weather check skipped."
        logger.warning(result["error"])
        return result

    url = (
        f"https://api.openweathermap.org/data/2.5/weather"
        f"?q={CITY_NAME},{COUNTRY_CODE}&appid={api_key}&units=metric"
    )

    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()

        description = data["weather"][0]["description"].lower()
        result["description"] = description
        result["temp_c"]      = data["main"]["temp"]
        result["humidity"]    = data["main"]["humidity"]

        result["rain_predicted"] = any(kw in description for kw in RAIN_KEYWORDS)
        result["heavy_rain"]     = any(kw in description for kw in HEAVY_RAIN_KEYWORDS)

        logger.info("Weather fetched: %s  |  temp=%.1f°C  |  humidity=%.0f%%",
                    description, result["temp_c"], result["humidity"])

    except requests.exceptions.RequestException as exc:
        result["error"] = str(exc)
        logger.error("Weather API error: %s", exc)

    return result


# ─────────────────────────────────────────────
# HELPER: DECISION ENGINE
# ─────────────────────────────────────────────
def make_irrigation_decision(soil_pct: float, weather: dict) -> tuple[str, str]:
    """
    Core decision logic.

    Parameters
    ----------
    soil_pct : Current soil-moisture percentage.
    weather  : Dict returned by fetch_weather().

    Returns
    -------
    (decision, reason)  where decision ∈ {'ON', 'OFF', 'MAINTAIN'}
    """
    global _current_pump_status

    rain_coming  = weather["rain_predicted"]
    heavy_rain   = weather["heavy_rain"]
    weather_desc = weather["description"]

    # Rule 1 – heavy rain predicted → always turn off to avoid waterlogging
    if heavy_rain:
        decision = "OFF"
        reason = (f"Heavy rain predicted ({weather_desc}). "
                  "Pump suspended to prevent waterlogging.")
        _alert_heavy_rain(weather_desc)

    # Rule 2 – dry soil AND no rain → irrigate
    elif soil_pct < MOISTURE_THRESHOLD and not rain_coming:
        decision = "ON"
        reason = (f"Soil moisture {soil_pct:.1f}% < threshold {MOISTURE_THRESHOLD}% "
                  f"and no rain predicted. Activating pump.")

    # Rule 3 – rain predicted → hold off
    elif rain_coming:
        decision = "OFF"
        reason = (f"Rain predicted ({weather_desc}). "
                  "Pump off to conserve water.")

    # Rule 4 – soil is sufficiently moist → maintain / turn off
    elif soil_pct >= MOISTURE_THRESHOLD:
        decision = "OFF"
        reason = (f"Soil moisture {soil_pct:.1f}% ≥ threshold {MOISTURE_THRESHOLD}%. "
                  "No irrigation needed.")

    else:
        decision = "MAINTAIN"
        reason = "Conditions unchanged. Maintaining current pump state."

    _current_pump_status = decision if decision != "MAINTAIN" else _current_pump_status
    return decision, reason


# ─────────────────────────────────────────────
# ALERT SIMULATORS  (replace with real SMS lib)
# ─────────────────────────────────────────────
def _alert_critical_moisture(soil_pct: float):
    """Simulate an SMS alert when soil moisture drops critically low."""
    msg = (
        f"\n{'='*60}\n"
        f"[SMS ALERT] CRITICAL SOIL MOISTURE!\n"
        f"  Current moisture: {soil_pct:.1f}%\n"
        f"  Threshold: {MOISTURE_CRITICAL_THRESHOLD}%\n"
        f"  Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"  Action: Pump has been turned ON automatically.\n"
        f"{'='*60}\n"
    )
    print(msg)
    logger.warning("ALERT: Critical soil moisture at %.1f%%", soil_pct)


def _alert_heavy_rain(weather_desc: str):
    """Simulate a notification when heavy rain is forecast."""
    msg = (
        f"\n{'='*60}\n"
        f"[SMS ALERT] HEAVY RAIN PREDICTED!\n"
        f"  Forecast: {weather_desc}\n"
        f"  Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"  Action: Irrigation suspended to prevent waterlogging.\n"
        f"{'='*60}\n"
    )
    print(msg)
    logger.warning("ALERT: Heavy rain predicted — irrigation suspended.")


# ─────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────
@app.route("/sensor-data", methods=["POST"])
def receive_sensor_data():
    """
    POST /sensor-data
    -----------------
    Expected JSON body from NodeMCU:
        {
            "soil_moisture_raw": 650,
            "temperature": 28.5,
            "humidity": 65.0
        }

    Response JSON:
        {
            "pump_command": "ON" | "OFF",
            "reason": "...",
            "moisture_pct": 35.2
        }
    """
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "Invalid or missing JSON payload"}), 400

    # --- Parse & validate ---
    try:
        soil_raw    = int(data["soil_moisture_raw"])
        temperature = float(data["temperature"])
        humidity    = float(data["humidity"])
    except (KeyError, ValueError) as exc:
        return jsonify({"error": f"Missing/invalid field: {exc}"}), 422

    # --- Calibrate moisture ---
    soil_pct = raw_to_percent(soil_raw)

    # --- Check for critical moisture BEFORE running main logic ---
    if soil_pct < MOISTURE_CRITICAL_THRESHOLD:
        _alert_critical_moisture(soil_pct)

    # --- Fetch weather & decide ---
    weather  = fetch_weather()
    decision, reason = make_irrigation_decision(soil_pct, weather)

    pump_cmd = decision if decision != "MAINTAIN" else _current_pump_status

    # --- Persist to DB ---
    db.insert_sensor_reading(soil_raw, soil_pct, temperature, humidity, pump_cmd)
    db.insert_decision_log(decision, reason,
                           weather["rain_predicted"], weather["description"])

    logger.info(
        "Sensor data received | moisture=%.1f%% | temp=%.1f°C | humidity=%.0f%% "
        "| decision=%s | pump=%s",
        soil_pct, temperature, humidity, decision, pump_cmd
    )

    return jsonify({
        "pump_command" : pump_cmd,
        "reason"       : reason,
        "moisture_pct" : soil_pct,
    }), 200


@app.route("/dashboard-data", methods=["GET"])
def dashboard_data():
    """
    GET /dashboard-data
    -------------------
    Returns the latest sensor reading, decision, and live weather as JSON.
    Used by the dashboard's auto-refresh JavaScript.
    """
    latest_reading  = db.get_latest_reading()
    latest_decision = db.get_latest_decision()
    recent_readings = db.get_recent_readings(limit=10)
    weather         = fetch_weather()

    return jsonify({
        "latest_reading" : latest_reading,
        "latest_decision": latest_decision,
        "recent_readings": recent_readings,
        "weather"        : weather,
    }), 200


@app.route("/clear-history", methods=["POST"])
def clear_history():
    """Delete all sensor readings and decision log entries."""
    db.clear_history()
    logger.info("History cleared via dashboard.")
    return jsonify({"status": "cleared"}), 200


@app.route("/", methods=["GET"])
def index():
    """Serve the HTML dashboard."""
    return render_template("dashboard.html")


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────
if __name__ == "__main__":
    logger.info("Starting Smart Irrigation Flask server on http://0.0.0.0:5000")
    app.run(host="0.0.0.0", port=5000, debug=True)
