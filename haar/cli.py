"""Command-line interface for Haar weather prediction system."""

import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table

from haar import __version__
from haar.collectors import MetOfficeObservationsCollector, OpenMeteoCollector
from haar.config import HaarConfig, get_config
from haar.logging import get_logger, setup_logging
from haar.storage import get_session, init_db, reset_db_connection

console = Console()


@click.group()
@click.version_option(version=__version__, prog_name="haar")
@click.option(
    "--config",
    type=click.Path(dir_okay=False, path_type=Path),
    envvar="HAAR_CONFIG",
    help="Path to configuration file (default: ./config/haar.toml)",
)
@click.option(
    "-v",
    "--verbose",
    count=True,
    help="Increase verbosity (use -v, -vv, or -vvv)",
)
@click.pass_context
def cli(ctx: click.Context, config: Optional[Path], verbose: int) -> None:
    """Haar - Hyperlocal Scottish Weather Prediction System.

    A machine learning system for predicting local weather patterns in Scotland
    by combining NWP models, personal weather stations, and terrain-aware features.
    """
    # Store config and verbosity in context for subcommands
    ctx.ensure_object(dict)
    ctx.obj["config"] = config or Path("./config/haar.toml")
    ctx.obj["verbose"] = verbose

    # Setup logging based on config and verbosity
    try:
        cfg = get_config(config or Path("./config/haar.toml"))
        setup_logging(cfg.logging, verbose=verbose)
    except Exception:
        # If config loading fails, use basic logging
        setup_logging(verbose=verbose)


# ============================================================================
# Config Commands
# ============================================================================


@cli.group()
def config() -> None:
    """Manage configuration settings."""
    pass


@config.command("show")
@click.pass_context
def config_show(ctx: click.Context) -> None:
    """Display current configuration."""
    config_path = ctx.obj["config"]

    try:
        cfg = get_config(config_path, reload=True)
        config_exists = config_path.exists()

        console.print(f"[bold cyan]Configuration:[/bold cyan] {config_path}")
        if not config_exists:
            console.print(
                "[yellow]⚠ Using default configuration (file not found)[/yellow]\n"
            )

        # Location
        table = Table(title="Location", show_header=False)
        table.add_row("Name", cfg.location.name)
        table.add_row("Latitude", f"{cfg.location.latitude}°")
        table.add_row("Longitude", f"{cfg.location.longitude}°")
        table.add_row("Search Radius", f"{cfg.location.radius_km} km")
        console.print(table)

        # Database
        table = Table(title="Database", show_header=False)
        table.add_row("Path", str(cfg.database.path))
        if cfg.database.url:
            table.add_row("URL", cfg.database.url)
        console.print(table)

        # Collection
        table = Table(title="Collection", show_header=False)
        table.add_row("Interval", f"{cfg.collection.interval_minutes} minutes")
        table.add_row("Backfill", f"{cfg.collection.backfill_days} days")
        console.print(table)

        # Data Sources
        table = Table(title="Data Sources", show_header=True, header_style="bold magenta")
        table.add_column("Source")
        table.add_column("Enabled")
        table.add_column("Details")

        table.add_row(
            "Open-Meteo",
            "✓" if cfg.sources.openmeteo.enabled else "✗",
            f"{len(cfg.sources.openmeteo.models)} models",
        )
        table.add_row(
            "Met Office Atmospheric",
            "✓" if cfg.sources.metoffice_atmospheric.enabled else "✗",
            "API key " + ("set" if cfg.sources.metoffice_atmospheric.api_key else "missing"),
        )
        table.add_row(
            "Met Office Observations",
            "✓" if cfg.sources.metoffice_observations.enabled else "✗",
            "API key " + ("set" if cfg.sources.metoffice_observations.api_key else "missing"),
        )
        table.add_row(
            "Netatmo",
            "✓" if cfg.sources.netatmo.enabled else "✗",
            f"{cfg.sources.netatmo.search_radius_km} km radius",
        )
        table.add_row(
            "Terrain", "✓", cfg.sources.terrain.dataset
        )
        console.print(table)

        # Models
        table = Table(title="ML Models", show_header=False)
        table.add_row("Target Variables", ", ".join(cfg.models.target_variables))
        table.add_row(
            "Forecast Horizons",
            ", ".join(f"{h}h" for h in cfg.models.forecast_horizons_hours),
        )
        table.add_row("Min Training Days", str(cfg.models.min_training_days))
        console.print(table)

        if not config_exists:
            console.print("\n[dim]To create a configuration file:[/dim]")
            console.print("[dim]  cp config/haar.example.toml config/haar.toml[/dim]")

    except Exception as e:
        console.print(f"[bold red]Error loading configuration:[/bold red] {e}")


