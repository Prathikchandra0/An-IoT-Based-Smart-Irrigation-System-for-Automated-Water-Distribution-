# IoT-Based Smart Irrigation System

Flask + SQLite backend with a NodeMCU firmware client for automated irrigation decisions.

## 1) Prerequisites

- Python 3.10+
- pip
- NodeMCU (ESP8266) + moisture sensor + DHT11 + relay (for hardware mode)

## 2) Project setup

From the project root:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 3) Environment setup (.env)

Create a `.env` file in the project root (copy from `.env.example`):

```env
OPENWEATHER_API_KEY=your_real_openweathermap_api_key
CITY_NAME=Hyderabad
COUNTRY_CODE=IN
```

Notes:
- If `OPENWEATHER_API_KEY` is empty or left as placeholder text, weather calls are skipped safely.
- You can still run and test the app without a weather key.

## 4) Run the backend

```bash
python app.py
```

Server starts at:
- `http://127.0.0.1:5000`
- `http://0.0.0.0:5000`

Dashboard:
- `http://127.0.0.1:5000/`

## 5) API quick check

### POST /sensor-data
Send JSON:

```json
{
  "soil_moisture_raw": 650,
  "temperature": 28.5,
  "humidity": 65.0
}
```

### GET /dashboard-data
Returns latest reading, latest decision, recent readings, and weather state.

### POST /clear-history
Clears sensor and decision tables in SQLite.

## 6) NodeMCU firmware setup (Physical Hardware)

If you are using real hardware, edit values in `arduino_code.ino` before flashing:
- `WIFI_SSID`
- `WIFI_PASSWORD`
- `SERVER_URL` (point to your Flask server IP, e.g. `http://192.168.x.x:5000/sensor-data`)

## 7) Run Software Simulator (Demo Mode)

If you don't have physical sensors and want to test or demo the project, there is a built-in software simulator that acts exactly like the NodeMCU hardware.

While `app.py` is running, open a new terminal in the project root and run:
```bash
python simulator.py
```
This script will post simulated sensor data to the server every 10 seconds. It automatically drops soil moisture when the pump turns "ON" (simulating watering) and slowly raises moisture when "OFF" (simulating drying).

## 8) Database file

SQLite DB is auto-created as `irrigation.db` in the project root when `app.py` starts.
