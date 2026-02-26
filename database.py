"""
database.py
-----------
Handles all SQLite database operations for the Smart Irrigation System.
Creates tables, inserts sensor readings, and retrieves the latest data.
"""

import sqlite3
import os

# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────
DB_PATH = os.path.join(os.path.dirname(__file__), "irrigation.db")


def get_connection():
    """Return a new SQLite connection with row_factory set."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row          # rows behave like dicts
    return conn


# ─────────────────────────────────────────────
# TABLE INITIALISATION
# ─────────────────────────────────────────────
def init_db():
    """
    Create the required tables if they do not already exist.

    Tables
    ------
    sensor_readings  – stores every payload received from the NodeMCU.
    decision_log     – stores every irrigation decision with reasoning.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # --- Sensor readings table ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sensor_readings (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp         DATETIME DEFAULT CURRENT_TIMESTAMP,
            soil_moisture_raw INTEGER,          -- raw ADC value (0-1023)
            soil_moisture_pct REAL,             -- mapped to 0-100 %
            temperature       REAL,             -- °C from DHT11
            humidity          REAL,             -- % RH from DHT11
            pump_status       TEXT DEFAULT 'OFF'
        )
    """)

    # --- Decision log table ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS decision_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp       DATETIME DEFAULT CURRENT_TIMESTAMP,
            decision        TEXT,               -- 'ON' | 'OFF' | 'MAINTAIN'
            reason          TEXT,               -- plain-English explanation
            rain_predicted  INTEGER,            -- 1 = yes, 0 = no
            weather_desc    TEXT
        )
    """)

    conn.commit()
    conn.close()
    print("[DB] Tables initialised successfully.")


# ─────────────────────────────────────────────
# WRITE OPERATIONS
# ─────────────────────────────────────────────
def insert_sensor_reading(soil_raw: int, soil_pct: float,
                          temperature: float, humidity: float,
                          pump_status: str = "OFF") -> int:
    """
    Persist one sensor reading.

    Parameters
    ----------
    soil_raw     : Raw ADC value from the moisture sensor.
    soil_pct     : Converted moisture percentage.
    temperature  : Temperature in °C.
    humidity     : Relative humidity in %.
    pump_status  : Current relay state ('ON' or 'OFF').

    Returns
    -------
    The row-id of the newly inserted record.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO sensor_readings
            (soil_moisture_raw, soil_moisture_pct, temperature, humidity, pump_status)
        VALUES (?, ?, ?, ?, ?)
    """, (soil_raw, soil_pct, temperature, humidity, pump_status))
    row_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return row_id


def insert_decision_log(decision: str, reason: str,
                        rain_predicted: bool, weather_desc: str):
    """
    Log an irrigation decision alongside its reasoning.

    Parameters
    ----------
    decision       : 'ON', 'OFF', or 'MAINTAIN'.
    reason         : Human-readable reason string.
    rain_predicted : Whether rain was forecast.
    weather_desc   : Short weather description from OpenWeatherMap.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO decision_log (decision, reason, rain_predicted, weather_desc)
        VALUES (?, ?, ?, ?)
    """, (decision, reason, int(rain_predicted), weather_desc))
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────
# READ OPERATIONS
# ─────────────────────────────────────────────
def get_latest_reading() -> dict | None:
    """Return the most recent sensor reading as a dict, or None."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM sensor_readings
        ORDER BY id DESC
        LIMIT 1
    """)
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_recent_readings(limit: int = 20) -> list[dict]:
    """Return the last `limit` sensor readings (newest first)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM sensor_readings
        ORDER BY id DESC
        LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_latest_decision() -> dict | None:
    """Return the most recent decision log entry as a dict, or None."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM decision_log
        ORDER BY id DESC
        LIMIT 1
    """)
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_recent_decisions(limit: int = 10) -> list[dict]:
    """Return the last `limit` decision log entries (newest first)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM decision_log
        ORDER BY id DESC
        LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def clear_history() -> None:
    """Delete all rows from sensor_readings and decision_log tables."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sensor_readings")
    cursor.execute("DELETE FROM decision_log")
    conn.commit()
    conn.close()
