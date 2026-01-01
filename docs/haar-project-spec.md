# Haar: Hyperlocal Scottish Weather Prediction

## Project Overview

**Haar** is a hyperlocal weather prediction system designed for a 100-200 mile radius in Scotland. It combines data from multiple sources (NWP models, personal weather station networks, and official observations) with machine learning to produce forecasts that outperform generic national predictions by accounting for local terrain and microclimates.

This is a hobby project prioritising learning and practical utility over enterprise patterns.

### Goals

1. Collect and store weather data from multiple sources in a unified schema
2. Build ML models that predict local weather 1-72 hours ahead
3. Outperform persistence baseline and match/beat generic API forecasts
4. Learn NWP data handling, meteorological feature engineering, and time-series ML

### Non-Goals

- Production-grade reliability or 24/7 uptime
- Mobile apps or public-facing services
- Real-time alerting systems
- Covering areas beyond ~200 miles from base location

---

## Technical Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Language | Python 3.11+ | Rich ecosystem for weather data (xarray, cfgrib, metpy), ML (scikit-learn, lightgbm), and APIs |
| Database | SQLite initially, PostgreSQL later if needed | Zero config, file-based, sufficient for hobby scale |
| Scheduling | Systemd timers | Native on NixOS, no external dependencies |
| Visualisation | Matplotlib/Plotly for analysis, optional Grafana later | Keep dependencies minimal initially |
| ML Framework | scikit-learn + LightGBM | Tabular data doesn't need deep learning |
| Config | TOML or YAML | Human-readable, easy to version |

### Directory Structure

```
haar/
├── haar/
│   ├── __init__.py
│   ├── cli.py                 # Command-line interface
│   ├── config.py              # Configuration management
│   ├── collectors/            # Data collection modules
│   │   ├── __init__.py
│   │   ├── base.py            # Abstract collector interface
│   │   ├── openmeteo.py       # Open-Meteo API
│   │   ├── metoffice.py       # Met Office DataPoint + WOW
│   │   ├── pws.py             # Personal weather station networks
│   │   └── terrain.py         # Terrain data extraction
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── database.py        # SQLite/PostgreSQL interface
│   │   ├── models.py          # Data models / schema
│   │   └── migrations/        # Schema migrations
│   ├── features/
│   │   ├── __init__.py
│   │   ├── temporal.py        # Time-based features (lags, rolling stats)
│   │   ├── spatial.py         # Location-based features (terrain, distance)
│   │   └── quality.py         # Data quality checks, outlier detection
│   ├── models/
│   │   ├── __init__.py
│   │   ├── baseline.py        # Persistence, climatology baselines
│   │   ├── ml.py              # ML model training and inference
│   │   └── evaluation.py      # Metrics, skill scores
│   └── visualisation/
│       ├── __init__.py
│       └── plots.py           # Analysis and forecast plots
├── scripts/
│   ├── discover_stations.py   # One-off station discovery
│   └── backfill.py            # Historical data backfill
├── tests/
│   └── ...
├── data/                      # Local data storage (gitignored)
│   ├── haar.db                # SQLite database
│   ├── terrain/               # Cached terrain data
│   └── cache/                 # API response cache
├── config/
│   ├── haar.example.toml      # Example configuration
│   └── logging.toml           # Logging configuration
├── pyproject.toml
├── README.md
└── flake.nix                  # NixOS development environment
```

---

## Data Sources (Priority Order)

### Tier 1: Essential (Implement First)

| Source | Data Type | Update Frequency | Access Method |
|--------|-----------|------------------|---------------|
| **Open-Meteo** | Forecasts + 80yr historical | Hourly forecasts, historical on-demand | REST API, no key |
| **Met Office DataPoint** | UK observations | Hourly | REST API, free key |
| **Met Office WOW** | PWS observations | Varies by station | REST API |
| **OS Terrain 50** | Elevation data | Static | Download once |

### Tier 2: Enhancement (Add Later)

| Source | Data Type | Access Method |
|--------|-----------|---------------|
| **ECMWF Open Data** | High-res NWP (GRIB2) | Download via API |
| **ERA5 Reanalysis** | Historical reanalysis | Copernicus CDS API |
| **MET Norway** | Alternative forecasts | REST API, no key |
| **Weather Underground** | Additional PWS | REST API (IBM) |

### Tier 3: Advanced (Future)

