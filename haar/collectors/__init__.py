"""Data collectors for weather sources."""

from haar.collectors.base import BaseCollector
from haar.collectors.era5 import ERA5Collector
from haar.collectors.metoffice import MetOfficeObservationsCollector
from haar.collectors.netatmo import NetatmoCollector
from haar.collectors.openmeteo import OpenMeteoCollector

__all__ = [
    "BaseCollector",
    "ERA5Collector",
    "MetOfficeObservationsCollector",
    "NetatmoCollector",
    "OpenMeteoCollector",
]
