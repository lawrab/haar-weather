"""Streamlit dashboard for Haar weather data visualization."""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from typing import Optional

from haar.config import get_config
from haar.storage import get_session, Observation, Forecast, Location, CollectionLog


def get_observations_df(hours: int = 72) -> pd.DataFrame:
    """Fetch observations from database as DataFrame."""
    cutoff = datetime.utcnow() - timedelta(hours=hours)

    with get_session() as session:
        observations = (
            session.query(Observation)
            .filter(Observation.observed_at >= cutoff)
            .order_by(Observation.observed_at.desc())
            .all()
        )

        if not observations:
            return pd.DataFrame()

        data = [
            {
                "observed_at": obs.observed_at,
                "location_id": obs.location_id,
                "source": obs.source,
                "temperature_c": obs.temperature_c,
                "humidity_pct": obs.humidity_pct,
                "pressure_hpa": obs.pressure_hpa,
                "wind_speed_ms": obs.wind_speed_ms,
                "wind_direction_deg": obs.wind_direction_deg,
                "visibility_m": obs.visibility_m,
            }
            for obs in observations
        ]

        return pd.DataFrame(data)


def get_forecasts_df(hours: int = 168) -> pd.DataFrame:
    """Fetch forecasts from database as DataFrame."""
    cutoff = datetime.utcnow() - timedelta(hours=24)

    with get_session() as session:
        forecasts = (
            session.query(Forecast)
            .filter(Forecast.issued_at >= cutoff)
            .order_by(Forecast.valid_at.asc())
            .all()
        )

        if not forecasts:
            return pd.DataFrame()

        data = [
            {
                "issued_at": fc.issued_at,
                "valid_at": fc.valid_at,
                "location_id": fc.location_id,
                "source": fc.source,
                "lead_time_hours": fc.lead_time_hours,
                "temperature_c": fc.temperature_c,
                "humidity_pct": fc.humidity_pct,
                "pressure_hpa": fc.pressure_hpa,
                "wind_speed_ms": fc.wind_speed_ms,
                "precipitation_mm": fc.precipitation_mm,
                "cloud_cover_pct": fc.cloud_cover_pct,
            }
            for fc in forecasts
        ]

        return pd.DataFrame(data)


def get_locations_df() -> pd.DataFrame:
    """Fetch locations from database as DataFrame."""
    with get_session() as session:
        locations = session.query(Location).all()

        if not locations:
            return pd.DataFrame()

        data = [
            {
                "id": loc.id,
                "name": loc.name,
                "latitude": loc.latitude,
                "longitude": loc.longitude,
                "location_type": loc.location_type,
                "source": loc.source,
            }
            for loc in locations
        ]

        return pd.DataFrame(data)


def get_collection_stats() -> dict:
    """Get collection statistics."""
    with get_session() as session:
        obs_count = session.query(Observation).count()
        forecast_count = session.query(Forecast).count()
        location_count = session.query(Location).count()

        # Recent collection logs
        recent_logs = (
            session.query(CollectionLog)
            .order_by(CollectionLog.started_at.desc())
            .limit(10)
            .all()
        )

        return {
            "observations": obs_count,
            "forecasts": forecast_count,
            "locations": location_count,
            "recent_logs": recent_logs,
        }