| Source | Data Type | Purpose |
|--------|-----------|---------|
| **Met Office Rain Radar** | Precipitation imagery | Nowcasting |
| **EUMETSAT** | Satellite imagery | Cloud tracking |
| **DWD ICON-EU** | European NWP | Ensemble diversity |

---

## Database Schema

### Core Tables

```sql
-- Locations we care about (our location + PWS stations + grid points)
CREATE TABLE locations (
    id TEXT PRIMARY KEY,
    name TEXT,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    elevation_m REAL,
    location_type TEXT NOT NULL, -- 'target', 'pws', 'metoffice', 'grid'
    source TEXT,                 -- Which network/source
    metadata JSON,               -- Station-specific info
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Actual weather observations
CREATE TABLE observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id TEXT NOT NULL REFERENCES locations(id),
    observed_at TIMESTAMP NOT NULL,
    source TEXT NOT NULL,
    temperature_c REAL,
    humidity_pct REAL,
    pressure_hpa REAL,
    wind_speed_ms REAL,
    wind_direction_deg REAL,
    wind_gust_ms REAL,
    precipitation_mm REAL,
    cloud_cover_pct REAL,
    visibility_m REAL,
    weather_code INTEGER,
    raw_data JSON,               -- Original API response
    quality_flag INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(location_id, observed_at, source)
);

-- Forecasts from various sources (for comparison and training)
CREATE TABLE forecasts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id TEXT NOT NULL REFERENCES locations(id),
    source TEXT NOT NULL,        -- 'openmeteo', 'metoffice', 'haar_v1', etc.
    issued_at TIMESTAMP NOT NULL,
    valid_at TIMESTAMP NOT NULL,
    lead_time_hours INTEGER NOT NULL,
    temperature_c REAL,
    humidity_pct REAL,
    pressure_hpa REAL,
    wind_speed_ms REAL,
    wind_direction_deg REAL,
    precipitation_mm REAL,
    precipitation_probability_pct REAL,
    cloud_cover_pct REAL,
    weather_code INTEGER,
    raw_data JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(location_id, source, issued_at, valid_at)
);

-- Terrain features (computed once per location)
CREATE TABLE terrain_features (
    location_id TEXT PRIMARY KEY REFERENCES locations(id),
    elevation_m REAL,
    slope_deg REAL,
    aspect_deg REAL,
    distance_to_coast_km REAL,
    distance_to_highland_km REAL,
    terrain_roughness REAL,
    is_valley INTEGER,
    is_hilltop INTEGER,
    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Model training runs and metadata
CREATE TABLE model_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    trained_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    training_start_date DATE,
    training_end_date DATE,
    features JSON,
    hyperparameters JSON,
    metrics JSON,               -- MAE, RMSE, skill scores
    model_path TEXT,            -- Path to serialised model
    notes TEXT
);

-- Collection job logs
CREATE TABLE collection_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    collector TEXT NOT NULL,
    started_at TIMESTAMP NOT NULL,
    finished_at TIMESTAMP,
    status TEXT,                -- 'success', 'partial', 'failed'
    records_collected INTEGER,
    error_message TEXT
);
```

### Indexes

```sql
CREATE INDEX idx_observations_location_time ON observations(location_id, observed_at);
CREATE INDEX idx_observations_time ON observations(observed_at);
CREATE INDEX idx_forecasts_location_valid ON forecasts(location_id, valid_at);
CREATE INDEX idx_forecasts_source_issued ON forecasts(source, issued_at);
```

---

## Implementation Phases

### Phase 1: Foundation (Weeks 1-2)

**Objective**: Working data collection pipeline with storage.

1. Project scaffolding (pyproject.toml, flake.nix, directory structure)
2. Configuration system with location setup
3. SQLite database with schema
4. Open-Meteo collector (forecasts + historical)
5. Met Office DataPoint collector (observations)
6. Basic CLI: `haar collect`, `haar status`
7. Systemd timer for hourly collection

**Success Criteria**: Data flowing into database every hour, queryable via CLI.

### Phase 2: Station Discovery (Week 3)

**Objective**: Find and integrate nearby PWS stations.

1. Met Office WOW station discovery script
2. Weather Underground station discovery (if API accessible)
3. Station quality assessment (uptime, data completeness)
4. PWS collector implementation
5. Multi-station collection scheduling

**Success Criteria**: 5+ reliable stations identified and collecting.

### Phase 3: Terrain & Features (Week 4)

**Objective**: Compute static terrain features and implement feature engineering.

