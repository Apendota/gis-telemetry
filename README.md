# GIS/BIM Telemetry Pipeline

A small telemetry pipeline that simulates bridge strain-gauge sensors,
stores GPS-tagged readings in PostGIS, and serves them through a FastAPI
backend to a Leaflet map.

**Stack:** FastAPI · Supabase (Postgres + PostGIS) · GeoPandas · Leaflet.js

## How it fits together

- `sql/schema.sql` — PostGIS schema: `sensors` (fixed GPS mount points) and
  `sensor_readings` (time-series strain readings with GEOMETRY location and
  an anomaly flag).
- `app/` — FastAPI backend. Ingests and queries readings, auto-flags
  anomalies over a strain threshold, and serves GeoJSON for the map.
- `scripts/generate_mock_data.py` — simulates realistic sensor readings
  (daily thermal cycle, load noise, GPS jitter, occasional anomaly spikes).
- `static/index.html` — Leaflet map that consumes `/readings/geojson`.

## Local setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file with your Supabase connection string:

```
DATABASE_URL=postgresql://...
```

Apply the schema, then generate mock data:

```bash
python -c "
import os, psycopg2
from dotenv import load_dotenv
load_dotenv()
conn = psycopg2.connect(os.environ['DATABASE_URL'])
with conn.cursor() as cur, open('sql/schema.sql') as f:
    cur.execute(f.read())
conn.commit()
"
python scripts/generate_mock_data.py --hours 24 --interval-minutes 5
```

Run the app:

```bash
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000` for the map.

## API

| Method | Path                | Description                                   |
|--------|---------------------|------------------------------------------------|
| GET    | `/health`           | Liveness check                                  |
| POST   | `/sensors`           | Register/update a sensor                        |
| GET    | `/sensors`           | List sensors                                    |
| POST   | `/readings`          | Ingest a reading (auto-flags anomalies)         |
| GET    | `/readings`          | Query readings (`sensor_id`, `since`, `anomalies_only`, `bbox`, `limit`) |
| GET    | `/readings/geojson`  | Readings as a GeoJSON FeatureCollection         |

## Deployment (Render)

`render.yaml` defines a single web service. In the Render dashboard:

1. New → Blueprint → point at this repo.
2. Set the `DATABASE_URL` env var to your Supabase connection string
   (kept out of the repo/blueprint on purpose).
3. Deploy — Render runs `pip install -r requirements.txt` then
   `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.

Make sure the schema (`sql/schema.sql`) has already been applied to the
target database before the first deploy.
