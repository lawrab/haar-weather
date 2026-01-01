"""SQLAlchemy database models for Haar weather system."""

import json
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.types import TypeDecorator

Base = declarative_base()


class JSONType(TypeDecorator):
    """Custom type for storing JSON data in SQLite."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Optional[Dict], dialect) -> Optional[str]:
        """Convert dict to JSON string for storage."""
        if value is not None:
            return json.dumps(value)
        return value

    def process_result_value(self, value: Optional[str], dialect) -> Optional[Dict]:
        """Convert JSON string back to dict."""
        if value is not None:
            return json.loads(value)
        return value


class Location(Base):
    """Location model for target, PWS, Met Office stations, and grid points."""

    __tablename__ = "locations"

    id = Column(String, primary_key=True)
    name = Column(String)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    elevation_m = Column(Float)
    location_type = Column(String, nullable=False)  # 'target', 'pws', 'metoffice', 'grid'
    source = Column(String)  # Which network/source
    station_metadata = Column(JSONType)  # Station-specific info
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    observations = relationship("Observation", back_populates="location", cascade="all, delete-orphan")
    forecasts = relationship("Forecast", back_populates="location", cascade="all, delete-orphan")
    terrain_features = relationship("TerrainFeature", back_populates="location", uselist=False, cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Location(id='{self.id}', name='{self.name}', type='{self.location_type}')>"


class Observation(Base):
    """Weather observation model."""

    __tablename__ = "observations"
    __table_args__ = (
        UniqueConstraint("location_id", "observed_at", "source", name="uix_observation"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    location_id = Column(String, ForeignKey("locations.id"), nullable=False)
    observed_at = Column(DateTime, nullable=False)
    source = Column(String, nullable=False)

    # Weather variables
    temperature_c = Column(Float)
    humidity_pct = Column(Float)
    pressure_hpa = Column(Float)
    wind_speed_ms = Column(Float)
    wind_direction_deg = Column(Float)
    wind_gust_ms = Column(Float)
    precipitation_mm = Column(Float)
    cloud_cover_pct = Column(Float)
    visibility_m = Column(Float)
    weather_code = Column(Integer)

    raw_data = Column(JSONType)  # Original API response
    quality_flag = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    location = relationship("Location", back_populates="observations")

    def __repr__(self) -> str:
        return f"<Observation(location='{self.location_id}', time='{self.observed_at}', temp={self.temperature_c}°C)>"


class Forecast(Base):
    """Forecast model for various sources."""

    __tablename__ = "forecasts"
    __table_args__ = (
        UniqueConstraint("location_id", "source", "issued_at", "valid_at", name="uix_forecast"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    location_id = Column(String, ForeignKey("locations.id"), nullable=False)
    source = Column(String, nullable=False)  # 'openmeteo', 'metoffice', 'haar_v1', etc.
    issued_at = Column(DateTime, nullable=False)
    valid_at = Column(DateTime, nullable=False)
    lead_time_hours = Column(Integer, nullable=False)

    # Weather variables
    temperature_c = Column(Float)
    humidity_pct = Column(Float)
    pressure_hpa = Column(Float)
    wind_speed_ms = Column(Float)
    wind_direction_deg = Column(Float)
    precipitation_mm = Column(Float)
    precipitation_probability_pct = Column(Float)
    cloud_cover_pct = Column(Float)
    weather_code = Column(Integer)

    raw_data = Column(JSONType)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    location = relationship("Location", back_populates="forecasts")

    def __repr__(self) -> str:
        return f"<Forecast(location='{self.location_id}', source='{self.source}', valid_at='{self.valid_at}')>"


class TerrainFeature(Base):
    """Terrain features computed once per location."""

    __tablename__ = "terrain_features"

    location_id = Column(String, ForeignKey("locations.id"), primary_key=True)
    elevation_m = Column(Float)
    slope_deg = Column(Float)
    aspect_deg = Column(Float)
    distance_to_coast_km = Column(Float)
    distance_to_highland_km = Column(Float)
    terrain_roughness = Column(Float)
    is_valley = Column(Integer)
    is_hilltop = Column(Integer)
    computed_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    location = relationship("Location", back_populates="terrain_features")

    def __repr__(self) -> str:
        return f"<TerrainFeature(location='{self.location_id}', elevation={self.elevation_m}m)>"


class ModelRun(Base):
    """Model training run metadata."""

    __tablename__ = "model_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_name = Column(String, nullable=False)
    model_version = Column(String, nullable=False)
    trained_at = Column(DateTime, default=datetime.utcnow)
    training_start_date = Column(DateTime)
    training_end_date = Column(DateTime)
    features = Column(JSONType)  # Feature list
    hyperparameters = Column(JSONType)
    metrics = Column(JSONType)  # MAE, RMSE, skill scores
    model_path = Column(Text)  # Path to serialized model
    notes = Column(Text)

    def __repr__(self) -> str:
        return f"<ModelRun(name='{self.model_name}', version='{self.model_version}', trained='{self.trained_at}')>"


class CollectionLog(Base):
    """Collection job execution logs."""

    __tablename__ = "collection_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    collector = Column(String, nullable=False)
    started_at = Column(DateTime, nullable=False)
    finished_at = Column(DateTime)
    status = Column(String)  # 'success', 'partial', 'failed'
    records_collected = Column(Integer)
    error_message = Column(Text)

    def __repr__(self) -> str:
        return f"<CollectionLog(collector='{self.collector}', status='{self.status}', records={self.records_collected})>"