1. Download and process OS Terrain 50 (or SRTM)
2. Compute terrain features for all locations
3. Temporal feature engineering (lags, rolling means, time encoding)
4. Data quality module (outlier detection, gap identification)
5. Feature pipeline that produces ML-ready datasets

**Success Criteria**: Can generate feature matrix for any location/time range.

### Phase 4: Baseline Models (Weeks 5-6)

**Objective**: Establish baselines and first ML model.

1. Persistence baseline (tomorrow = today)
2. Climatological baseline (historical average for this day/hour)
3. Simple ML model (RandomForest or LightGBM)
4. Evaluation framework (MAE, RMSE, skill score vs baselines)
5. Comparison with Open-Meteo/Met Office forecasts
6. Basic forecast output: `haar forecast`

**Success Criteria**: ML model beats persistence; competitive with API forecasts.

### Phase 5: Iteration & Improvement (Ongoing)

**Objective**: Refine and extend.

1. Hyperparameter tuning
2. Additional data sources (ECMWF, ERA5)
3. Ensemble approaches
4. Nowcasting experiments (0-6 hour focus)
5. Visualisation improvements
6. Optional: Simple web dashboard

---

## Key Features to Engineer

### Temporal Features

| Feature | Description |
|---------|-------------|
| `hour_sin`, `hour_cos` | Cyclical encoding of hour |
| `day_of_year_sin`, `day_of_year_cos` | Cyclical encoding of season |
| `temp_lag_1h` to `temp_lag_24h` | Lagged observations |
| `temp_rolling_mean_6h` | Rolling averages |
| `temp_change_3h` | Rate of change |
| `pressure_tendency_3h` | Pressure trend (strong predictor) |

### Spatial/Terrain Features

| Feature | Description |
|---------|-------------|
| `elevation_m` | Station/location elevation |
| `slope_deg` | Terrain slope |
| `aspect_deg` | Which direction slope faces |
| `distance_to_coast_km` | Coastal influence |
| `terrain_roughness` | Local terrain variability |
| `is_valley` | Sheltered vs exposed |

### Weather-Derived Features

| Feature | Description |
|---------|-------------|
| `wind_u`, `wind_v` | Wind vector components |
| `dewpoint_c` | Computed from temp + humidity |
| `pressure_msl` | Corrected to sea level |
| `frontal_passage` | Detected from pressure/wind shifts |

---

## Configuration Example

```toml
# haar.toml

[location]
name = "Home"
latitude = 55.9533
longitude = -3.1883
radius_km = 200

[database]
path = "data/haar.db"

[collection]
interval_minutes = 60
backfill_days = 365

[sources.openmeteo]
enabled = true
models = ["ecmwf_ifs04", "gfs_seamless", "icon_seamless"]

[sources.metoffice]
enabled = true
api_key_env = "METOFFICE_API_KEY"

[sources.wow]
enabled = true
search_radius_km = 50
min_station_uptime = 0.8

[sources.terrain]
dataset = "os_terrain_50"  # or "srtm"
cache_dir = "data/terrain"

[models]
target_variables = ["temperature_c", "precipitation_mm", "wind_speed_ms"]
forecast_horizons_hours = [1, 3, 6, 12, 24, 48, 72]
```

---

## CLI Interface

```bash
# Setup and configuration
haar init                          # Interactive setup, creates config
haar config show                   # Display current configuration
haar config set location.latitude 55.95

# Data collection
haar collect                       # Run all collectors once
haar collect --source openmeteo    # Run specific collector
haar collect --backfill 30         # Backfill last 30 days
haar status                        # Show collection status, data gaps

# Station management
haar stations discover             # Find nearby PWS stations
haar stations list                 # Show known stations
haar stations add <id>             # Manually add a station
haar stations quality              # Assess station data quality

# Analysis and forecasting
haar forecast                      # Show forecast for home location
haar forecast --hours 48           # Specify horizon
haar compare                       # Compare Haar vs API forecasts
haar accuracy                      # Show model accuracy metrics

# Model management
haar train                         # Train/retrain models
haar train --target temperature_c  # Train specific variable
haar evaluate                      # Evaluate against test set

# Database
haar db stats                      # Database statistics
haar db export --format csv        # Export data
haar db vacuum                     # Clean up database
```

---

## Testing Strategy

### Unit Tests
- Collector parsing logic (mock API responses)
- Feature engineering calculations
- Data quality checks
- Database operations

### Integration Tests
- End-to-end collection with live APIs (rate-limited)
- Full pipeline from collection to prediction

