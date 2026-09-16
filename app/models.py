from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


class SensorCreate(BaseModel):
    sensor_id: str
    bridge_name: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class SensorOut(BaseModel):
    sensor_id: str
    bridge_name: str
    latitude: float
    longitude: float
    installed_at: date


class ReadingCreate(BaseModel):
    sensor_id: str
    strain_value: float
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    recorded_at: Optional[datetime] = None
    is_anomaly: Optional[bool] = None


class ReadingOut(BaseModel):
    id: int
    sensor_id: str
    recorded_at: datetime
    latitude: float
    longitude: float
    strain_value: float
    is_anomaly: bool