@config.command("set")
@click.argument("key")
@click.argument("value")
def config_set(key: str, value: str) -> None:
    """Set a configuration value.

    Example: haar config set location.latitude 55.9533
    """
    console.print(f"[dim]Setting {key} = {value}[/dim]")
    console.print("[yellow]Configuration management will be implemented in Issue #3[/yellow]")


# ============================================================================
# Database Commands
# ============================================================================


@cli.group()
def db() -> None:
    """Database management commands."""
    pass


@db.command("init")
@click.option("--force", is_flag=True, help="Recreate database if it exists")
@click.pass_context
def db_init(ctx: click.Context, force: bool) -> None:
    """Initialize the database schema."""
    logger = get_logger(__name__)
    console.print("[bold cyan]Initializing database...[/bold cyan]")

    if force:
        console.print("[yellow]⚠ Force mode: existing database will be recreated[/yellow]")

    try:
        init_db(force=force)
        console.print("[green]✓ Database initialized successfully[/green]")

        # Show database location
        cfg = get_config(ctx.obj.get("config"))
        if cfg.database.url:
            console.print(f"  Database: {cfg.database.url}")
        else:
            console.print(f"  Database: {cfg.database.path}")

    except RuntimeError as e:
        console.print(f"[red]✗ {e}[/red]")
        console.print("[dim]  Use --force to recreate the database[/dim]")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Database initialization failed: {e}", exc_info=True)
        console.print(f"[bold red]✗ Database initialization failed:[/bold red] {e}")
        sys.exit(1)


@db.command("stats")
def db_stats() -> None:
    """Show database statistics."""
    from haar.storage import CollectionLog, Forecast, Location, ModelRun, Observation, TerrainFeature

    console.print("[bold cyan]Database Statistics[/bold cyan]\n")

    try:
        with get_session() as session:
            # Query counts for each table
            counts = {
                "locations": session.query(Location).count(),
                "observations": session.query(Observation).count(),
                "forecasts": session.query(Forecast).count(),
                "terrain_features": session.query(TerrainFeature).count(),
                "model_runs": session.query(ModelRun).count(),
                "collection_logs": session.query(CollectionLog).count(),
            }

        # Create table
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Table")
        table.add_column("Records", justify="right")

        for table_name, count in counts.items():
            table.add_row(table_name, str(count))

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error querying database:[/red] {e}")
        console.print("[dim]Database may not be initialized. Run 'haar db init' first.[/dim]")
        sys.exit(1)


@db.command("vacuum")
def db_vacuum() -> None:
    """Optimize database (VACUUM)."""
    console.print("[bold cyan]Optimizing database...[/bold cyan]")
    console.print("[dim]Database optimization will be implemented in Issue #4[/dim]")


@db.command("export")
@click.option(
    "--format",
    type=click.Choice(["csv", "json", "parquet"]),
    default="csv",
    help="Export format",
)
@click.option("--output", type=click.Path(), help="Output file path")
def db_export(format: str, output: Optional[str]) -> None:
    """Export database to file."""
    console.print(f"[bold cyan]Exporting database to {format.upper()}...[/bold cyan]")
    console.print(f"Output: {output or 'stdout'}")
    console.print("[dim]Database export will be implemented in Issue #4[/dim]")


