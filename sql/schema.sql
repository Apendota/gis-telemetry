-- PostGIS schema for bridge sensor telemetry
-- Run against the Supabase Postgres database (DATABASE_URL in .env)

CREATE EXTENSION IF NOT EXISTS postgis;

-- Physical sensors mounted on a structure (strain gauges w/ GPS-tagged position)
CREATE TABLE IF NOT EXISTS sensors (
    sensor_id     VARCHAR(50) PRIMARY KEY,
    bridge_name   VARCHAR(100) NOT NULL,
    location      GEOMETRY(Point, 4326) NOT NULL,
    installed_at  DATE NOT NULL DEFAULT CURRENT_DATE
);

CREATE INDEX IF NOT EXISTS idx_sensors_location ON sensors USING GIST (location);

-- Time-series telemetry readings
CREATE TABLE IF NOT EXISTS sensor_readings (
    id            BIGSERIAL PRIMARY KEY,
    sensor_id     VARCHAR(50) NOT NULL REFERENCES sensors(sensor_id) ON DELETE CASCADE,
    recorded_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    location      GEOMETRY(Point, 4326) NOT NULL,
    strain_value  DOUBLE PRECISION NOT NULL,   -- microstrain (µε)
    is_anomaly    BOOLEAN NOT NULL DEFAULT false,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_readings_location   ON sensor_readings USING GIST (location);
CREATE INDEX IF NOT EXISTS idx_readings_sensor_id  ON sensor_readings (sensor_id);
CREATE INDEX IF NOT EXISTS idx_readings_recorded_at ON sensor_readings (recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_readings_anomaly    ON sensor_readings (is_anomaly) WHERE is_anomaly = true;
