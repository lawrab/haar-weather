"""Configuration management for Haar weather prediction system."""

import os
from pathlib import Path
from typing import List, Literal, Optional

from dotenv import load_dotenv

# Load .env file if it exists
load_dotenv()

try:
    import tomllib  # Python 3.11+
except ImportError:
    import tomli as tomllib  # Fallback for older Python

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LocationConfig(BaseModel):
    """Location configuration."""

    name: str = Field(default="Home", description="Location name")
    latitude: float = Field(
        default=55.9533, ge=-90, le=90, description="Latitude in decimal degrees"
    )
    longitude: float = Field(
        default=-3.1883, ge=-180, le=180, description="Longitude in decimal degrees"
    )
    radius_km: float = Field(default=200, gt=0, description="Search radius for stations")

    @field_validator("latitude", "longitude")
    @classmethod
    def validate_coordinates(cls, v: float, info) -> float:
        """Validate coordinate values."""
        if info.field_name == "latitude" and not -90 <= v <= 90:
            raise ValueError("Latitude must be between -90 and 90")
        if info.field_name == "longitude" and not -180 <= v <= 180:
            raise ValueError("Longitude must be between -180 and 180")
        return v


class DatabaseConfig(BaseModel):
    """Database configuration."""

    path: Path = Field(default=Path("data/haar.db"), description="SQLite database path")
    url: Optional[str] = Field(default=None, description="PostgreSQL connection URL")


class CollectionConfig(BaseModel):
    """Data collection configuration."""

    interval_minutes: int = Field(default=60, gt=0, description="Collection interval")
    backfill_days: int = Field(default=365, ge=0, description="Days to backfill")


class OpenMeteoConfig(BaseModel):
    """Open-Meteo API configuration."""

    enabled: bool = Field(default=True, description="Enable Open-Meteo collector")
    models: List[str] = Field(
        default=["ecmwf", "gfs", "icon"],
        description="NWP model families to collect (ecmwf, gfs, icon, auto)",
    )
    cache_hours: int = Field(default=1, ge=0, description="Response cache duration")


class MetOfficeConfig(BaseModel):
    """Met Office Weather DataHub API configuration."""

    enabled: bool = Field(default=True, description="Enable Met Office collector")
    api_key_env: str = Field(
        default="METOFFICE_DATAHUB_API_KEY",
        description="Environment variable for API key",
    )

    @property
    def api_key(self) -> Optional[str]:
        """Get API key from environment."""
        return os.getenv(self.api_key_env)


class NetatmoConfig(BaseModel):
    """Netatmo public weather stations configuration."""

    enabled: bool = Field(default=True, description="Enable Netatmo collector")
    client_id_env: str = Field(
        default="NETATMO_CLIENT_ID",
        description="Environment variable for client ID",
    )
    client_secret_env: str = Field(
        default="NETATMO_CLIENT_SECRET",
        description="Environment variable for client secret",
    )
    search_radius_km: float = Field(
        default=50, gt=0, description="Station search radius in km"
    )

    @property
    def client_id(self) -> Optional[str]:
        """Get client ID from environment."""
        return os.getenv(self.client_id_env)

    @property
    def client_secret(self) -> Optional[str]:
        """Get client secret from environment."""
        return os.getenv(self.client_secret_env)

    @property
    def access_token(self) -> Optional[str]:
        """Get access token from environment."""
        return os.getenv("NETATMO_ACCESS_TOKEN")

    @property
    def refresh_token(self) -> Optional[str]:
        """Get refresh token from environment."""
        return os.getenv("NETATMO_REFRESH_TOKEN")


class WeatherUndergroundConfig(BaseModel):
    """Weather Underground PWS configuration."""

    enabled: bool = Field(default=False, description="Enable Weather Underground collector")
    api_key_env: str = Field(
        default="WUNDERGROUND_API_KEY",
        description="Environment variable for API key",
    )

    @property
    def api_key(self) -> Optional[str]:
        """Get API key from environment."""
        return os.getenv(self.api_key_env)


class TerrainConfig(BaseModel):
    """Terrain data configuration."""

    dataset: Literal["srtm", "os_terrain_50"] = Field(
        default="srtm", description="Terrain dataset to use"
    )
    cache_dir: Path = Field(default=Path("data/terrain"), description="Terrain cache directory")