@db.command("reset")
@click.option("--logs", is_flag=True, help="Also clear log files")
@click.option("--cache", is_flag=True, help="Also clear terrain cache")
@click.option("--all", "clear_all", is_flag=True, help="Clear everything (db, logs, cache)")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
@click.pass_context
def db_reset(ctx: click.Context, logs: bool, cache: bool, clear_all: bool, yes: bool) -> None:
    """Reset database and optionally clear logs/cache.

    By default, only deletes the database. Use flags to clear more:

    \b
    haar db reset           # Delete database only
    haar db reset --logs    # Delete database and logs
    haar db reset --cache   # Delete database and terrain cache
    haar db reset --all     # Delete everything
    """
    import shutil

    cfg = get_config(ctx.obj.get("config"))

    # Determine what to delete
    delete_logs = logs or clear_all
    delete_cache = cache or clear_all

    # Build list of items to delete
    items_to_delete = []

    # Database
    db_path = cfg.database.path
    if db_path.exists():
        items_to_delete.append(("Database", db_path, "file"))

    # Logs
    log_dir = cfg.logging.file.parent
    if delete_logs and log_dir.exists():
        items_to_delete.append(("Logs", log_dir, "directory"))

    # Terrain cache
    terrain_dir = cfg.sources.terrain.cache_dir
    if delete_cache and terrain_dir.exists():
        items_to_delete.append(("Terrain cache", terrain_dir, "directory"))

    if not items_to_delete:
        console.print("[yellow]Nothing to delete.[/yellow]")
        return

    # Show what will be deleted
    console.print("[bold red]The following will be deleted:[/bold red]\n")
    for name, path, item_type in items_to_delete:
        if item_type == "directory":
            console.print(f"  • {name}: {path}/ (directory)")
        else:
            console.print(f"  • {name}: {path}")

    console.print()

    # Confirm unless --yes flag
    if not yes:
        if not click.confirm("Are you sure you want to proceed?"):
            console.print("[dim]Aborted.[/dim]")
            return

    # Reset database connection to release file handles
    reset_db_connection()

    # Delete items
    deleted_count = 0
    for name, path, item_type in items_to_delete:
        try:
            if item_type == "directory":
                shutil.rmtree(path)
            else:
                path.unlink()
            console.print(f"[green]✓ Deleted {name}[/green]")
            deleted_count += 1
        except Exception as e:
            console.print(f"[red]✗ Failed to delete {name}: {e}[/red]")

    console.print(f"\n[bold cyan]Reset complete.[/bold cyan] {deleted_count} item(s) deleted.")


# ============================================================================
# Collection Commands
# ============================================================================


@cli.group()
def collect() -> None:
    """Data collection commands."""
    pass


@collect.command("run")
@click.option(
    "--source",
    type=click.Choice(["all", "openmeteo", "metoffice", "netatmo"]),
    default="all",
    help="Data source to collect from",
)
@click.option("--backfill", type=int, help="Backfill N days of historical data")
def collect_run(source: str, backfill: Optional[int]) -> None:
    """Run data collection."""
    logger = get_logger(__name__)
    console.print(f"[bold cyan]Collecting data from: {source}[/bold cyan]")

    if backfill:
        console.print(f"[yellow]Backfill option not yet implemented[/yellow]")

    total_collected = 0
    errors = []

    try:
        # Collect from Open-Meteo (forecasts)
        if source in ("all", "openmeteo"):
            try:
                console.print("\n[cyan]→[/cyan] Collecting from Open-Meteo...")
                with OpenMeteoCollector() as collector:
                    count = collector.collect()
                console.print(f"  [green]✓[/green] Collected {count} forecasts from Open-Meteo")
                total_collected += count
            except Exception as e:
                error_msg = f"Open-Meteo collection failed: {e}"
                logger.error(error_msg, exc_info=True)
                console.print(f"  [red]✗[/red] {error_msg}")
                errors.append(("Open-Meteo", str(e)))

        # Collect from Met Office (observations)
        if source in ("all", "metoffice"):
            cfg = get_config()
            if cfg.sources.metoffice_observations.api_key:
                try:
                    console.print("\n[cyan]→[/cyan] Collecting from Met Office...")
                    with MetOfficeObservationsCollector() as collector:
                        count = collector.collect()
                    console.print(f"  [green]✓[/green] Collected {count} observations from Met Office")
                    total_collected += count
                except Exception as e:
                    error_msg = f"Met Office collection failed: {e}"
                    logger.error(error_msg, exc_info=True)
                    console.print(f"  [red]✗[/red] {error_msg}")
                    errors.append(("Met Office", str(e)))
            else:
                console.print("\n[dim]Met Office API key not configured (set METOFFICE_OBSERVATIONS_API_KEY)[/dim]")

        # Placeholder for Netatmo
        if source in ("all", "netatmo"):
            console.print("\n[dim]Netatmo collector not yet implemented (Issue #42)[/dim]")

        # Summary
        console.print(f"\n[bold]Total: {total_collected} records collected[/bold]")

        if errors:
            console.print(f"\n[yellow]Errors ({len(errors)}):[/yellow]")
            for source_name, error in errors:
                console.print(f"  • {source_name}: {error}")
            sys.exit(1)

    except Exception as e:
        logger.error(f"Collection failed: {e}", exc_info=True)
        console.print(f"\n[bold red]✗ Collection failed:[/bold red] {e}")
        sys.exit(1)


