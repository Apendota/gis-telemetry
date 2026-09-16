import json
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles

from app.database import get_cursor
from app.models import ReadingCreate, ReadingOut, SensorCreate, SensorOut

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

# Threshold beyond which a strain reading is auto-flagged when the client
# doesn't explicitly set is_anomaly (typical yield strain for structural steel
# monitoring is ~1000-2000 µε; 150 µε is a conservative "worth reviewing" line).
ANOMALY_STRAIN_THRESHOLD_UE = 150.0

app = FastAPI(title="GIS/BIM Telemetry API")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/sensors", response_model=SensorOut, status_code=201)
def create_sensor(sensor: SensorCreate):
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO sensors (sensor_id, bridge_name, location)
            VALUES (%s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
            ON CONFLICT (sensor_id) DO UPDATE
                SET bridge_name = EXCLUDED.bridge_name,
                    location = EXCLUDED.location
            RETURNING sensor_id, bridge_name, installed_at,
                      ST_Y(location) AS latitude, ST_X(location) AS longitude
            """,
            (sensor.sensor_id, sensor.bridge_name, sensor.longitude, sensor.latitude),
        )
        return cur.fetchone()


@app.get("/sensors", response_model=list[SensorOut])
def list_sensors():
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT sensor_id, bridge_name, installed_at,
                   ST_Y(location) AS latitude, ST_X(location) AS longitude
            FROM sensors
            ORDER BY sensor_id
            """
        )
        return cur.fetchall()


@app.post("/readings", response_model=ReadingOut, status_code=201)
def create_reading(reading: ReadingCreate):
    is_anomaly = reading.is_anomaly
    if is_anomaly is None:
        is_anomaly = abs(reading.strain_value) > ANOMALY_STRAIN_THRESHOLD_UE

    with get_cursor() as cur:
        cur.execute("SELECT 1 FROM sensors WHERE sensor_id = %s", (reading.sensor_id,))
        if cur.fetchone() is None:
            raise HTTPException(status_code=404, detail=f"Unknown sensor_id '{reading.sensor_id}'")

        cur.execute(
            """
            INSERT INTO sensor_readings
                (sensor_id, recorded_at, location, strain_value, is_anomaly)
            VALUES
                (%s, COALESCE(%s, now()), ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s, %s)
            RETURNING id, sensor_id, recorded_at, strain_value, is_anomaly,
                      ST_Y(location) AS latitude, ST_X(location) AS longitude
            """,
            (
                reading.sensor_id,
                reading.recorded_at,
                reading.longitude,
                reading.latitude,
                reading.strain_value,
                is_anomaly,
            ),
        )
        return cur.fetchone()


@app.get("/readings", response_model=list[ReadingOut])
def list_readings(
    sensor_id: Optional[str] = None,
    since: Optional[str] = Query(None, description="ISO timestamp; only readings at/after this time"),
    anomalies_only: bool = False,
    bbox: Optional[str] = Query(None, description="minLon,minLat,maxLon,maxLat"),
    limit: int = Query(100, ge=1, le=1000),
):
    where = []
    params: list = []

    if sensor_id:
        where.append("sensor_id = %s")
        params.append(sensor_id)
    if since:
        where.append("recorded_at >= %s")
        params.append(since)
    if anomalies_only:
        where.append("is_anomaly = true")
    if bbox:
        try:
            min_lon, min_lat, max_lon, max_lat = (float(v) for v in bbox.split(","))
        except ValueError:
            raise HTTPException(status_code=400, detail="bbox must be 'minLon,minLat,maxLon,maxLat'")
        where.append("ST_Intersects(location, ST_MakeEnvelope(%s, %s, %s, %s, 4326))")
        params.extend([min_lon, min_lat, max_lon, max_lat])

    where_clause = f"WHERE {' AND '.join(where)}" if where else ""
    params.append(limit)

    with get_cursor() as cur:
        cur.execute(
            f"""
            SELECT id, sensor_id, recorded_at, strain_value, is_anomaly,
                   ST_Y(location) AS latitude, ST_X(location) AS longitude
            FROM sensor_readings
            {where_clause}
            ORDER BY recorded_at DESC
            LIMIT %s
            """,
            params,
        )
        return cur.fetchall()


@app.get("/readings/geojson")
def list_readings_geojson(
    sensor_id: Optional[str] = None,
    anomalies_only: bool = False,
    limit: int = Query(500, ge=1, le=5000),
):
    where = []
    params: list = []

    if sensor_id:
        where.append("sensor_id = %s")
        params.append(sensor_id)
    if anomalies_only:
        where.append("is_anomaly = true")

    where_clause = f"WHERE {' AND '.join(where)}" if where else ""
    params.append(limit)

    with get_cursor() as cur:
        cur.execute(
            f"""
            SELECT id, sensor_id, recorded_at, strain_value, is_anomaly,
                   ST_AsGeoJSON(location) AS geometry
            FROM sensor_readings
            {where_clause}
            ORDER BY recorded_at DESC
            LIMIT %s
            """,
            params,
        )
        rows = cur.fetchall()

    features = [
        {
            "type": "Feature",
            "geometry": json.loads(row["geometry"]),
            "properties": {
                "id": row["id"],
                "sensor_id": row["sensor_id"],
                "recorded_at": row["recorded_at"].isoformat(),
                "strain_value": row["strain_value"],
                "is_anomaly": row["is_anomaly"],
            },
        }
        for row in rows
    ]
    return {"type": "FeatureCollection", "features": features}


# Mounted last so it never shadows the API routes above (Starlette matches
# routes in registration order, and a root mount would otherwise catch
# everything, including /readings and /sensors, first).
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