### Validation
- Holdout test set (most recent N days)
- Cross-validation for model selection
- Comparison against persistence and API forecasts

---

## Success Metrics

| Metric | Target | Notes |
|--------|--------|-------|
| Data completeness | >95% hours covered | For primary location |
| Temperature MAE (24h) | <1.5°C | Beat persistence |
| Precipitation accuracy | >75% categorical | Rain/no-rain |
| Skill score vs persistence | >0.3 | Meaningful improvement |
| Competitive with Met Office | Within 20% MAE | At target location |

---

## GitHub Issues to Create

### Epic 1: Project Foundation
1. **Project scaffolding** - pyproject.toml, directory structure, flake.nix, README
2. **Configuration system** - TOML config loading, validation, environment variable support
3. **Database setup** - SQLite connection, schema creation, migrations approach
4. **CLI framework** - Click-based CLI with subcommands
5. **Logging setup** - Structured logging configuration

### Epic 2: Data Collection
6. **Collector base class** - Abstract interface for all collectors
7. **Open-Meteo collector** - Forecasts and historical data
8. **Met Office DataPoint collector** - Official UK observations
9. **Met Office WOW collector** - Personal weather station data
10. **Collection scheduler** - Systemd timer integration
11. **Collection status command** - Show what's been collected, gaps

### Epic 3: Station Discovery
12. **WOW station discovery** - Find stations within radius
13. **Station quality assessment** - Uptime, completeness, reliability scoring
14. **Station management CLI** - List, add, remove, assess stations

### Epic 4: Terrain & Features
15. **Terrain data acquisition** - Download and cache OS Terrain 50 / SRTM
16. **Terrain feature extraction** - Compute elevation, slope, aspect, etc.
17. **Temporal feature engineering** - Lags, rolling stats, cyclical encoding
18. **Data quality module** - Outlier detection, gap handling
19. **Feature pipeline** - Generate ML-ready datasets

### Epic 5: Modelling
20. **Baseline models** - Persistence and climatology
21. **Evaluation framework** - MAE, RMSE, skill scores, comparison tools
22. **ML model training** - LightGBM/RandomForest training pipeline
23. **Forecast generation** - Produce forecasts for target location
24. **Model versioning** - Track model runs and performance

### Epic 6: Analysis & Visualisation
25. **Accuracy reporting** - Model performance summaries
26. **Forecast comparison plots** - Haar vs API forecasts
27. **Data exploration tools** - Query and visualise collected data

---

## Development Notes

### NixOS Development Shell

```nix
{
  description = "Haar weather prediction";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python311;
        pythonPackages = python.pkgs;
      in {
        devShells.default = pkgs.mkShell {
          buildInputs = [
            python
            pythonPackages.pip
            pythonPackages.virtualenv
            pythonPackages.numpy
            pythonPackages.pandas
            pythonPackages.scikit-learn
            pythonPackages.requests
            pythonPackages.click
            pythonPackages.rich
            pythonPackages.pytest
            pkgs.sqlite
          ];
          
          shellHook = ''
            export HAAR_CONFIG="./config/haar.toml"
            echo "Haar development environment loaded"
          '';
        };
      });
}
```

### API Keys Required

| Service | Environment Variable | How to Get |
|---------|---------------------|------------|
| Met Office DataPoint | `METOFFICE_API_KEY` | Register at datahub.metoffice.gov.uk |
| Weather Underground | `WUNDERGROUND_API_KEY` | IBM Weather Company API (optional) |

### Data Volume Estimates

| Data Type | Frequency | Daily Records | Monthly Storage |
|-----------|-----------|---------------|-----------------|
| Observations (10 stations) | Hourly | 240 | ~5 MB |
| Forecasts (3 models) | 6-hourly | ~1,000 | ~20 MB |
| Historical backfill | Once | - | ~500 MB |

SQLite will handle this comfortably for years.

---

## References

- [Open-Meteo API Documentation](https://open-meteo.com/en/docs)
- [Met Office DataPoint](https://www.metoffice.gov.uk/services/data/datapoint)
- [Met Office WOW](https://wow.metoffice.gov.uk/)
- [ECMWF Open Data](https://www.ecmwf.int/en/forecasts/datasets/open-data)
- [OS Terrain 50](https://www.ordnancesurvey.co.uk/products/os-terrain-50)
- [LightGBM Documentation](https://lightgbm.readthedocs.io/)
- [Metpy - Meteorological Python](https://unidata.github.io/MetPy/)
