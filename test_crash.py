import subprocess
import time
import requests
import sys

print("Starting server...")
proc = subprocess.Popen([sys.executable, "app.py"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

time.sleep(3) # wait for server to start

try:
    print("Sending POST request...")
    response = requests.post("http://127.0.0.1:5000/sensor-data", json={
        "soil_moisture_raw": 800,
        "temperature": 28.0,
        "humidity": 50.0
    })
    print("Response Code:", response.status_code)
    print("Response Body:", response.text)
except Exception as e:
    print("Request failed:", e)

time.sleep(2) # wait for any crash output
proc.kill()

print("\n--- SERVER OUTPUT ---")
print(proc.stdout.read())
print("---------------------")
