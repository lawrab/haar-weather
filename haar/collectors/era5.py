"""Open-Meteo ERA5 Reanalysis collector for historical weather data."""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from haar.collectors.base import BaseCollector
from haar.config import LocationConfig, get_config
from haar.storage import Location, Observation, get_session

logger = logging.getLogger(__name__)


class ERA5Collector(BaseCollector):
    """Collector for ERA5 reanalysis historical data via Open-Meteo Archive API.

    ERA5 is ECMWF's fifth generation atmospheric reanalysis, providing
    consistent historical weather data from 1940 to present (5-day delay).
    """

    ARCHIVE_ENDPOINT = "https://archive-api.open-meteo.com/v1/archive"

    # Variables to collect (matching our observation schema)
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

    # Maximum days per request to avoid timeouts
    MAX_DAYS_PER_REQUEST = 90

    def __init__(
        self,
        location_config: Optional[LocationConfig] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ):
        """Initialize ERA5 collector.

        Args:
            location_config: Location configuration
            start_date: Start date for historical data (default: 1 year ago)
            end_date: End date for historical data (default: 5 days ago)
        """
        super().__init__("era5_reanalysis")

        # Load config if not provided
        if location_config is None:
            config = get_config()
            location_config = config.location

        self.location_config = location_config

        # Set date range
        now = datetime.utcnow()
        self.end_date = end_date or (now - timedelta(days=5))  # ERA5 has 5-day delay
        self.start_date = start_date or (self.end_date - timedelta(days=365))

        # Ensure dates are date objects for API
        if isinstance(self.start_date, datetime):
            self.start_date = self.start_date.date()
        if isinstance(self.end_date, datetime):
            self.end_date = self.end_date.date()

        self.client = httpx.Client(timeout=60.0)  # Longer timeout for archive queries

    def collect(self) -> int:
        """Collect historical data from ERA5 reanalysis.

        Returns:
            Number of observation records collected
        """
        started_at = self.log_collection_start()
        total_collected = 0

        try:
            # Chunk the date range to avoid timeouts
            date_chunks = self._get_date_chunks()
            self.logger.info(
                f"Collecting ERA5 data from {self.start_date} to {self.end_date} "
                f"({len(date_chunks)} chunks)"
            )

            for chunk_start, chunk_end in date_chunks:
                count = self._collect_chunk(chunk_start, chunk_end)
                total_collected += count
                self.logger.debug(
                    f"Collected {count} records for {chunk_start} to {chunk_end}"
                )

            self.log_collection_success(started_at, total_collected)
            self._store_collection_log(
                started_at, datetime.utcnow(), "success", total_collected
            )

            return total_collected

        except Exception as e:
            self.log_collection_error(started_at, e)
            self._store_collection_log(
                started_at, datetime.utcnow(), "failed", total_collected, str(e)
            )
            raise

    def _get_date_chunks(self) -> List[tuple]:
        """Split date range into chunks for API requests.

        Returns:
            List of (start_date, end_date) tuples
        """
        chunks = []
        current = self.start_date

        while current < self.end_date:
            chunk_end = min(
                current + timedelta(days=self.MAX_DAYS_PER_REQUEST - 1),
                self.end_date,
            )
            chunks.append((current, chunk_end))
            current = chunk_end + timedelta(days=1)

        return chunks

    def _collect_chunk(self, start_date, end_date) -> int:
        """Collect data for a single date chunk.

        Args:
            start_date: Chunk start date
            end_date: Chunk end date

        Returns:
            Number of records collected
        """
        params = {
            "latitude": self.location_config.latitude,
            "longitude": self.location_config.longitude,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "hourly": ",".join(self.HOURLY_VARIABLES),
            "timezone": "UTC",
        }

        response = self.client.get(self.ARCHIVE_ENDPOINT, params=params)
        response.raise_for_status()
        data = response.json()

        return self._parse_and_store_observations(data)

    def _parse_and_store_observations(self, data: Dict[str, Any]) -> int:
        """Parse API response and store as observations.

        Args:
            data: API response JSON

        Returns:
            Number of records stored
        """
        # Get or create location
        location_id = f"era5_{self.location_config.name.lower().replace(' ', '_')}"

        with get_session() as session:
            location = session.query(Location).filter_by(id=location_id).first()
            if not location:
                location = Location(
                    id=location_id,
                    name=f"ERA5 - {self.location_config.name}",
                    latitude=self.location_config.latitude,
                    longitude=self.location_config.longitude,
                    location_type="reanalysis",
                    source="era5",
                    station_metadata={
                        "resolution_km": 25,
                        "data_type": "reanalysis",
                        "provider": "ECMWF via Open-Meteo",
                    },
                )
                session.add(location)
                session.commit()

        # Parse hourly data
        hourly = data.get("hourly", {})
        times = hourly.get("time", [])

        if not times:
            return 0

        observation_dicts = []
        for i, time_str in enumerate(times):
            observed_at = datetime.fromisoformat(time_str.replace("Z", "+00:00"))

            observation_dicts.append({
                "location_id": location_id,
                "observed_at": observed_at,
                "source": "era5_reanalysis",
                "temperature_c": self._get_value(hourly, "temperature_2m", i),
                "humidity_pct": self._get_value(hourly, "relative_humidity_2m", i),
                "pressure_hpa": self._get_value(hourly, "pressure_msl", i),
                "wind_speed_ms": self._get_value(hourly, "wind_speed_10m", i),
                "wind_direction_deg": self._get_value(hourly, "wind_direction_10m", i),
                "wind_gust_ms": self._get_value(hourly, "wind_gusts_10m", i),
                "precipitation_mm": self._get_value(hourly, "precipitation", i),
                "cloud_cover_pct": self._get_value(hourly, "cloud_cover", i),
                "weather_code": self._get_int_value(hourly, "weather_code", i),
                "raw_data": {
                    "data_type": "era5_reanalysis",
                    "resolution_km": 25,
                },
                "quality_flag": 2,  # Reanalysis data - good quality but not direct obs
            })

        if not observation_dicts:
            return 0

        # Store with upsert
        with get_session() as session:
            stmt = sqlite_insert(Observation).values(observation_dicts)
            stmt = stmt.on_conflict_do_update(
                index_elements=["location_id", "observed_at", "source"],
                set_={
                    "temperature_c": stmt.excluded.temperature_c,
                    "humidity_pct": stmt.excluded.humidity_pct,
                    "pressure_hpa": stmt.excluded.pressure_hpa,
                    "wind_speed_ms": stmt.excluded.wind_speed_ms,
                    "wind_direction_deg": stmt.excluded.wind_direction_deg,
                    "wind_gust_ms": stmt.excluded.wind_gust_ms,
                    "precipitation_mm": stmt.excluded.precipitation_mm,
                    "cloud_cover_pct": stmt.excluded.cloud_cover_pct,
                    "weather_code": stmt.excluded.weather_code,
                    "raw_data": stmt.excluded.raw_data,
                    "quality_flag": stmt.excluded.quality_flag,
                },
            )
            session.execute(stmt)

        return len(observation_dicts)

    def _get_value(self, data: Dict, key: str, index: int) -> Optional[float]:
        """Safely extract float value from API response."""
        values = data.get(key, [])
        if index < len(values):
            value = values[index]
            return float(value) if value is not None else None
        return None

    def _get_int_value(self, data: Dict, key: str, index: int) -> Optional[int]:
        """Safely extract integer value from API response."""
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
        """Store collection log in database."""
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
