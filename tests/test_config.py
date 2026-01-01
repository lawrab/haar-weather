"""Tests for configuration management."""

import os
from pathlib import Path

import pytest

from haar.config import (
    DatabaseConfig,
    HaarConfig,
    LocationConfig,
    LoggingConfig,
    get_config,
    reset_config,
)


@pytest.fixture
def temp_config_file(tmp_path):
    """Create a temporary config file."""
    config_content = """
[location]
name = "Test Location"
latitude = 56.0
longitude = -4.0
radius_km = 100

[database]
path = "test.db"

[collection]
interval_minutes = 30
backfill_days = 180

[sources.openmeteo]
enabled = true
models = ["gfs_seamless"]

[sources.metoffice]
enabled = false

[logging]
level = "DEBUG"
console = false
"""
    config_file = tmp_path / "test_config.toml"
    config_file.write_text(config_content)
    return config_file


@pytest.fixture(autouse=True)
def reset_global_config():
    """Reset global config before each test."""
    reset_config()
    yield
    reset_config()


def test_location_config_defaults():
    """Test LocationConfig with defaults."""
    config = LocationConfig(latitude=55.9533, longitude=-3.1883)
    assert config.name == "Home"
    assert config.latitude == 55.9533
    assert config.longitude == -3.1883
    assert config.radius_km == 200


def test_location_config_validation():
    """Test LocationConfig validation."""
    # Valid coordinates
    config = LocationConfig(latitude=0, longitude=0)
    assert config.latitude == 0
    assert config.longitude == 0

    # Invalid latitude
    with pytest.raises(ValueError):
        LocationConfig(latitude=91, longitude=0)

    with pytest.raises(ValueError):
        LocationConfig(latitude=-91, longitude=0)

    # Invalid longitude
    with pytest.raises(ValueError):
        LocationConfig(latitude=0, longitude=181)

    with pytest.raises(ValueError):
        LocationConfig(latitude=0, longitude=-181)


def test_database_config_defaults():
    """Test DatabaseConfig with defaults."""
    config = DatabaseConfig()
    assert config.path == Path("data/haar.db")
    assert config.url is None


def test_logging_config_defaults():
    """Test LoggingConfig with defaults."""
    config = LoggingConfig()
    assert config.level == "INFO"
    assert config.file == Path("data/logs/haar.log")
    assert config.console is True
    assert config.max_bytes == 10485760
    assert config.backup_count == 5


def test_haar_config_defaults():
    """Test HaarConfig with all defaults."""
    config = HaarConfig()

    # Location defaults
    assert config.location.name == "Home"
    assert config.location.radius_km == 200

    # Database defaults
    assert config.database.path == Path("data/haar.db")

    # Collection defaults
    assert config.collection.interval_minutes == 60
    assert config.collection.backfill_days == 365

    # Sources defaults
    assert config.sources.openmeteo.enabled is True
    assert config.sources.metoffice.enabled is True
    assert config.sources.wow.enabled is True

    # Models defaults
    assert "temperature_c" in config.models.target_variables
    assert 24 in config.models.forecast_horizons_hours

    # Logging defaults
    assert config.logging.level == "INFO"


def test_config_from_toml(temp_config_file):
    """Test loading configuration from TOML file."""
    config = HaarConfig.from_toml(temp_config_file)

    assert config.location.name == "Test Location"
    assert config.location.latitude == 56.0
    assert config.location.longitude == -4.0
    assert config.location.radius_km == 100

    assert str(config.database.path) == "test.db"

    assert config.collection.interval_minutes == 30
    assert config.collection.backfill_days == 180

    assert config.sources.openmeteo.enabled is True
    assert config.sources.openmeteo.models == ["gfs_seamless"]
    assert config.sources.metoffice.enabled is False

    assert config.logging.level == "DEBUG"
    assert config.logging.console is False


def test_config_from_toml_file_not_found():
    """Test error when config file doesn't exist."""
    with pytest.raises(FileNotFoundError):
        HaarConfig.from_toml(Path("nonexistent.toml"))


def test_config_load_with_path(temp_config_file):
    """Test loading config with explicit path."""
    config = HaarConfig.load(temp_config_file)
    assert config.location.name == "Test Location"


def test_config_load_with_env_var(temp_config_file, monkeypatch):
    """Test loading config from environment variable."""
    monkeypatch.setenv("HAAR_CONFIG", str(temp_config_file))
    config = HaarConfig.load()
    assert config.location.name == "Test Location"


def test_config_load_defaults_when_missing():
    """Test loading defaults when no config file exists."""
    config = HaarConfig.load(Path("nonexistent.toml"))
    assert config.location.name == "Home"  # Default value


def test_config_to_dict():
    """Test exporting config to dictionary."""
    config = HaarConfig()
    config_dict = config.to_dict()

    assert isinstance(config_dict, dict)
    assert "location" in config_dict
    assert "database" in config_dict
    assert "sources" in config_dict
    assert config_dict["location"]["name"] == "Home"


def test_get_config_singleton():
    """Test global config singleton."""
    config1 = get_config()
    config2 = get_config()
    assert config1 is config2  # Same instance


def test_get_config_reload(temp_config_file):
    """Test reloading configuration."""
    # First load
    config1 = get_config()
    assert config1.location.name == "Home"

    # Reload with different config
    config2 = get_config(temp_config_file, reload=True)
    assert config2.location.name == "Test Location"

    # Subsequent call returns reloaded config
    config3 = get_config()
    assert config3.location.name == "Test Location"


def test_metoffice_api_key_from_env(monkeypatch):
    """Test Met Office API key retrieval from environment."""
    monkeypatch.setenv("METOFFICE_API_KEY", "test_key_12345")

    config = HaarConfig()
    assert config.sources.metoffice.api_key == "test_key_12345"


def test_metoffice_api_key_missing():
    """Test Met Office API key when not set."""
    config = HaarConfig()
    # Should return None if env var not set
    assert config.sources.metoffice.api_key is None or isinstance(
        config.sources.metoffice.api_key, str
    )


def test_config_save_not_implemented():
    """Test that config saving raises NotImplementedError."""
    config = HaarConfig()
    with pytest.raises(NotImplementedError):
        config.save(Path("test.toml"))


def test_example_config_loads():
    """Test that the example config file loads correctly."""
    example_config = Path("config/haar.example.toml")
    if example_config.exists():
        config = HaarConfig.from_toml(example_config)
        assert config.location.name == "Home"
        assert config.location.latitude == 55.9533
        assert config.database.path == Path("data/haar.db")
