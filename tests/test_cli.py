"""Tests for the CLI."""

from click.testing import CliRunner

from haar.cli import cli


def test_cli_help():
    """Test CLI help message."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "Haar - Hyperlocal Scottish Weather Prediction System" in result.output


def test_cli_version():
    """Test CLI version flag."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_config_show():
    """Test config show command."""
    runner = CliRunner()
    result = runner.invoke(cli, ["config", "show"])
    assert result.exit_code == 0
    assert "Configuration file not found" in result.output or "Configuration:" in result.output


def test_db_stats():
    """Test db stats command."""
    runner = CliRunner()
    result = runner.invoke(cli, ["db", "stats"])
    assert result.exit_code == 0
    assert "Database Statistics" in result.output


def test_collect_status():
    """Test collect status command."""
    runner = CliRunner()
    result = runner.invoke(cli, ["collect", "status"])
    assert result.exit_code == 0
    assert "Collection Status" in result.output


def test_stations_list():
    """Test stations list command."""
    runner = CliRunner()
    result = runner.invoke(cli, ["stations", "list"])
    assert result.exit_code == 0
    assert "Weather Stations" in result.output


def test_forecast_show():
    """Test forecast show command."""
    runner = CliRunner()
    result = runner.invoke(cli, ["forecast", "show"])
    assert result.exit_code == 0
    assert "Haar Weather Forecast" in result.output


def test_models_list():
    """Test models list command."""
    runner = CliRunner()
    result = runner.invoke(cli, ["models", "list"])
    assert result.exit_code == 0
    assert "Trained Models" in result.output


def test_train_run():
    """Test train run command."""
    runner = CliRunner()
    result = runner.invoke(cli, ["train", "run", "--target", "temperature_c"])
    assert result.exit_code == 0
    assert "Training model" in result.output
