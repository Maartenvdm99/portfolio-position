import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import date, time, timedelta

st.set_page_config(page_title="Portfolio Position Dashboard", layout="wide")

# ── CSS for thick vertical borders between column groups ─────────────────
# Column groups (0-indexed columns in the data_editor / dataframe):
#   A-D (0-3): Summary         → thick right border on col 3
#   E   (4):   ID trades       → thick right border on col 4
#   F   (5):   DA position     → thick right border on col 5
#   G-I (6-8): Solar           → thick right border on col 8
#   J-L (9-11): Wind           → thick right border on col 11
#   M-O (12-14): Nowcast       → thick right border on col 14
#   P-R (15-17): LargePV       → thick right border on col 17
#   S   (18): Flex
# For data_editor the column indices shift by 1 due to the checkbox column being hidden
THICK_BORDER_CSS = """
<style>
/* Thick vertical borders for st.dataframe (Position overview styled table) */
div[data-testid="stDataFrame"] table td:nth-child(4),
div[data-testid="stDataFrame"] table th:nth-child(4),
div[data-testid="stDataFrame"] table td:nth-child(5),
div[data-testid="stDataFrame"] table th:nth-child(5),
div[data-testid="stDataFrame"] table td:nth-child(6),
div[data-testid="stDataFrame"] table th:nth-child(6),
div[data-testid="stDataFrame"] table td:nth-child(9),
div[data-testid="stDataFrame"] table th:nth-child(9),
div[data-testid="stDataFrame"] table td:nth-child(12),
div[data-testid="stDataFrame"] table th:nth-child(12),
div[data-testid="stDataFrame"] table td:nth-child(15),
div[data-testid="stDataFrame"] table th:nth-child(15),
div[data-testid="stDataFrame"] table td:nth-child(18),
div[data-testid="stDataFrame"] table th:nth-child(18) {
    border-right: 3px solid #333 !important;
}

/* Thick borders for the glide-data-grid used by data_editor and dataframe */
</style>
"""

st.markdown(THICK_BORDER_CSS, unsafe_allow_html=True)

st.title("Portfolio Position Dashboard")

# ── Date selector at the top ──────────────────────────────────────────────
selected_date = st.date_input("Select day", value=date(2026, 3, 17))

# ── Helper: build the 96 PTU time slots for the selected date ─────────────
def build_time_slots(d: date) -> list[str]:
    """Return 96 quarter-hour labels like '17-03-2026 00:00-00:15'."""
    slots = []
    for ptu in range(96):
        start_min = ptu * 15
        end_min = start_min + 15
        sh, sm = divmod(start_min, 60)
        eh, em = divmod(end_min, 60)
        # PTU 96 wraps to 00:00 next day
        if eh == 24:
            eh = 0
        label = f"{d.strftime('%d-%m-%Y')} {sh:02d}:{sm:02d}-{eh:02d}:{em:02d}"
        slots.append(label)
    return slots


# ── Load example data from the Excel file ─────────────────────────────────
EXCEL_PATH = "Dashboard portfolio position.xlsx"


@st.cache_data
def load_excel():
    """Read all sheets once and return raw DataFrames."""
    return {
        "Position overview": pd.read_excel(EXCEL_PATH, sheet_name="Position overview"),
        "Wind": pd.read_excel(EXCEL_PATH, sheet_name="Wind"),
        "Solar": pd.read_excel(EXCEL_PATH, sheet_name="Solar"),
        "EXPOST": pd.read_excel(EXCEL_PATH, sheet_name="EXPOST", header=None),
    }


raw = load_excel()

# ── Check if selected date has data (Excel date or generated dates) ────────
excel_date = date(2026, 3, 17)  # the date in the example file
supported_dates = {date(2026, 3, 17), date(2026, 3, 18)}
has_data = selected_date in supported_dates


