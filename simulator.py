import time
import random
import requests
import json
import threading

SERVER_URL = "http://127.0.0.1:5000/sensor-data"

# Initial simulated environment states
current_temp = 28.0
current_humidity = 50.0

# In app.py: 
#   MOISTURE_AIR_VALUE = 1023 (dry/0%) 
#   MOISTURE_WATER_VALUE = 300 (wet/100%)
# Let's start around ~30% moisture (raw ~800)
soil_moisture_raw = 800.0

def simulate_environment():
    global current_temp, current_humidity, soil_moisture_raw
    while True:
        # Prepare the data payload, replicating arduino JSON shape
        payload = {
            "soil_moisture_raw": int(soil_moisture_raw),
            "temperature": round(current_temp, 1),
            "humidity": round(current_humidity, 1)
        }
        
        try:
            print(f"\n[SIMULATOR] ---> POSTing payload: {payload}")
            response = requests.post(SERVER_URL, json=payload, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                pump_cmd = data.get("pump_command")
                moist_pct = data.get("moisture_pct")
                reason = data.get("reason", "")
                
                print(f"[SIMULATOR] <--- Server responded | Pump: {pump_cmd} | Moisture: {moist_pct}%")
                print(f"[SIMULATOR]      Reason: {reason}")
                
                # Feedback loop logic to adjust moisture
                if pump_cmd == "ON":
                    print("  => Pump is ON -> Simulating watering...")
                    # Moisture goes towards 300 rapidly (wetter)
                    soil_moisture_raw = max(300, soil_moisture_raw - 150)
                else:
                    print("  => Pump is OFF -> Soil naturally drying over time...")
                    # Moisture drifts back towards 1023 (drier)
                    soil_moisture_raw = min(1023, soil_moisture_raw + 20)
                    
            else:
                print(f"[SIMULATOR] Error response: {response.text}")
                
        except Exception as e:
            print(f"[SIMULATOR] Could not reach server at {SERVER_URL}: {e}")
            
        # Add random minor fluctuations to temp/humidity
        current_temp += random.uniform(-0.5, 0.5)
        current_humidity += random.uniform(-2.0, 2.0)
        current_humidity = max(0, min(100, current_humidity))
        
        # Wait 10 seconds as defined in the hardware codebase
        time.sleep(10)

if __name__ == "__main__":
    print("=" * 60)
    print(" IoT Smart Irrigation Simulator ".center(60, "="))
    print("=" * 60)
    print("This script simulates an ESP8266 sending data every 10 secs.")
    print("Requirements before running:")
    print("  1. Flask backend (app.py) must be running on port 5000.")
    print("  2. This script creates an automated feedback loop:")
    print("     - If the pump turns ON, the simulated soil gets wetter.")
    print("     - If the pump is OFF, the soil naturally dries out.")
    print("=" * 60)
    
    try:
        simulate_environment()
    except KeyboardInterrupt:
        print("\nSimulator stopped cleanly.")
