"""Streamlit dashboard for Haar weather data visualization."""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from typing import Optional, Tuple

from haar.config import get_config
from haar.storage import get_session, Observation, Forecast, Location, CollectionLog


# Time range options with hours and aggregation settings
TIME_RANGES = {
    "Today": {"hours": 24, "aggregate": False},
    "Week": {"hours": 168, "aggregate": False},
    "Month": {"hours": 720, "aggregate": True, "freq": "D"},  # Daily
    "3 Months": {"hours": 2160, "aggregate": True, "freq": "D"},  # Daily
}


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
                "precipitation_mm": obs.precipitation_mm,
                "visibility_m": obs.visibility_m,
            }
            for obs in observations
        ]

        return pd.DataFrame(data)


def aggregate_observations(df: pd.DataFrame, freq: str = "D") -> pd.DataFrame:
    """Aggregate observations to daily summaries with min/max/mean.

    Args:
        df: Raw observations DataFrame
        freq: Pandas frequency string ('D' for daily, 'H' for hourly)

    Returns:
        Aggregated DataFrame with mean, min, max columns
    """
    if df.empty:
        return df

    # Ensure observed_at is datetime
    df = df.copy()
    df["observed_at"] = pd.to_datetime(df["observed_at"])

    # Group by date and source
    df["date"] = df["observed_at"].dt.floor(freq)

    numeric_cols = ["temperature_c", "humidity_pct", "pressure_hpa",
                    "wind_speed_ms", "precipitation_mm"]

    # Aggregate with multiple functions
    agg_dict = {col: ["mean", "min", "max"] for col in numeric_cols if col in df.columns}
    agg_dict["observed_at"] = "count"  # Count observations

    grouped = df.groupby(["date", "source"]).agg(agg_dict).reset_index()

    # Flatten column names
    grouped.columns = [
        f"{col[0]}_{col[1]}" if col[1] and col[0] != "date" and col[0] != "source"
        else col[0]
        for col in grouped.columns
    ]

    # Rename count column
    if "observed_at_count" in grouped.columns:
        grouped = grouped.rename(columns={"observed_at_count": "observation_count"})

    return grouped


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