def main():
    """Main dashboard entry point."""
    st.set_page_config(
        page_title="Haar Weather Dashboard",
        page_icon="🌫️",
        layout="wide",
    )

    st.title("🌫️ Haar Weather Dashboard")
    st.caption("Hyperlocal Scottish Weather Prediction System")

    # Sidebar
    st.sidebar.header("Settings")
    obs_hours = st.sidebar.slider("Observation history (hours)", 24, 168, 72)
    auto_refresh = st.sidebar.checkbox("Auto-refresh (60s)", value=False)

    if auto_refresh:
        st.experimental_rerun()

    # Stats overview
    stats = get_collection_stats()

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Observations", f"{stats['observations']:,}")
    with col2:
        st.metric("Forecasts", f"{stats['forecasts']:,}")
    with col3:
        st.metric("Locations", stats['locations'])

    st.divider()

    # Tabs for different views
    tab1, tab2, tab3, tab4 = st.tabs(["📊 Observations", "🔮 Forecasts", "📍 Locations", "📋 Collection Logs"])

    with tab1:
        st.header("Weather Observations")

        obs_df = get_observations_df(obs_hours)

        if obs_df.empty:
            st.warning("No observations found. Run `haar collect run --source metoffice` to collect data.")
        else:
            # Temperature chart
            st.subheader("Temperature")
            fig_temp = px.line(
                obs_df.sort_values("observed_at"),
                x="observed_at",
                y="temperature_c",
                color="source",
                title="Temperature Over Time",
                labels={"temperature_c": "Temperature (°C)", "observed_at": "Time"},
            )
            st.plotly_chart(fig_temp, width="stretch")

            # Multi-variable chart
            col1, col2 = st.columns(2)

            with col1:
                st.subheader("Humidity")
                fig_hum = px.line(
                    obs_df.sort_values("observed_at"),
                    x="observed_at",
                    y="humidity_pct",
                    color="source",
                    labels={"humidity_pct": "Humidity (%)", "observed_at": "Time"},
                )
                st.plotly_chart(fig_hum, width="stretch")

            with col2:
                st.subheader("Pressure")
                fig_pres = px.line(
                    obs_df.sort_values("observed_at"),
                    x="observed_at",
                    y="pressure_hpa",
                    color="source",
                    labels={"pressure_hpa": "Pressure (hPa)", "observed_at": "Time"},
                )
                st.plotly_chart(fig_pres, width="stretch")

            # Wind
            st.subheader("Wind")
            col1, col2 = st.columns(2)

            with col1:
                fig_wind = px.line(
                    obs_df.sort_values("observed_at"),
                    x="observed_at",
                    y="wind_speed_ms",
                    color="source",
                    labels={"wind_speed_ms": "Wind Speed (m/s)", "observed_at": "Time"},
                )
                st.plotly_chart(fig_wind, width="stretch")

            with col2:
                # Wind rose / direction scatter
                fig_dir = px.scatter(
                    obs_df.sort_values("observed_at"),
                    x="observed_at",
                    y="wind_direction_deg",
                    color="source",
                    labels={"wind_direction_deg": "Wind Direction (°)", "observed_at": "Time"},
                )
                st.plotly_chart(fig_dir, width="stretch")

            # Raw data table
            with st.expander("View Raw Data"):
                st.dataframe(obs_df, width="stretch")

    with tab2:
        st.header("Weather Forecasts")

        fc_df = get_forecasts_df()

        if fc_df.empty:
            st.warning("No forecasts found. Run `haar collect run --source openmeteo` to collect data.")
        else:
            # Temperature forecast
            st.subheader("Temperature Forecast")
            fig_fc_temp = px.line(
                fc_df.sort_values("valid_at"),
                x="valid_at",
                y="temperature_c",
                color="source",
                title="Temperature Forecast",
                labels={"temperature_c": "Temperature (°C)", "valid_at": "Valid Time"},
            )
            # Add vertical line for now
            now = datetime.utcnow()
            fig_fc_temp.add_shape(
                type="line",
                x0=now, x1=now,
                y0=0, y1=1,
                yref="paper",
                line=dict(color="red", dash="dash"),
            )
            fig_fc_temp.add_annotation(x=now, y=1, yref="paper", text="Now", showarrow=False)
            st.plotly_chart(fig_fc_temp, width="stretch")

            col1, col2 = st.columns(2)

            with col1:
                st.subheader("Precipitation")
                fig_precip = px.bar(
                    fc_df.sort_values("valid_at"),
                    x="valid_at",
                    y="precipitation_mm",
                    color="source",
                    labels={"precipitation_mm": "Precipitation (mm)", "valid_at": "Valid Time"},
                )
                st.plotly_chart(fig_precip, width="stretch")

            with col2:
                st.subheader("Cloud Cover")
                fig_cloud = px.area(
                    fc_df.sort_values("valid_at"),
                    x="valid_at",
                    y="cloud_cover_pct",
                    color="source",
                    labels={"cloud_cover_pct": "Cloud Cover (%)", "valid_at": "Valid Time"},
                )
                st.plotly_chart(fig_cloud, width="stretch")

            # Raw data table
            with st.expander("View Raw Data"):
                st.dataframe(fc_df, width="stretch")

    with tab3:
        st.header("Data Locations")

        loc_df = get_locations_df()

        if loc_df.empty:
            st.warning("No locations found.")
        else:
            # Map
            st.subheader("Station Map")
            st.map(loc_df, latitude="latitude", longitude="longitude")

            # Table
            st.subheader("Location Details")
            st.dataframe(loc_df, width="stretch")

    with tab4:
        st.header("Collection Logs")

        logs = stats.get("recent_logs", [])

        if not logs:
            st.info("No collection logs yet.")
        else:
            log_data = [
                {
                    "Started": log.started_at,
                    "Finished": log.finished_at,
                    "Collector": log.collector,
                    "Status": log.status,
                    "Records": log.records_collected,
                    "Error": log.error_message or "",
                }
                for log in logs
            ]
            st.dataframe(pd.DataFrame(log_data), width="stretch")

    # Footer
    st.divider()
    st.caption(f"Last updated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")


if __name__ == "__main__":
    main()