@collect.command("status")
def collect_status() -> None:
    """Show collection status and recent runs."""
    from haar.storage import CollectionLog

    console.print("[bold cyan]Collection Status[/bold cyan]\n")

    try:
        with get_session() as session:
            # Get recent collection logs
            logs = (
                session.query(CollectionLog)
                .order_by(CollectionLog.started_at.desc())
                .limit(10)
                .all()
            )

        if not logs:
            console.print("[dim]No collection runs found. Run 'haar collect run' first.[/dim]")
            return

        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Collector")
        table.add_column("Started")
        table.add_column("Duration")
        table.add_column("Status")
        table.add_column("Records", justify="right")

        for log in logs:
            # Format duration
            if log.finished_at:
                duration = (log.finished_at - log.started_at).total_seconds()
                duration_str = f"{duration:.1f}s"
            else:
                duration_str = "running"

            # Format started time (relative)
            from datetime import datetime, timezone
            started = log.started_at.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            time_ago = now - started
            if time_ago.days > 0:
                started_str = f"{time_ago.days}d ago"
            elif time_ago.seconds > 3600:
                started_str = f"{time_ago.seconds // 3600}h ago"
            elif time_ago.seconds > 60:
                started_str = f"{time_ago.seconds // 60}m ago"
            else:
                started_str = f"{time_ago.seconds}s ago"

            # Color-code status
            status_str = log.status
            if log.status == "success":
                status_str = f"[green]{log.status}[/green]"
            elif log.status == "failed":
                status_str = f"[red]{log.status}[/red]"
            elif log.status == "partial":
                status_str = f"[yellow]{log.status}[/yellow]"

            table.add_row(
                log.collector,
                started_str,
                duration_str,
                status_str,
                str(log.records_collected or 0),
            )

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error querying collection logs:[/red] {e}")
        console.print("[dim]Database may not be initialized. Run 'haar db init' first.[/dim]")
        sys.exit(1)


# ============================================================================
# Station Commands
# ============================================================================


@cli.group()
def stations() -> None:
    """Weather station management."""
    pass


@stations.command("discover")
@click.option("--radius", type=float, help="Search radius in km")
def stations_discover(radius: Optional[float]) -> None:
    """Discover nearby weather stations."""
    console.print(f"[bold cyan]Discovering stations (radius: {radius or 'default'} km)[/bold cyan]")
    console.print("[dim]Station discovery will be implemented in Issue #15[/dim]")


@stations.command("list")
def stations_list() -> None:
    """List known weather stations."""
    console.print("[bold cyan]Weather Stations[/bold cyan]\n")

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("ID")
    table.add_column("Name")
    table.add_column("Distance (km)", justify="right")
    table.add_column("Quality", justify="right")

    console.print(table)
    console.print("\n[dim]Station listing will be implemented in Issue #17[/dim]")


@stations.command("add")
@click.argument("station_id")
def stations_add(station_id: str) -> None:
    """Add a weather station by ID."""
    console.print(f"[bold cyan]Adding station: {station_id}[/bold cyan]")
    console.print("[dim]Station management will be implemented in Issue #17[/dim]")


@stations.command("remove")
@click.argument("station_id")
def stations_remove(station_id: str) -> None:
    """Remove a weather station."""
    console.print(f"[bold cyan]Removing station: {station_id}[/bold cyan]")
    console.print("[dim]Station management will be implemented in Issue #17[/dim]")