def plot_with_range(df: pd.DataFrame, x_col: str, y_col: str,
                    title: str, y_label: str, aggregated: bool = False) -> go.Figure:
    """Create a line plot, optionally with min/max range bands for aggregated data."""

    if aggregated and f"{y_col}_mean" in df.columns:
        # Aggregated data - show mean line with min/max bands
        fig = go.Figure()

        for source in df["source"].unique():
            source_df = df[df["source"] == source].sort_values("date")

            # Add min/max range as filled area
            fig.add_trace(go.Scatter(
                x=pd.concat([source_df["date"], source_df["date"][::-1]]),
                y=pd.concat([source_df[f"{y_col}_max"], source_df[f"{y_col}_min"][::-1]]),
                fill="toself",
                fillcolor=f"rgba(100, 100, 100, 0.2)",
                line=dict(color="rgba(255,255,255,0)"),
                name=f"{source} (range)",
                showlegend=False,
            ))

            # Add mean line
            fig.add_trace(go.Scatter(
                x=source_df["date"],
                y=source_df[f"{y_col}_mean"],
                mode="lines+markers",
                name=source,
            ))

        fig.update_layout(
            title=title,
            xaxis_title="Date",
            yaxis_title=y_label,
        )
        return fig
    else:
        # Raw data - simple line plot
        return px.line(
            df.sort_values(x_col),
            x=x_col,
            y=y_col,
            color="source",
            title=title,
            labels={y_col: y_label, x_col: "Time"},
        )


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

    # Time range selector
    time_range = st.sidebar.selectbox(
        "Time Range",
        options=list(TIME_RANGES.keys()),
        index=1,  # Default to "Week"
    )
    range_config = TIME_RANGES[time_range]

    # Source filter
    source_filter = st.sidebar.multiselect(
        "Data Sources",
        options=["netatmo", "metoffice_datahub", "era5_reanalysis"],
        default=["netatmo", "metoffice_datahub", "era5_reanalysis"],
    )

    auto_refresh = st.sidebar.checkbox("Auto-refresh (60s)", value=False)

    if auto_refresh:
        st.experimental_rerun()

    # Stats overview
    stats = get_collection_stats()

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Observations", f"{stats['observations']:,}")
    with col2:
        st.metric("Forecasts", f"{stats['forecasts']:,}")
    with col3:
        st.metric("Locations", stats['locations'])
    with col4:
        st.metric("Time Range", time_range)

    st.divider()

    # Tabs for different views
    tab1, tab2, tab3, tab4 = st.tabs(["📊 Observations", "🔮 Forecasts", "📍 Locations", "📋 Collection Logs"])

    with tab1:
        st.header("Weather Observations")

        # Show aggregation info
        if range_config["aggregate"]:
            st.info(f"📊 Showing daily aggregates (mean with min/max range) for {time_range}")

        obs_df = get_observations_df(range_config["hours"])

        # Filter by source
        if not obs_df.empty and source_filter:
            obs_df = obs_df[obs_df["source"].isin(source_filter)]

        if obs_df.empty:
            st.warning("No observations found. Run `haar collect run` to collect data.")
        else:
            # Aggregate if needed
            if range_config["aggregate"]:
                display_df = aggregate_observations(obs_df, range_config["freq"])
                x_col = "date"
            else:
                display_df = obs_df
                x_col = "observed_at"

            # Temperature chart
            st.subheader("Temperature")
            fig_temp = plot_with_range(
                display_df, x_col, "temperature_c",
                "Temperature Over Time", "Temperature (°C)",
                aggregated=range_config["aggregate"]
            )
            st.plotly_chart(fig_temp, width="stretch")

            # Multi-variable chart
            col1, col2 = st.columns(2)

            with col1:
                st.subheader("Humidity")
                fig_hum = plot_with_range(
                    display_df, x_col, "humidity_pct",
                    "Humidity Over Time", "Humidity (%)",
                    aggregated=range_config["aggregate"]
                )
                st.plotly_chart(fig_hum, width="stretch")

            with col2:
                st.subheader("Pressure")
                fig_pres = plot_with_range(
                    display_df, x_col, "pressure_hpa",
                    "Pressure Over Time", "Pressure (hPa)",
                    aggregated=range_config["aggregate"]
                )
                st.plotly_chart(fig_pres, width="stretch")

            # Wind
            st.subheader("Wind Speed")
            fig_wind = plot_with_range(
                display_df, x_col, "wind_speed_ms",
                "Wind Speed Over Time", "Wind Speed (m/s)",
                aggregated=range_config["aggregate"]
            )
            st.plotly_chart(fig_wind, width="stretch")

            # Summary stats
            if range_config["aggregate"]:
                st.subheader("Summary Statistics")
                col1, col2, col3 = st.columns(3)

                with col1:
                    if "temperature_c_mean" in display_df.columns:
                        avg_temp = display_df["temperature_c_mean"].mean()
                        min_temp = display_df["temperature_c_min"].min()
                        max_temp = display_df["temperature_c_max"].max()
                        st.metric("Avg Temperature", f"{avg_temp:.1f}°C")
                        st.caption(f"Range: {min_temp:.1f}°C to {max_temp:.1f}°C")

                with col2:
                    if "humidity_pct_mean" in display_df.columns:
                        avg_hum = display_df["humidity_pct_mean"].mean()
                        st.metric("Avg Humidity", f"{avg_hum:.0f}%")

                with col3:
                    if "observation_count" in display_df.columns:
                        total_obs = display_df["observation_count"].sum()
                        st.metric("Total Observations", f"{int(total_obs):,}")

            # Raw data table
            with st.expander("View Data"):
                st.dataframe(display_df, width="stretch")

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
            # Filter by source
            loc_sources = loc_df["source"].unique().tolist()
            selected_sources = st.multiselect(
                "Filter by source",
                options=loc_sources,
                default=loc_sources,
            )
            filtered_loc_df = loc_df[loc_df["source"].isin(selected_sources)]

            # Map
            st.subheader(f"Station Map ({len(filtered_loc_df)} locations)")
            st.map(filtered_loc_df, latitude="latitude", longitude="longitude")

            # Table
            st.subheader("Location Details")
            st.dataframe(filtered_loc_df, width="stretch")

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
