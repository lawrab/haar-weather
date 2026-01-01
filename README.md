# Haar - Hyperlocal Scottish Weather Prediction

> Combining NWP models, personal weather stations, and machine learning to predict local weather in Scotland.

## Overview

Haar is a hobby project that aims to create hyperlocal weather forecasts for a ~200 mile radius in Scotland by:
- Collecting data from multiple sources (NWP models, PWS networks, official observations)
- Engineering terrain-aware features
- Training machine learning models that account for local microclimates
- Outperforming generic national forecasts

**Status**: 🚧 In development - Phase 1

## Goals

1. Collect and store weather data from multiple sources in a unified schema
2. Build ML models that predict local weather 1-72 hours ahead
3. Outperform persistence baseline and match/beat generic API forecasts
4. Learn NWP data handling, meteorological feature engineering, and time-series ML

## Project Name

**Haar** (Scottish English pronunciation: /hɑːr/) - a cold sea fog that occurs on the east coast of Scotland, particularly common in spring and early summer. The name reflects the project's focus on understanding and predicting Scotland's unique and often hyperlocal weather patterns.

## Technical Stack

- **Language**: Python 3.11+
- **Database**: SQLite (initially), PostgreSQL (if needed later)
- **Scheduling**: Systemd timers
- **ML Framework**: scikit-learn + LightGBM
- **Configuration**: TOML
- **CLI**: Click + Rich

## Quick Start

> **Note**: The project is in early development. Full installation instructions will be available after Phase 1 completion.

### Requirements
- Python 3.11+
- NixOS (recommended) or manual dependency installation
- SQLite
- Met Office API key (free from [datahub.metoffice.gov.uk](https://datahub.metoffice.gov.uk))

### Development Setup (Planned)

```bash
# Clone the repository
git clone https://github.com/lawrab/haar-weather.git
cd haar-weather

# Enter Nix development shell (NixOS)
nix develop

# Or install dependencies manually
pip install -e .

# Initialize configuration
cp config/haar.example.toml config/haar.toml
# Edit config/haar.toml with your location and API keys

# Initialize database
haar db init

# Collect initial data
haar collect
```

## Project Structure

See [docs/haar-project-spec.md](docs/haar-project-spec.md) for comprehensive documentation.

## Development Roadmap

### Phase 1: Foundation (Current)
- [x] Project planning and specification
- [x] GitHub repository setup
- [ ] Project scaffolding
- [ ] Configuration system
- [ ] Database schema
- [ ] CLI framework
- [ ] First data collector (Open-Meteo)

### Phase 2: Station Discovery
- Personal weather station integration
- Station quality assessment
- Multi-source data collection

### Phase 3: Terrain & Features
- Terrain data acquisition
- Feature engineering pipeline
- Data quality modules

### Phase 4: Baseline Models
- Baseline forecasting models
- ML model training
- Evaluation framework

### Phase 5: Iteration
- Model refinement
- Additional data sources
- Visualization and analysis tools

## Data Sources

### Tier 1 (Essential)
- **Open-Meteo**: Forecasts + historical data (no API key required)
- **Met Office DataPoint**: UK observations (free API key)
- **Met Office WOW**: Personal weather station network
- **OS Terrain 50 / SRTM**: Elevation data

### Tier 2 (Enhancement)
- ECMWF Open Data
- ERA5 Reanalysis
- MET Norway

### Tier 3 (Future)
- Met Office Rain Radar
- EUMETSAT satellite imagery
- DWD ICON-EU

## Contributing

This is a personal hobby project, but suggestions and discussions are welcome via GitHub issues.

## License

MIT License - See [LICENSE](LICENSE) for details.

## Project Status

Track progress and view issues at: https://github.com/lawrab/haar-weather/issues

Current milestone: [Phase 1: Foundation](https://github.com/lawrab/haar-weather/milestone/1)
