"""Netatmo public weather station collector for PWS observations."""

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from haar.collectors.base import BaseCollector
from haar.config import LocationConfig, NetatmoConfig, get_config
from haar.storage import Location, Observation, get_session

logger = logging.getLogger(__name__)


class NetatmoCollector(BaseCollector):
    """Collector for Netatmo public weather station data.

    Uses the Netatmo /getpublicdata endpoint to fetch observations
    from personal weather stations in the configured area.
    """

    API_BASE = "https://api.netatmo.com/api"
    OAUTH_URL = "https://api.netatmo.com/oauth2/token"

    def __init__(
        self,
        location_config: Optional[LocationConfig] = None,
        netatmo_config: Optional[NetatmoConfig] = None,
    ):
        """Initialize Netatmo collector.

        Args:
            location_config: Location configuration
            netatmo_config: Netatmo API configuration
        """
        super().__init__("netatmo")

        # Load config if not provided
        if location_config is None or netatmo_config is None:
            config = get_config()
            location_config = location_config or config.location
            netatmo_config = netatmo_config or config.sources.netatmo

        self.location_config = location_config
        self.netatmo_config = netatmo_config

        # Validate credentials
        if not self.netatmo_config.access_token:
            raise ValueError(
                "Netatmo access token not configured. "
                "Set NETATMO_ACCESS_TOKEN in your .env file."
            )

        self._access_token = self.netatmo_config.access_token
        self.client = httpx.Client(timeout=30.0)

    def _refresh_token(self) -> bool:
        """Refresh the OAuth2 access token.

        Returns:
            True if token was refreshed successfully
        """
        refresh_token = self.netatmo_config.refresh_token
        if not refresh_token:
            self.logger.error("No refresh token available")
            return False

        client_id = self.netatmo_config.client_id
        client_secret = self.netatmo_config.client_secret
        if not client_id or not client_secret:
            self.logger.error("Client ID or secret not configured")
            return False

        try:
            response = self.client.post(
                self.OAUTH_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
            )
            response.raise_for_status()

            data = response.json()
            new_access_token = data.get("access_token")
            new_refresh_token = data.get("refresh_token")

            if new_access_token:
                self._access_token = new_access_token
                # Update environment for future runs
                os.environ["NETATMO_ACCESS_TOKEN"] = new_access_token
                if new_refresh_token:
                    os.environ["NETATMO_REFRESH_TOKEN"] = new_refresh_token

                self.logger.info("Successfully refreshed Netatmo access token")
                self.logger.warning(
                    "Token refreshed in memory only. Update your .env file with:\n"
                    f"  NETATMO_ACCESS_TOKEN={new_access_token}\n"
                    f"  NETATMO_REFRESH_TOKEN={new_refresh_token}"
                )
                return True

        except Exception as e:
            self.logger.error(f"Failed to refresh token: {e}")

        return False

    def _get_bounding_box(self) -> tuple[float, float, float, float]:
        """Calculate bounding box for station search.

        Returns:
            Tuple of (lat_sw, lon_sw, lat_ne, lon_ne)
        """
        lat = self.location_config.latitude
        lon = self.location_config.longitude
        radius_km = self.netatmo_config.search_radius_km

        # Approximate degrees for radius (1 degree ~= 111 km at equator)
        # For latitude, this is fairly constant
        # For longitude, we need to account for latitude
        import math

        lat_offset = radius_km / 111.0
        lon_offset = radius_km / (111.0 * math.cos(math.radians(lat)))

        lat_sw = lat - lat_offset
        lon_sw = lon - lon_offset
        lat_ne = lat + lat_offset
        lon_ne = lon + lon_offset

        return (lat_sw, lon_sw, lat_ne, lon_ne)

    def _fetch_public_data(self) -> List[Dict[str, Any]]:
        """Fetch public weather station data from Netatmo API.

        Returns:
            List of station data dictionaries
        """
        lat_sw, lon_sw, lat_ne, lon_ne = self._get_bounding_box()

        self.logger.debug(
            f"Fetching stations in bounding box: "
            f"({lat_sw:.4f}, {lon_sw:.4f}) to ({lat_ne:.4f}, {lon_ne:.4f})"
        )

        response = self.client.get(
            f"{self.API_BASE}/getpublicdata",
            params={
                "lat_ne": lat_ne,
                "lon_ne": lon_ne,
                "lat_sw": lat_sw,
                "lon_sw": lon_sw,
            },
            headers={"Authorization": f"Bearer {self._access_token}"},
        )

        # Handle token expiry
        if response.status_code == 403:
            self.logger.warning("Access token expired, attempting refresh...")
            if self._refresh_token():
                # Retry with new token
                response = self.client.get(
                    f"{self.API_BASE}/getpublicdata",
                    params={
                        "lat_ne": lat_ne,
                        "lon_ne": lon_ne,
                        "lat_sw": lat_sw,
                        "lon_sw": lon_sw,
                    },
                    headers={"Authorization": f"Bearer {self._access_token}"},
                )
            else:
                response.raise_for_status()

        response.raise_for_status()
        data = response.json()

        return data.get("body", [])

    def collect(self) -> int:
        """Collect observation data from Netatmo public stations.

        Returns:
            Number of observation records collected
        """
        started_at = self.log_collection_start()
        total_collected = 0

        try:
            stations = self._fetch_public_data()
            self.logger.info(f"Found {len(stations)} Netatmo stations in area")

            for station in stations:
                count = self._process_station(station)
                total_collected += count

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

    def _process_station(self, station_data: Dict[str, Any]) -> int:
        """Process a single station's data.

        Args:
            station_data: Station data from API

        Returns:
            Number of observations stored
        """
        station_id = station_data.get("_id")
        if not station_id:
            return 0

        # Station location
        location = station_data.get("place", {})
        lat = location.get("location", [0, 0])[1]  # [lon, lat] format
        lon = location.get("location", [0, 0])[0]
        city = location.get("city", "Unknown")
        street = location.get("street", "")

        # Create location ID
        location_id = f"netatmo_{station_id}"

        # Ensure location exists
        self._ensure_location(
            location_id=location_id,
            name=f"Netatmo - {city}" + (f" ({street})" if street else ""),
            latitude=lat,
            longitude=lon,
            station_metadata={
                "station_id": station_id,
                "city": city,
                "street": street,
                "altitude": location.get("altitude"),
                "timezone": location.get("timezone"),
            },
        )

        # Parse measures from all modules
        measures = station_data.get("measures", {})
        observations = self._parse_measures(measures, location_id)

        if observations:
            self._store_observations(observations)

        return len(observations)

    def _ensure_location(
        self,
        location_id: str,
        name: str,
        latitude: float,
        longitude: float,
        station_metadata: Dict[str, Any],
    ) -> None:
        """Ensure location exists in database.

        Args:
            location_id: Unique location ID
            name: Display name
            latitude: Station latitude
            longitude: Station longitude
            station_metadata: Additional station info
        """
        with get_session() as session:
            existing = session.query(Location).filter_by(id=location_id).first()
            if not existing:
                location = Location(
                    id=location_id,
                    name=name,
                    latitude=latitude,
                    longitude=longitude,
                    location_type="netatmo",
                    source="netatmo",
                    station_metadata=station_metadata,
                )
                session.add(location)
                session.commit()
                self.logger.debug(f"Created location: {name}")

    def _parse_measures(
        self, measures: Dict[str, Any], location_id: str
    ) -> List[Dict[str, Any]]:
        """Parse measures from station modules.

        Args:
            measures: Measures dict from API (keyed by module ID)
            location_id: Location ID for observations

        Returns:
            List of observation dicts ready for upsert
        """
        observations = []

        # Collect the most recent readings from all modules
        latest_timestamp = None
        temp_c = None
        humidity_pct = None
        pressure_hpa = None
        rain_mm = None
        wind_speed_ms = None
        wind_gust_ms = None
        wind_direction_deg = None

        for module_id, module_data in measures.items():
            if not isinstance(module_data, dict):
                continue

            # Check for rain data (NAModule3)
            rain_60min = module_data.get("rain_60min")
            if rain_60min is not None:
                rain_mm = rain_60min

            rain_live = module_data.get("rain_live")
            if rain_live is not None:
                rain_mm = rain_live

            # Check for wind data (NAModule2)
            wind_strength = module_data.get("wind_strength")
            if wind_strength is not None:
                # Convert km/h to m/s
                wind_speed_ms = wind_strength / 3.6

            gust_strength = module_data.get("gust_strength")
            if gust_strength is not None:
                wind_gust_ms = gust_strength / 3.6

            wind_angle = module_data.get("wind_angle")
            if wind_angle is not None:
                wind_direction_deg = wind_angle

            # Check for typed data (temperature, humidity, pressure)
            res = module_data.get("res", {})
            module_type = module_data.get("type", [])

            for timestamp_str, values in res.items():
                try:
                    timestamp = int(timestamp_str)
                    observed_at = datetime.utcfromtimestamp(timestamp)

                    # Track latest timestamp
                    if latest_timestamp is None or timestamp > latest_timestamp:
                        latest_timestamp = timestamp

                    # Parse values based on type array
                    for i, type_name in enumerate(module_type):
                        if i < len(values):
                            value = values[i]
                            if type_name == "temperature":
                                temp_c = value
                            elif type_name == "humidity":
                                humidity_pct = value
                            elif type_name == "pressure":
                                pressure_hpa = value

                except (ValueError, TypeError) as e:
                    self.logger.debug(f"Failed to parse measure: {e}")
                    continue

        # Create observation if we have any data
        if latest_timestamp is not None:
            observed_at = datetime.utcfromtimestamp(latest_timestamp)
            observations.append({
                "location_id": location_id,
                "observed_at": observed_at,
                "source": "netatmo",
                "temperature_c": temp_c,
                "humidity_pct": humidity_pct,
                "pressure_hpa": pressure_hpa,
                "wind_speed_ms": wind_speed_ms,
                "wind_direction_deg": wind_direction_deg,
                "wind_gust_ms": wind_gust_ms,
                "precipitation_mm": rain_mm,
                "raw_data": {
                    "rain_60min": rain_mm,
                },
                "quality_flag": 1,  # PWS data - lower quality than official stations
            })

        return observations

    def _store_observations(self, observations: List[Dict[str, Any]]) -> None:
        """Store observations with upsert.

        Args:
            observations: List of observation dicts
        """
        if not observations:
            return

        with get_session() as session:
            stmt = sqlite_insert(Observation).values(observations)
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
                    "raw_data": stmt.excluded.raw_data,
                    "quality_flag": stmt.excluded.quality_flag,
                },
            )
            session.execute(stmt)

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
