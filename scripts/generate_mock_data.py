"""Simulate bridge strain-gauge telemetry and load it into Supabase/PostGIS.

Models `n` sensors spaced along a bridge deck. Each sensor reports strain
(microstrain, µε) driven by a daily thermal cycle plus load noise, with
occasional injected spikes to represent structural anomalies. GPS location
per reading jitters by a few meters around the sensor's fixed mount point,
mimicking real GPS receiver noise.

Usage:
    python scripts/generate_mock_data.py --hours 24 --interval-minutes 5
"""

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

import numpy as np
import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import execute_values

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]

# Golden Gate Bridge deck, roughly evenly spaced sensor mounts.
BRIDGE_NAME = "Golden Gate Bridge (simulated)"
SENSOR_POSITIONS = [
    ("strain-01", 37.8199, -122.4783),
    ("strain-02", 37.8226, -122.4785),
    ("strain-03", 37.8253, -122.4786),
    ("strain-04", 37.8280, -122.4788),
    ("strain-05", 37.8307, -122.4789),
]

BASELINE_STRAIN_UE = 40.0       # resting microstrain under dead load
THERMAL_AMPLITUDE_UE = 25.0     # daily thermal cycle swing
NOISE_STDDEV_UE = 6.0           # sensor + traffic load noise
ANOMALY_RATE = 0.02             # fraction of readings that spike
ANOMALY_STRAIN_UE = (180.0, 320.0)  # spike magnitude range
GPS_JITTER_DEGREES = 0.00003    # ~3m of GPS noise at this latitude

ANOMALY_STRAIN_THRESHOLD_UE = 150.0  # keep in sync with app/main.py


def upsert_sensors(cur):
    execute_values(
        cur,
        """
        INSERT INTO sensors (sensor_id, bridge_name, location)
        VALUES %s
        ON CONFLICT (sensor_id) DO UPDATE
            SET bridge_name = EXCLUDED.bridge_name,
                location = EXCLUDED.location
        """,
        [
            (sensor_id, BRIDGE_NAME, f"SRID=4326;POINT({lon} {lat})")
            for sensor_id, lat, lon in SENSOR_POSITIONS
        ],
        template="(%s, %s, ST_GeomFromEWKT(%s))",
    )


def simulate_strain(rng: np.random.Generator, hour_of_day: float) -> tuple[float, bool]:
    thermal = THERMAL_AMPLITUDE_UE * np.sin(2 * np.pi * (hour_of_day - 6) / 24)
    noise = rng.normal(0, NOISE_STDDEV_UE)
    value = BASELINE_STRAIN_UE + thermal + noise

    is_injected_anomaly = rng.random() < ANOMALY_RATE
    if is_injected_anomaly:
        spike = rng.uniform(*ANOMALY_STRAIN_UE)
        value += spike if rng.random() < 0.5 else -spike

    is_anomaly = is_injected_anomaly or abs(value) > ANOMALY_STRAIN_THRESHOLD_UE
    return value, is_anomaly


def generate_readings(hours: int, interval_minutes: int, seed: int | None):
    rng = np.random.default_rng(seed)
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=hours)
    steps = int(hours * 60 / interval_minutes)

    rows = []
    for step in range(steps):
        ts = start + timedelta(minutes=step * interval_minutes)
        hour_of_day = ts.hour + ts.minute / 60

        for sensor_id, lat, lon in SENSOR_POSITIONS:
            strain_value, is_anomaly = simulate_strain(rng, hour_of_day)
            jittered_lat = lat + rng.normal(0, GPS_JITTER_DEGREES)
            jittered_lon = lon + rng.normal(0, GPS_JITTER_DEGREES)

            rows.append(
                (
                    sensor_id,
                    ts,
                    f"SRID=4326;POINT({jittered_lon} {jittered_lat})",
                    round(float(strain_value), 3),
                    bool(is_anomaly),
                )
            )
    return rows


def insert_readings(cur, rows):
    execute_values(
        cur,
        """
        INSERT INTO sensor_readings
            (sensor_id, recorded_at, location, strain_value, is_anomaly)
        VALUES %s
        """,
        rows,
        template="(%s, %s, ST_GeomFromEWKT(%s), %s, %s)",
        page_size=500,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hours", type=int, default=24, help="Hours of history to simulate")
    parser.add_argument("--interval-minutes", type=int, default=5, help="Sampling interval")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")
    args = parser.parse_args()

    rows = generate_readings(args.hours, args.interval_minutes, args.seed)
    anomaly_count = sum(1 for r in rows if r[4])

    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            upsert_sensors(cur)
            insert_readings(cur, rows)
        conn.commit()
    finally:
        conn.close()

    print(
        f"Inserted {len(rows)} readings across {len(SENSOR_POSITIONS)} sensors "
        f"({anomaly_count} flagged anomalies)."
    )


if __name__ == "__main__":
    main()