@stations.command("quality")
def stations_quality() -> None:
    """Assess station data quality."""
    console.print("[bold cyan]Station Quality Assessment[/bold cyan]")
    console.print("[dim]Quality assessment will be implemented in Issue #16[/dim]")


# ============================================================================
# Forecast Commands
# ============================================================================


@cli.group()
def forecast() -> None:
    """Weather forecasting commands."""
    pass


@forecast.command("show")
@click.option("--hours", type=int, default=24, help="Forecast horizon in hours")
def forecast_show(hours: int) -> None:
    """Display weather forecast."""
    console.print(f"[bold cyan]Haar Weather Forecast[/bold cyan] (next {hours} hours)\n")
    console.print("[dim]Forecasting will be implemented in Issue #26[/dim]")


@forecast.command("compare")
def forecast_compare() -> None:
    """Compare Haar vs API forecasts."""
    console.print("[bold cyan]Forecast Comparison[/bold cyan]")
    console.print("[dim]Forecast comparison will be implemented in Issue #29[/dim]")


# ============================================================================
# Training Commands
# ============================================================================


@cli.group()
def train() -> None:
    """Model training commands."""
    pass


@train.command("run")
@click.option(
    "--target",
    type=click.Choice(["temperature_c", "precipitation_mm", "wind_speed_ms", "all"]),
    default="all",
    help="Target variable to train",
)
def train_run(target: str) -> None:
    """Train ML models."""
    console.print(f"[bold cyan]Training model for: {target}[/bold cyan]")
    console.print("[dim]Model training will be implemented in Issue #25[/dim]")


@train.command("evaluate")
def train_evaluate() -> None:
    """Evaluate model performance."""
    console.print("[bold cyan]Model Evaluation[/bold cyan]")
    console.print("[dim]Model evaluation will be implemented in Issue #24[/dim]")


# ============================================================================
# Model Management Commands
# ============================================================================


@cli.group()
def models() -> None:
    """Model management commands."""
    pass


@models.command("list")
def models_list() -> None:
    """List trained models."""
    console.print("[bold cyan]Trained Models[/bold cyan]\n")

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Version")
    table.add_column("Target")
    table.add_column("Trained")
    table.add_column("MAE", justify="right")

    console.print(table)
    console.print("\n[dim]Model listing will be implemented in Issue #27[/dim]")


@models.command("compare")
def models_compare() -> None:
    """Compare model performance."""
    console.print("[bold cyan]Model Comparison[/bold cyan]")
    console.print("[dim]Model comparison will be implemented in Issue #27[/dim]")


# ============================================================================
# Analysis Commands
# ============================================================================


@cli.group()
def accuracy() -> None:
    """Accuracy and analysis commands."""
    pass


@accuracy.command("report")
def accuracy_report() -> None:
    """Generate accuracy report."""
    console.print("[bold cyan]Accuracy Report[/bold cyan]")
    console.print("[dim]Accuracy reporting will be implemented in Issue #28[/dim]")


# ============================================================================
# Data Exploration Commands
# ============================================================================


@cli.group()
def data() -> None:
    """Data exploration commands."""
    pass


@data.command("query")
@click.option("--start", help="Start date (YYYY-MM-DD)")
@click.option("--end", help="End date (YYYY-MM-DD)")
def data_query(start: Optional[str], end: Optional[str]) -> None:
    """Query collected data."""
    console.print(f"[bold cyan]Querying data: {start or 'all'} to {end or 'now'}[/bold cyan]")
    console.print("[dim]Data querying will be implemented in Issue #30[/dim]")


@data.command("plot")
@click.argument("variable")
@click.option("--days", type=int, default=7, help="Number of days to plot")
def data_plot(variable: str, days: int) -> None:
    """Plot collected data."""
    console.print(f"[bold cyan]Plotting {variable} (last {days} days)[/bold cyan]")
    console.print("[dim]Data plotting will be implemented in Issue #30[/dim]")


# ============================================================================
# Main Entry Point
# ============================================================================


def main() -> int:
    """Main entry point for the CLI."""
    try:
        cli(obj={})
        return 0
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