class SourcesConfig(BaseModel):
    """Data sources configuration."""

    openmeteo: OpenMeteoConfig = Field(default_factory=OpenMeteoConfig)
    metoffice: MetOfficeConfig = Field(default_factory=MetOfficeConfig)
    netatmo: NetatmoConfig = Field(default_factory=NetatmoConfig)
    wunderground: WeatherUndergroundConfig = Field(default_factory=WeatherUndergroundConfig)
    terrain: TerrainConfig = Field(default_factory=TerrainConfig)


class ModelsConfig(BaseModel):
    """Machine learning models configuration."""

    target_variables: List[str] = Field(
        default=["temperature_c", "precipitation_mm", "wind_speed_ms"],
        description="Target variables to predict",
    )
    forecast_horizons_hours: List[int] = Field(
        default=[1, 3, 6, 12, 24, 48, 72], description="Forecast lead times in hours"
    )
    min_training_days: int = Field(
        default=90, gt=0, description="Minimum days of data before training"
    )


class LoggingConfig(BaseModel):
    """Logging configuration."""

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", description="Log level"
    )
    file: Path = Field(default=Path("data/logs/haar.log"), description="Log file path")
    console: bool = Field(default=True, description="Enable console logging")
    max_bytes: int = Field(default=10485760, gt=0, description="Max log file size")
    backup_count: int = Field(default=5, ge=0, description="Number of backup log files")


class HaarConfig(BaseSettings):
    """Main Haar configuration."""

    model_config = SettingsConfigDict(
        env_prefix="HAAR_",
        env_nested_delimiter="__",
        case_sensitive=False,
    )

    location: LocationConfig = Field(default_factory=LocationConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    collection: CollectionConfig = Field(default_factory=CollectionConfig)
    sources: SourcesConfig = Field(default_factory=SourcesConfig)
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    @classmethod
    def from_toml(cls, path: Path) -> "HaarConfig":
        """Load configuration from TOML file.

        Args:
            path: Path to TOML configuration file

        Returns:
            HaarConfig instance

        Raises:
            FileNotFoundError: If config file doesn't exist
            ValueError: If config file is invalid
        """
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")

        try:
            with open(path, "rb") as f:
                config_dict = tomllib.load(f)
            return cls(**config_dict)
        except Exception as e:
            raise ValueError(f"Failed to load configuration from {path}: {e}") from e

    @classmethod
    def load(cls, config_path: Optional[Path] = None) -> "HaarConfig":
        """Load configuration from file or environment.

        Priority:
        1. Provided config_path
        2. HAAR_CONFIG environment variable
        3. Default path: ./config/haar.toml
        4. Fallback to defaults

        Args:
            config_path: Optional path to config file

        Returns:
            HaarConfig instance
        """
        # Determine config file path
        if config_path is None:
            env_path = os.getenv("HAAR_CONFIG")
            if env_path:
                config_path = Path(env_path)
            else:
                config_path = Path("config/haar.toml")

        # Load from file if it exists, otherwise use defaults
        if config_path.exists():
            return cls.from_toml(config_path)
        else:
            # Return default configuration
            return cls()

    def to_dict(self) -> dict:
        """Export configuration as dictionary.

        Returns:
            Configuration as dict
        """
        return self.model_dump()

    def save(self, path: Path) -> None:
        """Save configuration to TOML file.

        Args:
            path: Path to save configuration

        Note:
            This is a placeholder for future implementation.
            Currently not implemented as it requires TOML writing library.
        """
        raise NotImplementedError(
            "Configuration saving not yet implemented. "
            "Please edit config/haar.toml manually."
        )


# Global config instance (lazy loaded)
_config: Optional[HaarConfig] = None


def get_config(config_path: Optional[Path] = None, reload: bool = False) -> HaarConfig:
    """Get global configuration instance.

    Args:
        config_path: Optional path to config file
        reload: Force reload configuration

    Returns:
        HaarConfig instance
    """
    global _config

    if _config is None or reload:
        _config = HaarConfig.load(config_path)

    return _config


def reset_config() -> None:
    """Reset global configuration (useful for testing)."""
    global _config
    _config = None
