"""Database connection and session management."""

import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

from sqlalchemy import create_engine, event, Index
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from haar.config import DatabaseConfig, get_config
from haar.storage.models import Base, Forecast, Location, Observation

logger = logging.getLogger(__name__)

# Global engine and session factory
_engine: Optional[Engine] = None
_session_factory: Optional[sessionmaker] = None


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    """Enable foreign keys for SQLite connections."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def get_engine(config: Optional[DatabaseConfig] = None, echo: bool = False) -> Engine:
    """Get or create database engine.

    Args:
        config: Database configuration (uses global config if None)
        echo: Echo SQL statements for debugging

    Returns:
        SQLAlchemy engine
    """
    global _engine

    if _engine is None:
        if config is None:
            haar_config = get_config()
            config = haar_config.database

        # Determine database URL
        if config.url:
            # Use PostgreSQL or other database URL
            db_url = config.url
        else:
            # Use SQLite with provided path
            db_path = config.path
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db_url = f"sqlite:///{db_path}"

        logger.info(f"Creating database engine: {db_url}")
        _engine = create_engine(db_url, echo=echo, future=True)

    return _engine


def get_session_factory(config: Optional[DatabaseConfig] = None) -> sessionmaker:
    """Get or create session factory.

    Args:
        config: Database configuration

    Returns:
        SQLAlchemy session factory
    """
    global _session_factory

    if _session_factory is None:
        engine = get_engine(config)
        _session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    return _session_factory


@contextmanager
def get_session(config: Optional[DatabaseConfig] = None) -> Generator[Session, None, None]:
    """Context manager for database sessions.

    Args:
        config: Database configuration

    Yields:
        Database session

    Example:
        with get_session() as session:
            locations = session.query(Location).all()
    """
    factory = get_session_factory(config)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db(config: Optional[DatabaseConfig] = None, force: bool = False) -> None:
    """Initialize database schema.

    Args:
        config: Database configuration (uses global config if None)
        force: Drop existing tables and recreate

    Raises:
        RuntimeError: If database already exists and force=False
    """
    engine = get_engine(config)

    if force:
        logger.warning("Dropping all tables (force=True)")
        Base.metadata.drop_all(engine)

    # Check if tables already exist
    from sqlalchemy import inspect

    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()

    if existing_tables and not force:
        raise RuntimeError(
            f"Database already exists with {len(existing_tables)} tables. "
            f"Use force=True to recreate."
        )

    logger.info("Creating database tables")
    Base.metadata.create_all(engine)

    # Create indexes
    logger.info("Creating indexes")
    _create_indexes(engine)

    logger.info("Database initialization complete")


def _create_indexes(engine: Engine) -> None:
    """Create database indexes for query performance.

    Args:
        engine: SQLAlchemy engine
    """
    from sqlalchemy import inspect

    inspector = inspect(engine)

    # Indexes for observations
    obs_indexes = inspector.get_indexes("observations")
    obs_index_names = {idx["name"] for idx in obs_indexes}

    if "idx_observations_location_time" not in obs_index_names:
        idx = Index(
            "idx_observations_location_time",
            Observation.location_id,
            Observation.observed_at,
        )
        idx.create(engine)

    if "idx_observations_time" not in obs_index_names:
        idx = Index("idx_observations_time", Observation.observed_at)
        idx.create(engine)

    # Indexes for forecasts
    fcst_indexes = inspector.get_indexes("forecasts")
    fcst_index_names = {idx["name"] for idx in fcst_indexes}

    if "idx_forecasts_location_valid" not in fcst_index_names:
        idx = Index(
            "idx_forecasts_location_valid",
            Forecast.location_id,
            Forecast.valid_at,
        )
        idx.create(engine)

    if "idx_forecasts_source_issued" not in fcst_index_names:
        idx = Index(
            "idx_forecasts_source_issued",
            Forecast.source,
            Forecast.issued_at,
        )
        idx.create(engine)


def reset_db_connection() -> None:
    """Reset global database connection (useful for testing)."""
    global _engine, _session_factory

    if _engine:
        _engine.dispose()
        _engine = None

    _session_factory = None
