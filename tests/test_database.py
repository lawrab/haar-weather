"""Tests for database operations."""

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import inspect

from haar.config import DatabaseConfig
from haar.storage import (
    CollectionLog,
    Forecast,
    Location,
    ModelRun,
    Observation,
    TerrainFeature,
    get_engine,
    get_session,
    init_db,
    reset_db_connection,
)


@pytest.fixture
def test_db_config(tmp_path):
    """Create test database configuration."""
    db_path = tmp_path / "test.db"
    return DatabaseConfig(path=db_path)


@pytest.fixture(autouse=True)
def reset_db():
    """Reset database connection before each test."""
    reset_db_connection()
    yield
    reset_db_connection()


def test_init_db_creates_tables(test_db_config):
    """Test that init_db creates all tables."""
    init_db(test_db_config)

    # Check that database file was created
    assert test_db_config.path.exists()

    # Check that all tables exist
    engine = get_engine(test_db_config)
    inspector = inspect(engine)
    tables = inspector.get_table_names()

    expected_tables = {
        "locations",
        "observations",
        "forecasts",
        "terrain_features",
        "model_runs",
        "collection_logs",
    }
    assert set(tables) == expected_tables


def test_init_db_creates_indexes(test_db_config):
    """Test that indexes are created."""
    init_db(test_db_config)

    engine = get_engine(test_db_config)
    inspector = inspect(engine)

    # Check observations indexes
    obs_indexes = inspector.get_indexes("observations")
    obs_index_names = {idx["name"] for idx in obs_indexes}
    assert "idx_observations_location_time" in obs_index_names
    assert "idx_observations_time" in obs_index_names

    # Check forecasts indexes
    fcst_indexes = inspector.get_indexes("forecasts")
    fcst_index_names = {idx["name"] for idx in fcst_indexes}
    assert "idx_forecasts_location_valid" in fcst_index_names
    assert "idx_forecasts_source_issued" in fcst_index_names


def test_init_db_raises_if_exists(test_db_config):
    """Test that init_db raises error if database already exists."""
    init_db(test_db_config)

    with pytest.raises(RuntimeError, match="Database already exists"):
        init_db(test_db_config, force=False)


def test_init_db_force_recreates(test_db_config):
    """Test that force=True recreates the database."""
    init_db(test_db_config)

    # Add some data
    with get_session(test_db_config) as session:
        location = Location(
            id="test_loc",
            name="Test",
            latitude=55.0,
            longitude=-3.0,
            location_type="target",
        )
        session.add(location)

    # Verify data exists
    with get_session(test_db_config) as session:
        assert session.query(Location).count() == 1

    # Force recreate
    init_db(test_db_config, force=True)

    # Data should be gone
    with get_session(test_db_config) as session:
        assert session.query(Location).count() == 0


def test_location_crud(test_db_config):
    """Test Location create, read, update, delete."""
    init_db(test_db_config)

    # Create
    with get_session(test_db_config) as session:
        location = Location(
            id="edinburgh",
            name="Edinburgh",
            latitude=55.9533,
            longitude=-3.1883,
            elevation_m=47,
            location_type="target",
            station_metadata={"timezone": "Europe/London"},
        )
        session.add(location)

    # Read
    with get_session(test_db_config) as session:
        loc = session.query(Location).filter_by(id="edinburgh").first()
        assert loc is not None
        assert loc.name == "Edinburgh"
        assert loc.latitude == 55.9533
        assert loc.station_metadata["timezone"] == "Europe/London"

    # Update
    with get_session(test_db_config) as session:
        loc = session.query(Location).filter_by(id="edinburgh").first()
        loc.name = "Edinburgh City"
        session.commit()

    # Verify update
    with get_session(test_db_config) as session:
        loc = session.query(Location).filter_by(id="edinburgh").first()
        assert loc.name == "Edinburgh City"

    # Delete
    with get_session(test_db_config) as session:
        loc = session.query(Location).filter_by(id="edinburgh").first()
        session.delete(loc)

    # Verify deletion
    with get_session(test_db_config) as session:
        assert session.query(Location).count() == 0


def test_observation_crud(test_db_config):
    """Test Observation CRUD operations."""
    init_db(test_db_config)

    # Create location first
    with get_session(test_db_config) as session:
        location = Location(
            id="test_loc",
            name="Test",
            latitude=55.0,
            longitude=-3.0,
            location_type="pws",
        )
        session.add(location)

    # Create observation
    now = datetime.utcnow()
    with get_session(test_db_config) as session:
        obs = Observation(
            location_id="test_loc",
            observed_at=now,
            source="test",
            temperature_c=15.5,
            humidity_pct=75.0,
            pressure_hpa=1013.25,
            wind_speed_ms=3.5,
            precipitation_mm=0.0,
            raw_data={"test": "data"},
        )
        session.add(obs)

    # Read
    with get_session(test_db_config) as session:
        obs = session.query(Observation).first()
        assert obs.temperature_c == 15.5
        assert obs.humidity_pct == 75.0
        assert obs.raw_data["test"] == "data"


def test_observation_unique_constraint(test_db_config):
    """Test that duplicate observations are prevented."""
    init_db(test_db_config)

    with get_session(test_db_config) as session:
        location = Location(
            id="test_loc",
            name="Test",
            latitude=55.0,
            longitude=-3.0,
            location_type="pws",
        )
        session.add(location)

    now = datetime.utcnow()
    with get_session(test_db_config) as session:
        obs1 = Observation(
            location_id="test_loc",
            observed_at=now,
            source="test",
            temperature_c=15.5,
        )
        session.add(obs1)

    # Try to add duplicate
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        with get_session(test_db_config) as session:
            obs2 = Observation(
                location_id="test_loc",
                observed_at=now,
                source="test",
                temperature_c=16.0,
            )
            session.add(obs2)


