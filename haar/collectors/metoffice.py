"""Met Office Weather DataHub collector for UK observations."""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from haar.collectors.base import BaseCollector
from haar.config import LocationConfig, MetOfficeObservationsConfig, get_config
from haar.storage import Location, Observation, get_session

logger = logging.getLogger(__name__)


# Wind direction compass to degrees mapping
WIND_DIRECTION_MAP = {
    "N": 0,
    "NNE": 22.5,
    "NE": 45,
    "ENE": 67.5,
    "E": 90,
    "ESE": 112.5,
    "SE": 135,
    "SSE": 157.5,
    "S": 180,
    "SSW": 202.5,
    "SW": 225,
    "WSW": 247.5,
    "W": 270,
    "WNW": 292.5,
    "NW": 315,
    "NNW": 337.5,
}


class MetOfficeObservationsCollector(BaseCollector):
    """Collector for Met Office Weather DataHub Land Observations."""

    BASE_URL = "https://data.hub.api.metoffice.gov.uk/observation-land/1"

    def __init__(
        self,
        location_config: Optional[LocationConfig] = None,
        metoffice_config: Optional[MetOfficeObservationsConfig] = None,
    ):
        """Initialize Met Office observations collector.

        Args:
            location_config: Location configuration
            metoffice_config: Met Office API configuration
        """
        super().__init__("metoffice_observations")

        # Load config if not provided
        if location_config is None or metoffice_config is None:
            config = get_config()
            location_config = location_config or config.location
            metoffice_config = metoffice_config or config.sources.metoffice_observations

        self.location_config = location_config
        self.metoffice_config = metoffice_config

        # Validate API key
        if not self.metoffice_config.api_key:
            raise ValueError(
                "Met Office observations API key not configured. "
                "Set METOFFICE_OBSERVATIONS_API_KEY in your .env file."
            )

        self.client = httpx.Client(
            timeout=30.0,
            headers={"apikey": self.metoffice_config.api_key},
        )

        # Cache for station geohashes (to reduce API calls)
        self._station_cache: Dict[str, Dict[str, Any]] = {}

    def collect(self) -> int:
        """Collect observation data from Met Office Land Observations API.

        Returns:
            Number of observation records collected
        """
        started_at = self.log_collection_start()
        total_collected = 0

        try:
            # Find nearest station to target location
            station_info = self._find_nearest_station(
                self.location_config.latitude,
                self.location_config.longitude,
            )

            if not station_info:
                self.logger.warning("No nearby Met Office station found")
                return 0

            # Collect observations from the station
            count = self._collect_station_observations(station_info)
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

    def _find_nearest_station(self, latitude: float, longitude: float) -> Optional[Dict[str, Any]]:
        """Find nearest Met Office station to given coordinates.

        Args:
            latitude: Latitude (will be rounded to 2 decimal places)
            longitude: Longitude (will be rounded to 2 decimal places)

        Returns:
            Station info dict with geohash, area, region, country, or None
        """
        # Check cache first
        cache_key = f"{latitude:.2f},{longitude:.2f}"
        if cache_key in self._station_cache:
            return self._station_cache[cache_key]

        # API requires max 2 decimal places
        lat_rounded = round(latitude, 2)
        lon_rounded = round(longitude, 2)

        self.logger.debug(f"Finding nearest station to ({lat_rounded}, {lon_rounded})")

        response = self.client.get(
            f"{self.BASE_URL}/nearest",
            params={"lat": lat_rounded, "lon": lon_rounded},
        )
        response.raise_for_status()

        data = response.json()

        if data and len(data) > 0:
            station_info = data[0]
            self._station_cache[cache_key] = station_info
            self.logger.info(
                f"Found nearest station: {station_info.get('area', 'Unknown')} "
                f"(geohash: {station_info.get('geohash')})"
            )
            return station_info

        return None

    def _collect_station_observations(self, station_info: Dict[str, Any]) -> int:
        """Collect observations from a specific station.

        Args:
            station_info: Station info dict containing geohash

        Returns:
            Number of observations collected
        """
        geohash = station_info.get("geohash")
        if not geohash:
            self.logger.warning("Station info missing geohash")
            return 0

        self.logger.debug(f"Collecting observations for geohash: {geohash}")

        response = self.client.get(f"{self.BASE_URL}/{geohash}")
        response.raise_for_status()

        observations_data = response.json()

        if not observations_data:
            self.logger.warning(f"No observations returned for {geohash}")
            return 0

        # Parse and store observations
        return self._parse_and_store_observations(observations_data, station_info)

    def _parse_and_store_observations(
        self, observations_data: List[Dict[str, Any]], station_info: Dict[str, Any]
    ) -> int:
        """Parse API response and store observations in database.

        Args:
            observations_data: List of observation dicts from API
            station_info: Station metadata

        Returns:
            Number of records stored
        """
        geohash = station_info.get("geohash")
        area = station_info.get("area", "Unknown")

        # Create location ID for this station
        location_id = f"metoffice_{geohash}"

        with get_session() as session:
            # Ensure location exists
            location = session.query(Location).filter_by(id=location_id).first()
            if not location:
                location = Location(
                    id=location_id,
                    name=f"Met Office - {area}",
                    latitude=self.location_config.latitude,  # Approximate
                    longitude=self.location_config.longitude,  # Approximate
                    location_type="metoffice",
                    source="metoffice_datahub",
                    station_metadata={
                        "geohash": geohash,
                        "area": area,
                        "region": station_info.get("region"),
                        "country": station_info.get("country"),
                        "timezone": station_info.get("olson_time_zone"),
                    },
                )
                session.add(location)
                session.commit()

        # Parse observations into dicts for upsert
        observation_dicts = []
        for obs_data in observations_data:
            obs_dict = self._parse_observation_dict(obs_data, location_id)
            if obs_dict:
                observation_dicts.append(obs_dict)

        if not observation_dicts:
            return 0

        # Store observations with upsert (insert or update on conflict)
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
                    "visibility_m": stmt.excluded.visibility_m,
                    "weather_code": stmt.excluded.weather_code,
                    "raw_data": stmt.excluded.raw_data,
                    "quality_flag": stmt.excluded.quality_flag,
                },
            )
            session.execute(stmt)

        self.logger.debug(f"Stored {len(observation_dicts)} observations for {area}")
        return len(observation_dicts)

    def _parse_observation_dict(
        self, obs_data: Dict[str, Any], location_id: str
    ) -> Optional[Dict[str, Any]]:
        """Parse a single observation from API response into a dict for upsert.

        Args:
            obs_data: Single observation dict from API
            location_id: Location ID for this station

        Returns:
            Dict with observation fields or None if parsing fails
        """
        try:
            # Parse datetime
            datetime_str = obs_data.get("datetime")
            if not datetime_str:
                return None

            observed_at = datetime.fromisoformat(datetime_str.replace("Z", "+00:00"))

            # Convert wind direction from compass to degrees
            wind_dir_compass = obs_data.get("wind_direction")
            wind_direction_deg = WIND_DIRECTION_MAP.get(wind_dir_compass) if wind_dir_compass else None

            return {
                "location_id": location_id,
                "observed_at": observed_at,
                "source": "metoffice_datahub",
                "temperature_c": obs_data.get("temperature"),
                "humidity_pct": obs_data.get("humidity"),
                "pressure_hpa": obs_data.get("mslp"),
                "wind_speed_ms": self._convert_wind_speed(obs_data.get("wind_speed")),
                "wind_direction_deg": wind_direction_deg,
                "wind_gust_ms": self._convert_wind_speed(obs_data.get("wind_gust")),
                "visibility_m": obs_data.get("visibility"),
                "weather_code": obs_data.get("weather_code"),
                "raw_data": {
                    "original": obs_data,
                    "pressure_tendency": obs_data.get("pressure_tendency"),
                },
                "quality_flag": 0,  # Met Office data is high quality
            }

        except Exception as e:
            self.logger.warning(f"Failed to parse observation: {e}")
            return None

    def _convert_wind_speed(self, speed: Optional[float]) -> Optional[float]:
        """Convert wind speed to m/s if needed.

        Met Office API returns wind speed in m/s, so no conversion needed.

        Args:
            speed: Wind speed value

        Returns:
            Wind speed in m/s
        """
        # Met Office API already returns m/s
        return speed

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
