"""Met Office Weather DataHub collector for UK observations."""

import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import httpx
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from haar.collectors.base import BaseCollector
from haar.config import LocationConfig, MetOfficeObservationsConfig, get_config
from haar.storage import Location, Observation, get_session


def decode_geohash(geohash: str) -> Tuple[float, float]:
    """Decode a geohash to latitude/longitude.

    Simple implementation without external dependency.

    Args:
        geohash: Geohash string

    Returns:
        Tuple of (latitude, longitude)
    """
    BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"

    lat_range = [-90.0, 90.0]
    lon_range = [-180.0, 180.0]
    is_lon = True

    for char in geohash.lower():
        idx = BASE32.index(char)
        for bit in [16, 8, 4, 2, 1]:
            if is_lon:
                mid = (lon_range[0] + lon_range[1]) / 2
                if idx & bit:
                    lon_range[0] = mid
                else:
                    lon_range[1] = mid
            else:
                mid = (lat_range[0] + lat_range[1]) / 2
                if idx & bit:
                    lat_range[0] = mid
                else:
                    lat_range[1] = mid
            is_lon = not is_lon

    lat = (lat_range[0] + lat_range[1]) / 2
    lon = (lon_range[0] + lon_range[1]) / 2
    return (lat, lon)

logger = logging.getLogger(__name__)


# Known Met Office observation station geohashes (discovered via API)
# These rarely change - last updated January 2026
SCOTTISH_STATIONS = [
    "gfnmmy",  # Aberdeen
    "gfjuxq",  # Aberdeenshire
    "gf517k",  # Argyll and Bute
    "gcgsc8",  # Argyll and Bute
    "gcu2pd",  # Dumfries and Galloway
    "gctpub",  # Dumfries and Galloway
    "gcvw5v",  # Edinburgh
    "gf5yws",  # Highland
    "gfh7qb",  # Highland
    "gfjm2y",  # Highland
    "gf7cps",  # Highland
    "gfk82s",  # Highland
    "gfkgdg",  # Highland
    "gfsb5g",  # Highland
    "gfm8k6",  # Moray
    "gf4wr9",  # Na h-Eileanan Siar
    "gf7e0j",  # Na h-Eileanan Siar
    "gfmzqh",  # Orkney Islands
    "gcuy0c",  # Renfrewshire
    "gcykcv",  # Scottish Borders
    "gfwfdu",  # Shetland Islands
    "gfxnj5",  # Shetland Islands
]


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

        # Cache for discovered stations (keyed by geohash)
        self._station_cache: Dict[str, Dict[str, Any]] = {}

    def collect(self) -> int:
        """Collect observation data from Met Office Land Observations API.

        Collects from all configured stations (Scottish stations by default).

        Returns:
            Number of observation records collected
        """
        started_at = self.log_collection_start()
        total_collected = 0

        try:
            station_geohashes = self._get_stations()
            self.logger.info(f"Collecting from {len(station_geohashes)} Met Office stations")

            # Collect observations from each station (with rate limiting)
            for i, geohash in enumerate(station_geohashes):
                try:
                    count = self._collect_station_by_geohash(geohash)
                    total_collected += count
                    # Rate limit: ~2 requests per second to avoid 429 errors
                    if i < len(station_geohashes) - 1:
                        time.sleep(0.5)
                except Exception as e:
                    self.logger.warning(f"Failed to collect from {geohash}: {e}")
                    continue

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

    def _collect_station_by_geohash(self, geohash: str) -> int:
        """Collect observations from a station by geohash.

        Args:
            geohash: Station geohash

        Returns:
            Number of observations collected
        """
        self.logger.debug(f"Collecting observations for geohash: {geohash}")

        response = self.client.get(f"{self.BASE_URL}/{geohash}")
        response.raise_for_status()

        observations_data = response.json()

        if not observations_data:
            self.logger.debug(f"No observations returned for {geohash}")
            return 0

        # Get station info from first observation or create minimal info
        station_info = {"geohash": geohash, "area": "Unknown"}

        return self._parse_and_store_observations(observations_data, station_info)

    def _get_stations(self) -> List[str]:
        """Get list of station geohashes to collect from.

        Returns all Scottish stations by default.

        Returns:
            List of station geohash strings
        """
        return SCOTTISH_STATIONS

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

        # Decode geohash to get actual station coordinates
        station_lat, station_lon = decode_geohash(geohash)

        # Create location ID for this station
        location_id = f"metoffice_{geohash}"

        with get_session() as session:
            # Ensure location exists
            location = session.query(Location).filter_by(id=location_id).first()
            if not location:
                location = Location(
                    id=location_id,
                    name=f"Met Office - {area}",
                    latitude=station_lat,
                    longitude=station_lon,
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