def test_forecast_crud(test_db_config):
    """Test Forecast CRUD operations."""
    init_db(test_db_config)

    with get_session(test_db_config) as session:
        location = Location(
            id="test_loc",
            name="Test",
            latitude=55.0,
            longitude=-3.0,
            location_type="target",
        )
        session.add(location)

    now = datetime.utcnow()
    valid_time = now + timedelta(hours=6)

    with get_session(test_db_config) as session:
        forecast = Forecast(
            location_id="test_loc",
            source="openmeteo",
            issued_at=now,
            valid_at=valid_time,
            lead_time_hours=6,
            temperature_c=18.5,
            precipitation_probability_pct=25,
        )
        session.add(forecast)

    with get_session(test_db_config) as session:
        fcst = session.query(Forecast).first()
        assert fcst.source == "openmeteo"
        assert fcst.lead_time_hours == 6
        assert fcst.temperature_c == 18.5


def test_terrain_feature_crud(test_db_config):
    """Test TerrainFeature CRUD operations."""
    init_db(test_db_config)

    with get_session(test_db_config) as session:
        location = Location(
            id="test_loc",
            name="Test",
            latitude=55.0,
            longitude=-3.0,
            location_type="target",
        )
        session.add(location)

    with get_session(test_db_config) as session:
        terrain = TerrainFeature(
            location_id="test_loc",
            elevation_m=250,
            slope_deg=5.5,
            aspect_deg=180,
            distance_to_coast_km=25.5,
            is_valley=0,
            is_hilltop=1,
        )
        session.add(terrain)

    with get_session(test_db_config) as session:
        t = session.query(TerrainFeature).first()
        assert t.elevation_m == 250
        assert t.is_hilltop == 1


def test_model_run_crud(test_db_config):
    """Test ModelRun CRUD operations."""
    init_db(test_db_config)

    with get_session(test_db_config) as session:
        model_run = ModelRun(
            model_name="lightgbm",
            model_version="v1.0",
            training_start_date=datetime(2024, 1, 1),
            training_end_date=datetime(2024, 12, 31),
            features=["temperature", "humidity", "pressure"],
            hyperparameters={"max_depth": 5, "learning_rate": 0.1},
            metrics={"mae": 1.23, "rmse": 1.85},
            model_path="models/lightgbm_v1.pkl",
        )
        session.add(model_run)

    with get_session(test_db_config) as session:
        run = session.query(ModelRun).first()
        assert run.model_name == "lightgbm"
        assert run.metrics["mae"] == 1.23
        assert len(run.features) == 3


def test_collection_log_crud(test_db_config):
    """Test CollectionLog CRUD operations."""
    init_db(test_db_config)

    started = datetime.utcnow()
    finished = started + timedelta(minutes=5)

    with get_session(test_db_config) as session:
        log = CollectionLog(
            collector="openmeteo",
            started_at=started,
            finished_at=finished,
            status="success",
            records_collected=150,
        )
        session.add(log)

    with get_session(test_db_config) as session:
        log = session.query(CollectionLog).first()
        assert log.collector == "openmeteo"
        assert log.status == "success"
        assert log.records_collected == 150


def test_relationship_cascade_delete(test_db_config):
    """Test that deleting a location cascades to related records."""
    init_db(test_db_config)

    # Create location with observation and forecast
    with get_session(test_db_config) as session:
        location = Location(
            id="test_loc",
            name="Test",
            latitude=55.0,
            longitude=-3.0,
            location_type="target",
        )
        session.add(location)

    now = datetime.utcnow()
    with get_session(test_db_config) as session:
        obs = Observation(
            location_id="test_loc",
            observed_at=now,
            source="test",
            temperature_c=15.0,
        )
        fcst = Forecast(
            location_id="test_loc",
            source="test",
            issued_at=now,
            valid_at=now + timedelta(hours=1),
            lead_time_hours=1,
        )
        session.add_all([obs, fcst])

    # Verify data exists
    with get_session(test_db_config) as session:
        assert session.query(Observation).count() == 1
        assert session.query(Forecast).count() == 1

    # Delete location
    with get_session(test_db_config) as session:
        location = session.query(Location).filter_by(id="test_loc").first()
        session.delete(location)

    # Verify cascade delete
    with get_session(test_db_config) as session:
        assert session.query(Location).count() == 0
        assert session.query(Observation).count() == 0
        assert session.query(Forecast).count() == 0


def test_session_rollback_on_error(test_db_config):
    """Test that session rolls back on error."""
    init_db(test_db_config)

    with get_session(test_db_config) as session:
        location = Location(
            id="test_loc",
            name="Test",
            latitude=55.0,
            longitude=-3.0,
            location_type="target",
        )
        session.add(location)

    # Verify location exists
    with get_session(test_db_config) as session:
        assert session.query(Location).count() == 1

    # Try to add invalid data (should rollback)
    try:
        with get_session(test_db_config) as session:
            # Valid location
            loc2 = Location(
                id="test_loc2",
                name="Test 2",
                latitude=56.0,
                longitude=-2.0,
                location_type="target",
            )
            session.add(loc2)
            # Invalid observation (foreign key violation)
            obs = Observation(
                location_id="nonexistent",
                observed_at=datetime.utcnow(),
                source="test",
            )
            session.add(obs)
    except Exception:
        pass  # Expected to fail

    # Verify rollback - loc2 should not exist
    with get_session(test_db_config) as session:
        assert session.query(Location).count() == 1
        assert session.query(Location).filter_by(id="test_loc2").first() is None
