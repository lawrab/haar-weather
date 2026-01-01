"""Command-line interface for Haar weather prediction system."""

import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table

from haar import __version__
from haar.config import HaarConfig, get_config
from haar.logging import setup_logging

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
            "Met Office",
            "✓" if cfg.sources.metoffice.enabled else "✗",
            "API key " + ("set" if cfg.sources.metoffice.api_key else "missing"),
        )
        table.add_row(
            "WOW",
            "✓" if cfg.sources.wow.enabled else "✗",
            f"{cfg.sources.wow.search_radius_km} km radius",
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
def db_init(force: bool) -> None:
    """Initialize the database schema."""
    console.print("[bold cyan]Initializing database...[/bold cyan]")
    if force:
        console.print("[yellow]⚠ Force mode: existing database will be recreated[/yellow]")
    console.print("[dim]Database initialization will be implemented in Issue #4[/dim]")


@db.command("stats")
def db_stats() -> None:
    """Show database statistics."""
    console.print("[bold cyan]Database Statistics[/bold cyan]\n")

    # Placeholder table
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Table")
    table.add_column("Records", justify="right")
    table.add_column("Size", justify="right")

    table.add_row("locations", "-", "-")
    table.add_row("observations", "-", "-")
    table.add_row("forecasts", "-", "-")
    table.add_row("terrain_features", "-", "-")
    table.add_row("model_runs", "-", "-")

    console.print(table)
    console.print("\n[dim]Database statistics will be implemented in Issue #4[/dim]")


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
    type=click.Choice(["all", "openmeteo", "metoffice", "wow"]),
    default="all",
    help="Data source to collect from",
)
@click.option("--backfill", type=int, help="Backfill N days of historical data")
def collect_run(source: str, backfill: Optional[int]) -> None:
    """Run data collection."""
    console.print(f"[bold cyan]Collecting data from: {source}[/bold cyan]")
    if backfill:
        console.print(f"Backfilling {backfill} days of historical data")
    console.print("[dim]Data collection will be implemented in Issues #7-14[/dim]")


@collect.command("status")
def collect_status() -> None:
    """Show collection status and data gaps."""
    console.print("[bold cyan]Collection Status[/bold cyan]\n")

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Source")
    table.add_column("Last Run")
    table.add_column("Status")
    table.add_column("Records")

    table.add_row("openmeteo", "-", "-", "-")
    table.add_row("metoffice", "-", "-", "-")
    table.add_row("wow", "-", "-", "-")

    console.print(table)
    console.print("\n[dim]Collection status will be implemented in Issue #14[/dim]")


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