def generate_random_data(n_rows: int, seed: int) -> dict:
    """Generate realistic random portfolio data for n_rows PTUs."""
    rng = np.random.default_rng(seed)
    # Hour-of-day pattern: higher during day, lower at night
    hours = np.array([i // 4 for i in range(n_rows)])
    day_factor = np.where((hours >= 7) & (hours <= 20), 1.0, 0.4)

    wind_da = rng.uniform(400, 700, n_rows) * day_factor
    wind_real = wind_da + rng.normal(0, 30, n_rows)
    nowcast_da = rng.uniform(50, 200, n_rows) * day_factor
    nowcast_real = nowcast_da + rng.normal(0, 15, n_rows)
    largepv_da = rng.uniform(30, 150, n_rows) * np.where((hours >= 6) & (hours <= 19), 1.0, 0.0)
    largepv_real = largepv_da + rng.normal(0, 10, n_rows) * np.where(largepv_da > 0, 1, 0)
    da_position = rng.uniform(-20, 20, n_rows)
    id_trades = rng.uniform(-15, 15, n_rows)
    flex = rng.uniform(-5, 5, n_rows)

    return {
        "ID trades": id_trades,
        "DA position": da_position,
        "Wind DA": wind_da,
        "Wind realization": wind_real,
        "Wind realization overwrite": np.zeros(n_rows),
        "Nowcast DA sold": nowcast_da,
        "Nowcast realization": nowcast_real,
        "Nowcast realization overwrite": np.zeros(n_rows),
        "LargePV DA sold": largepv_da,
        "total largepv realization": largepv_real,
        "total largepv realization overwrite": np.zeros(n_rows),
        "Flex": flex,
    }

time_slots = build_time_slots(selected_date)
ptus = list(range(1, 97))


# =====================================================================
# TAB DEFINITIONS
# =====================================================================
tab_overview, tab_wind, tab_solar, tab_expost = st.tabs(
    ["Position overview", "Wind", "Solar", "EXPOST"]
)

# ── 1) Position overview ─────────────────────────────────────────────────
with tab_overview:
    if has_data:
        # Build a clean 96-row frame with the right column order
        df = pd.DataFrame()
        df["PTU"] = ptus
        df["Time"] = time_slots

        value_cols = [
            "ID trades", "DA position",
            "Wind DA", "Wind realization", "Wind realization overwrite",
            "Nowcast DA sold", "Nowcast realization", "Nowcast realization overwrite",
            "LargePV DA sold", "total largepv realization", "total largepv realization overwrite",
            "Flex",
        ]

        if selected_date == excel_date:
            # Load Excel data for the first 4 PTUs, fill rest with random
            df_src = raw["Position overview"].copy()
            for col in value_cols:
                if col in df_src.columns:
                    series = df_src[col].reindex(range(96))
                    df[col] = pd.to_numeric(series, errors="coerce").astype(float)
                else:
                    df[col] = np.nan

            # Fill remaining PTUs (rows 4-95) with random data
            rand = generate_random_data(96, seed=20260317)
            for col in value_cols:
                mask = df[col].isna()
                df.loc[mask, col] = pd.Series(rand[col])[mask].values
            df[value_cols] = df[value_cols].fillna(0.0)

            # Total ID position realization from Excel
            if "Total ID position realization" in df_src.columns:
                realization = df_src["Total ID position realization"].reindex(range(96))
                df["Total ID position realization"] = pd.to_numeric(realization, errors="coerce").fillna(0).astype(float)
            else:
                df["Total ID position realization"] = 0.0
        else:
            # Fully generated day (18-3-2026)
            rand = generate_random_data(96, seed=20260318)
            for col in value_cols:
                df[col] = rand[col]
            df["Total ID position realization"] = 0.0

        # ── Editable overwrite columns ──────────────────────────────────
        overwrite_col_names = [
            "Wind realization overwrite",
            "Nowcast realization overwrite",
            "total largepv realization overwrite",
        ]
        for ow_col in overwrite_col_names:
            state_key = f"ow_{ow_col}"
            if state_key not in st.session_state:
                st.session_state[state_key] = df[ow_col].tolist()
            else:
                # Apply previously edited values from session state
                df[ow_col] = pd.Series(st.session_state[state_key]).astype(float)

        # ── Recalculate derived columns using (potentially edited) overwrites ──
        # Overwrite logic: if overwrite != 0 use it, else use realization
        df["Wind eff"] = df["Wind realization overwrite"].where(
            df["Wind realization overwrite"] != 0, df["Wind realization"]
        )
        df["Nowcast eff"] = df["Nowcast realization overwrite"].where(
            df["Nowcast realization overwrite"] != 0, df["Nowcast realization"]
        )
        df["LargePV eff"] = df["total largepv realization overwrite"].where(
            df["total largepv realization overwrite"] != 0, df["total largepv realization"]
        )

        # Solar delta (H) = (Nowcast eff - Nowcast DA) + (LargePV eff - LargePV DA)
        df["Solar delta"] = (
            (df["Nowcast eff"] - df["Nowcast DA sold"])
            + (df["LargePV eff"] - df["LargePV DA sold"])
        )

        # Solar position H2H (G) = rolling 4-PTU average of Solar delta (per hour block)
        hour_block = [i // 4 for i in range(96)]
        df["_hour_block"] = hour_block
        df["Solar position H2H"] = df.groupby("_hour_block")["Solar delta"].transform("mean")

        # hvsQ (I) = Solar delta - Solar position H2H
        df["hvsQ"] = df["Solar delta"] - df["Solar position H2H"]

        # Total ID position forecast (C)
        df["Total ID position forecast"] = (
            df["ID trades"]
            + (df["Wind eff"] - df["Wind DA"])
            + (df["Nowcast eff"] - df["Nowcast DA sold"])
            + (df["LargePV eff"] - df["LargePV DA sold"])
            + df["DA position"]
        )

        # ── Assemble display dataframe with thick-border CSS classes ────
        display = pd.DataFrame()
        display["PTU"] = df["PTU"]
        display["Time"] = df["Time"]
        display["Total ID position forecast"] = df["Total ID position forecast"]
        display["Total ID position realization"] = df["Total ID position realization"]
        display["ID trades"] = df["ID trades"]
        display["DA position"] = df["DA position"]
        display["Solar position H2H"] = df["Solar position H2H"]
        display["Solar delta"] = df["Solar delta"]
        display["hvsQ"] = df["hvsQ"]
        display["Wind DA"] = df["Wind DA"]
        display["Wind realization"] = df["Wind realization"]
        display["Wind realization overwrite"] = df["Wind realization overwrite"]
        display["Nowcast DA sold"] = df["Nowcast DA sold"]
        display["Nowcast realization"] = df["Nowcast realization"]
        display["Nowcast realization overwrite"] = df["Nowcast realization overwrite"]
        display["LargePV DA sold"] = df["LargePV DA sold"]
        display["total largepv realization"] = df["total largepv realization"]
        display["total largepv realization overwrite"] = df["total largepv realization overwrite"]
        display["Flex"] = df["Flex"]

        # Columns that get thick right borders (0-indexed positions in display)
        # Total ID position realization (col 3), ID trades (4), DA position (5),
        # hvsQ (8), Wind realization overwrite (11), Nowcast realization overwrite (14),
        # total largepv realization overwrite (17)
        thick_border_cols = {
            "Total ID position realization",
            "ID trades",
            "DA position",
            "hvsQ",
            "Wind realization overwrite",
            "Nowcast realization overwrite",
            "total largepv realization overwrite",
        }
        bold_cols = ["Total ID position forecast", "Total ID position realization"]
        overwrite_cols = [
            "Wind realization overwrite",
            "Nowcast realization overwrite",
            "total largepv realization overwrite",
        ]

        def highlight_columns(row):
            styles = [""] * len(row)
            for i, col in enumerate(row.index):
                parts = []
                if col in bold_cols:
                    parts.append("font-weight: bold")
                if col in overwrite_cols:
                    parts.append("background-color: #FFF2CC")
                if col in thick_border_cols:
                    parts.append("border-right: 3px solid #333")
                styles[i] = "; ".join(parts)
            return styles

        st.subheader("Position overview")

        # Separate editor for overwrite columns
        edit_df = pd.DataFrame({
            "PTU": df["PTU"],
            "Time": df["Time"],
            "Wind realization overwrite": df["Wind realization overwrite"],
            "Nowcast realization overwrite": df["Nowcast realization overwrite"],
            "total largepv realization overwrite": df["total largepv realization overwrite"],
        })

        st.caption("Edit overwrite values below (yellow columns)")
        edited = st.data_editor(
            edit_df,
            use_container_width=False,
            height=300,
            hide_index=True,
            num_rows="fixed",
            disabled=["PTU", "Time"],
            key="overwrite_editor",
        )

        # Save edits back to session state and df
        for ow_col in overwrite_col_names:
            st.session_state[f"ow_{ow_col}"] = edited[ow_col].tolist()
            df[ow_col] = edited[ow_col].astype(float)
            display[ow_col] = edited[ow_col].astype(float)

        styled = display.style.apply(highlight_columns, axis=1).format(precision=1)
        st.dataframe(styled, use_container_width=True, height=700, hide_index=True)

        # Store chart data in session state so we can render charts outside the tab
        df["Wind delta"] = df["Wind eff"] - df["Wind DA"]
        st.session_state["chart_data"] = {
            "x_labels": [s.split(" ")[-1] for s in time_slots],
            "forecast": df["Total ID position forecast"].tolist(),
            "id_trades": df["ID trades"].tolist(),
            "da_position": df["DA position"].tolist(),
            "solar_delta": df["Solar delta"].tolist(),
            "wind_delta": df["Wind delta"].tolist(),
            "flex": df["Flex"].tolist(),
        }
    else:
        st.info(f"No data available for {selected_date.strftime('%d-%m-%Y')}. Example data is for 17-03-2026 and 18-03-2026.")

# ── 2) Wind ──────────────────────────────────────────────────────────────
with tab_wind:
    if has_data:
        df_w = pd.DataFrame()
        df_w["PTU"] = ptus
        df_w["Time"] = time_slots

        wind_cols = ["Wind DA", "Wind parks with realization", "Wind parks with no realization"]

        if selected_date == excel_date:
            df_src = raw["Wind"].copy()
            for col in wind_cols:
                if col in df_src.columns:
                    series = df_src[col].reindex(range(96))
                    df_w[col] = pd.to_numeric(series, errors="coerce").astype(float)
                else:
                    df_w[col] = np.nan
            # Fill remaining with random
            rng_w = np.random.default_rng(170317)
            hours = np.array([i // 4 for i in range(96)])
            day_f = np.where((hours >= 7) & (hours <= 20), 1.0, 0.5)
            rand_wind = {
                "Wind DA": rng_w.uniform(400, 700, 96) * day_f,
                "Wind parks with realization": rng_w.uniform(300, 600, 96) * day_f,
                "Wind parks with no realization": rng_w.uniform(50, 150, 96) * day_f,
            }
            for col in wind_cols:
                mask = df_w[col].isna()
                df_w.loc[mask, col] = pd.Series(rand_wind[col])[mask].values
            df_w[wind_cols] = df_w[wind_cols].fillna(0.0)
        else:
            rng_w = np.random.default_rng(180318)
            hours = np.array([i // 4 for i in range(96)])
            day_f = np.where((hours >= 7) & (hours <= 20), 1.0, 0.5)
            df_w["Wind DA"] = rng_w.uniform(400, 700, 96) * day_f
            df_w["Wind parks with realization"] = rng_w.uniform(300, 600, 96) * day_f
            df_w["Wind parks with no realization"] = rng_w.uniform(50, 150, 96) * day_f

        df_w["Wind total expected realization"] = (
            df_w["Wind parks with realization"] + df_w["Wind parks with no realization"]
        )
        df_w["Wind delta"] = df_w["Wind total expected realization"] - df_w["Wind DA"]

        st.dataframe(df_w, use_container_width=True, height=700, hide_index=True)
    else:
        st.info(f"No data available for {selected_date.strftime('%d-%m-%Y')}. Example data is for 17-03-2026 and 18-03-2026.")

# ── 3) Solar ─────────────────────────────────────────────────────────────
with tab_solar:
    if has_data:
        df_s = pd.DataFrame()
        df_s["PTU"] = ptus
        df_s["Time"] = time_slots

        solar_cols = [
            "LargePV DA sold",
            "Large pv realization",
            "Large PV park estimation (parks with no realization)",
            "total largepv expected realization",
            "Nowcast DA sold",
            "Nowcast realization",
        ]

        if selected_date == excel_date:
            df_src = raw["Solar"].copy()
            for col in solar_cols:
                if col in df_src.columns:
                    series = df_src[col].reindex(range(96))
                    df_s[col] = pd.to_numeric(series, errors="coerce").astype(float)
                else:
                    df_s[col] = np.nan
            # Fill remaining with random
            rng_s = np.random.default_rng(170317_2)
            hours = np.array([i // 4 for i in range(96)])
            sun_f = np.where((hours >= 6) & (hours <= 19), 1.0, 0.0)
            rand_solar = {
                "LargePV DA sold": rng_s.uniform(30, 150, 96) * sun_f,
                "Large pv realization": rng_s.uniform(25, 140, 96) * sun_f,
                "Large PV park estimation (parks with no realization)": rng_s.uniform(5, 30, 96) * sun_f,
                "total largepv expected realization": np.zeros(96),  # computed below
                "Nowcast DA sold": rng_s.uniform(50, 200, 96) * sun_f,
                "Nowcast realization": rng_s.uniform(45, 190, 96) * sun_f,
            }
            for col in solar_cols:
                mask = df_s[col].isna()
                df_s.loc[mask, col] = pd.Series(rand_solar[col])[mask].values
            df_s[solar_cols] = df_s[solar_cols].fillna(0.0)
        else:
            rng_s = np.random.default_rng(180318_2)
            hours = np.array([i // 4 for i in range(96)])
            sun_f = np.where((hours >= 6) & (hours <= 19), 1.0, 0.0)
            df_s["LargePV DA sold"] = rng_s.uniform(30, 150, 96) * sun_f
            df_s["Large pv realization"] = rng_s.uniform(25, 140, 96) * sun_f
            df_s["Large PV park estimation (parks with no realization)"] = rng_s.uniform(5, 30, 96) * sun_f
            df_s["total largepv expected realization"] = 0.0
            df_s["Nowcast DA sold"] = rng_s.uniform(50, 200, 96) * sun_f
            df_s["Nowcast realization"] = rng_s.uniform(45, 190, 96) * sun_f

        # Compute total largepv expected realization
        df_s["total largepv expected realization"] = (
            df_s["Large pv realization"]
            + df_s["Large PV park estimation (parks with no realization)"]
        )

        st.dataframe(df_s, use_container_width=True, height=700, hide_index=True)
    else:
        st.info(f"No data available for {selected_date.strftime('%d-%m-%Y')}. Example data is for 17-03-2026 and 18-03-2026.")

# ── 4) EXPOST (ETPA) ────────────────────────────────────────────────────
with tab_expost:
    if has_data:
        # Build the EXPOST / ETPA table
        df_e = pd.DataFrame()
        df_e["PTE"] = ptus

        start_times = []
        end_times = []
        for ptu in range(96):
            start_min = ptu * 15
            end_min = start_min + 15
            sh, sm = divmod(start_min, 60)
            eh, em = divmod(end_min, 60)
            if eh == 24:
                eh = 0
            start_times.append(f"{sh:02d}:{sm:02d}")
            end_times.append(f"{eh:02d}:{em:02d}")

        df_e["start"] = start_times
        df_e["end"] = end_times

        # Buy columns
        df_e["buy E/MWh"] = ""
        df_e["buy MW"] = ""
        df_e["buy status"] = "Fill in price!"

        # Sell columns
        df_e["sell E/MWh"] = ""
        df_e["sell MW"] = ""
        df_e["sell status"] = "Fill in price!"

        def highlight_fill_in(row):
            styles = [""] * len(row)
            for i, col in enumerate(row.index):
                if col in ("buy status", "sell status"):
                    styles[i] = "color: #CC0000; font-style: italic"
            return styles

        styled_e = df_e.style.apply(highlight_fill_in, axis=1)

        # Export CSV button
        csv_data = df_e.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Export CSV",
            data=csv_data,
            file_name=f"EXPOST_{selected_date.strftime('%Y-%m-%d')}.csv",
            mime="text/csv",
        )

        st.dataframe(styled_e, use_container_width=True, height=700, hide_index=True)
    else:
        st.info(f"No data available for {selected_date.strftime('%d-%m-%Y')}. Example data is for 17-03-2026 and 18-03-2026.")

# =====================================================================
# CHARTS (rendered outside tabs so they're always visible below)
# =====================================================================
if has_data and "chart_data" in st.session_state:
    cd = st.session_state["chart_data"]
    x_labels = cd["x_labels"]

    st.markdown("---")

    # Combined chart: stacked bar breakdown + total forecast line
    st.subheader("Position breakdown")
    fig = go.Figure()
    stack_components = [
        ("ID trades", cd["id_trades"], "#1f77b4"),
        ("DA position", cd["da_position"], "#ff7f0e"),
        ("Solar delta", cd["solar_delta"], "#2ca02c"),
        ("Wind delta", cd["wind_delta"], "#d62728"),
        ("Flex", cd["flex"], "#9467bd"),
    ]
    for name, values, color in stack_components:
        fig.add_trace(go.Bar(
            x=x_labels,
            y=values,
            name=name,
            marker_color=color,
        ))
    # Total forecast line on top – white and extra thick
    fig.add_trace(go.Scatter(
        x=x_labels,
        y=cd["forecast"],
        mode="lines",
        name="Total ID position forecast",
        line=dict(color="white", width=4),
    ))
    fig.update_layout(
        barmode="relative",
        xaxis_title="Time",
        yaxis_title="MW",
        height=450,
        margin=dict(l=40, r=20, t=30, b=40),
        xaxis=dict(tickangle=-45, dtick=4),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        plot_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, use_container_width=True)
