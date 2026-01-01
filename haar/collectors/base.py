"""Base collector interface for weather data sources."""

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional

from haar.storage import CollectionLog


class BaseCollector(ABC):
    """Abstract base class for weather data collectors."""

    def __init__(self, name: str):
        """Initialize collector.

        Args:
            name: Collector name for logging and tracking
        """
        self.name = name
        self.logger = logging.getLogger(f"haar.collectors.{name}")

    @abstractmethod
    def collect(self) -> int:
        """Collect data from source and store in database.

        Returns:
            Number of records collected

        Raises:
            Exception: If collection fails
        """
        pass

    def create_collection_log(
        self,
        started_at: datetime,
        finished_at: Optional[datetime] = None,
        status: str = "running",
        records_collected: int = 0,
        error_message: Optional[str] = None,
    ) -> CollectionLog:
        """Create a collection log entry.

        Args:
            started_at: Collection start time
            finished_at: Collection end time
            status: Status ('success', 'partial', 'failed', 'running')
            records_collected: Number of records collected
            error_message: Error message if failed

        Returns:
            CollectionLog instance
        """
        return CollectionLog(
            collector=self.name,
            started_at=started_at,
            finished_at=finished_at,
            status=status,
            records_collected=records_collected,
            error_message=error_message,
        )

    def log_collection_start(self) -> datetime:
        """Log collection start and return start time.

        Returns:
            Start timestamp
        """
        started_at = datetime.utcnow()
        self.logger.info(f"Starting collection from {self.name}")
        return started_at

    def log_collection_success(self, started_at: datetime, count: int) -> None:
        """Log successful collection.

        Args:
            started_at: Collection start time
            count: Number of records collected
        """
        duration = (datetime.utcnow() - started_at).total_seconds()
        self.logger.info(
            f"Collected {count} records from {self.name} in {duration:.1f}s"
        )

    def log_collection_error(self, started_at: datetime, error: Exception) -> None:
        """Log collection error.

        Args:
            started_at: Collection start time
            error: Exception that occurred
        """
        duration = (datetime.utcnow() - started_at).total_seconds()
        self.logger.error(
            f"Collection from {self.name} failed after {duration:.1f}s: {error}",
            exc_info=True,
        )
