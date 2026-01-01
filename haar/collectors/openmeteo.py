"""Open-Meteo API collector for NWP forecasts."""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx

from haar.collectors.base import BaseCollector
from haar.config import LocationConfig, OpenMeteoConfig, get_config
from haar.storage import Forecast, Location, get_session

logger = logging.getLogger(__name__)


class OpenMeteoCollector(BaseCollector):
    """Collector for Open-Meteo forecast data."""

    # API endpoints for different model families
    ENDPOINTS = {
        "ecmwf": "https://api.open-meteo.com/v1/ecmwf",
        "gfs": "https://api.open-meteo.com/v1/gfs",
        "icon": "https://api.open-meteo.com/v1/dwd-icon",
        "auto": "https://api.open-meteo.com/v1/forecast",  # Automatic model selection
    }

    # Weather variables to collect
    HOURLY_VARIABLES = [
        "temperature_2m",
        "relative_humidity_2m",
        "pressure_msl",
        "wind_speed_10m",
        "wind_direction_10m",
        "wind_gusts_10m",
        "precipitation",
        "cloud_cover",
        "weather_code",
    ]

    def __init__(
        self,
        location_config: Optional[LocationConfig] = None,
        openmeteo_config: Optional[OpenMeteoConfig] = None,
    ):
        """Initialize Open-Meteo collector.

        Args:
            location_config: Location configuration
            openmeteo_config: Open-Meteo API configuration
        """
        super().__init__("openmeteo")

        # Load config if not provided
        if location_config is None or openmeteo_config is None:
            config = get_config()
            location_config = location_config or config.location
            openmeteo_config = openmeteo_config or config.sources.openmeteo

        self.location_config = location_config
        self.openmeteo_config = openmeteo_config
        self.client = httpx.Client(timeout=30.0)

    def collect(self) -> int:
        """Collect forecast data from Open-Meteo API.

        Returns:
            Number of forecast records collected
        """
        started_at = self.log_collection_start()
        total_collected = 0

        try:
            # Collect forecasts for each configured model
            for model in self.openmeteo_config.models:
                count = self._collect_model_forecast(model)
                total_collected += count

            # Log collection success
            self.log_collection_success(started_at, total_collected)

            # Store collection log
            self._store_collection_log(started_at, datetime.utcnow(), "success", total_collected)

            return total_collected

        except Exception as e:
            self.log_collection_error(started_at, e)
            self._store_collection_log(
                started_at, datetime.utcnow(), "failed", total_collected, str(e)
            )
            raise

    def _collect_model_forecast(self, model_family: str) -> int:
        """Collect forecast from a specific NWP model family.

        Args:
            model_family: Model family name (e.g., 'ecmwf', 'gfs', 'icon', 'auto')

        Returns:
            Number of records collected
        """
        self.logger.debug(f"Collecting forecast from {model_family}")

        # Get the correct endpoint for this model family
        endpoint = self.ENDPOINTS.get(model_family)
        if not endpoint:
            self.logger.warning(f"Unknown model family '{model_family}', skipping")
            return 0

        # Build API request parameters
        params = {
            "latitude": self.location_config.latitude,
            "longitude": self.location_config.longitude,
            "hourly": ",".join(self.HOURLY_VARIABLES),
            "timezone": "UTC",
            "forecast_days": 7,  # 7-day forecast
        }

        # Make API request
        response = self.client.get(endpoint, params=params)
        response.raise_for_status()
        data = response.json()

        # Parse and store forecasts
        count = self._parse_and_store_forecasts(data, model_family)

        self.logger.debug(f"Collected {count} forecasts from {model_family}")
        return count

    def _parse_and_store_forecasts(self, data: Dict[str, Any], model_family: str) -> int:
        """Parse API response and store forecasts in database.

        Args:
            data: API response JSON
            model_family: NWP model family name (ecmwf, gfs, icon, auto)

        Returns:
            Number of records stored
        """
        # Get or create location
        location_id = f"target_{self.location_config.name.lower().replace(' ', '_')}"

        with get_session() as session:
            # Ensure location exists
            location = session.query(Location).filter_by(id=location_id).first()
            if not location:
                location = Location(
                    id=location_id,
                    name=self.location_config.name,
                    latitude=self.location_config.latitude,
                    longitude=self.location_config.longitude,
                    location_type="target",
                    source="config",
                )
                session.add(location)
                session.commit()

        # Parse hourly data
        hourly = data.get("hourly", {})
        times = hourly.get("time", [])

        if not times:
            self.logger.warning(f"No forecast data returned for {model_family}")
            return 0

        # Issued time is the current API request time
        issued_at = datetime.utcnow()

        forecasts = []
        for i, time_str in enumerate(times):
            # Parse valid time
            valid_at = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
            lead_time_hours = int((valid_at - issued_at).total_seconds() / 3600)

            # Skip if lead time is negative (shouldn't happen, but safety check)
            if lead_time_hours < 0:
                continue

            # Extract weather variables
            forecast = Forecast(
                location_id=location_id,
                source=f"openmeteo_{model_family}",
                issued_at=issued_at,
                valid_at=valid_at,
                lead_time_hours=lead_time_hours,
                temperature_c=self._get_value(hourly, "temperature_2m", i),
                humidity_pct=self._get_value(hourly, "relative_humidity_2m", i),
                pressure_hpa=self._get_value(hourly, "pressure_msl", i),
                wind_speed_ms=self._get_value(hourly, "wind_speed_10m", i),
                wind_direction_deg=self._get_value(hourly, "wind_direction_10m", i),
                precipitation_mm=self._get_value(hourly, "precipitation", i),
                cloud_cover_pct=self._get_value(hourly, "cloud_cover", i),
                weather_code=self._get_int_value(hourly, "weather_code", i),
                raw_data={
                    "model_family": model_family,
                    "endpoint": self.ENDPOINTS.get(model_family),
                    "api_response": {
                        k: v[i] if i < len(v) else None
                        for k, v in hourly.items()
                    },
                },
            )
            forecasts.append(forecast)

        # Store forecasts in database
        with get_session() as session:
            for forecast in forecasts:
                # Use merge to handle duplicates (update if exists)
                session.merge(forecast)

        return len(forecasts)

    def _get_value(self, data: Dict, key: str, index: int) -> Optional[float]:
        """Safely extract float value from API response.

        Args:
            data: Hourly data dict
            key: Variable name
            index: Time index

        Returns:
            Float value or None
        """
        values = data.get(key, [])
        if index < len(values):
            value = values[index]
            return float(value) if value is not None else None
        return None

    def _get_int_value(self, data: Dict, key: str, index: int) -> Optional[int]:
        """Safely extract integer value from API response.

        Args:
            data: Hourly data dict
            key: Variable name
            index: Time index

        Returns:
            Integer value or None
        """
        values = data.get(key, [])
        if index < len(values):
            value = values[index]
            return int(value) if value is not None else None
        return None

    def _store_collection_log(
        self,
        started_at: datetime,
        finished_at: datetime,
        status: str,
        records_collected: int,
        error_message: Optional[str] = None,
    ) -> None:
        """Store collection log in database.

        Args:
            started_at: Start time
            finished_at: End time
            status: Collection status
            records_collected: Number of records collected
            error_message: Error message if failed
        """
        log_entry = self.create_collection_log(
            started_at, finished_at, status, records_collected, error_message
        )

        with get_session() as session:
            session.add(log_entry)

    def close(self) -> None:
        """Close HTTP client."""
        self.client.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
