import streamlit as st
import pandas as pd
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

# ── Check if selected date matches the Excel data date ────────────────────
excel_date = date(2026, 3, 17)  # the date in the example file
has_data = selected_date == excel_date

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
        df_src = raw["Position overview"].copy()

        # Build a clean 96-row frame with the right column order
        df = pd.DataFrame()
        df["PTU"] = ptus
        df["Time"] = time_slots

        # Raw value columns from Excel (rows 0-3 have data, rest is NaN)
        value_cols = [
            "ID trades", "DA position",
            "Wind DA", "Wind realization", "Wind realization overwrite",
            "Nowcast DA sold", "Nowcast realization", "Nowcast realization overwrite",
            "LargePV DA sold", "total largepv realization", "total largepv realization overwrite",
            "Flex",
        ]
        for col in value_cols:
            if col in df_src.columns:
                series = df_src[col].reindex(range(96))
                df[col] = pd.to_numeric(series, errors="coerce").fillna(0).astype(float)
            else:
                df[col] = 0.0

        # Total ID position realization (from Excel, static values)
        if "Total ID position realization" in df_src.columns:
            realization = df_src["Total ID position realization"].reindex(range(96))
            df["Total ID position realization"] = pd.to_numeric(realization, errors="coerce").fillna(0).astype(float)
        else:
            df["Total ID position realization"] = 0.0

        # ── Editable overwrite columns ──────────────────────────────────
        # Initialize session state for overwrite columns if not present
        overwrite_col_names = [
            "Wind realization overwrite",
            "Nowcast realization overwrite",
            "total largepv realization overwrite",
        ]
        for ow_col in overwrite_col_names:
            state_key = f"ow_{ow_col}"
            if state_key not in st.session_state:
                st.session_state[state_key] = df[ow_col].tolist()

        # Build the editable dataframe with only the overwrite columns
        edit_df = pd.DataFrame({
            ow_col: st.session_state[f"ow_{ow_col}"] for ow_col in overwrite_col_names
        })

        st.subheader("Edit overwrite values")
        edited = st.data_editor(
            edit_df,
            use_container_width=False,
            height=300,
            hide_index=True,
            num_rows="fixed",
            key="overwrite_editor",
        )

        # Save edits back to session state
        for ow_col in overwrite_col_names:
            st.session_state[f"ow_{ow_col}"] = edited[ow_col].tolist()
            df[ow_col] = edited[ow_col].astype(float)

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
        styled = display.style.apply(highlight_columns, axis=1).format(precision=1)
        st.dataframe(styled, use_container_width=True, height=700, hide_index=True)
    else:
        st.info(f"No data available for {selected_date.strftime('%d-%m-%Y')}. Example data is for 17-03-2026.")

# ── 2) Wind ──────────────────────────────────────────────────────────────
with tab_wind:
    if has_data:
        df_src = raw["Wind"].copy()

        df_w = pd.DataFrame()
        df_w["PTU"] = ptus
        df_w["Time"] = time_slots

        for col in ["Wind DA", "Wind parks with realization", "Wind parks with no realization"]:
            if col in df_src.columns:
                series = df_src[col].reindex(range(96))
                df_w[col] = pd.to_numeric(series, errors="coerce").fillna(0).astype(float)
            else:
                df_w[col] = 0.0

        # Formula: Wind total expected realization = parks with realization + parks with no realization
        df_w["Wind total expected realization"] = (
            df_w["Wind parks with realization"] + df_w["Wind parks with no realization"]
        )
        # Formula: Wind delta = total expected - DA
        df_w["Wind delta"] = df_w["Wind total expected realization"] - df_w["Wind DA"]

        st.dataframe(df_w, use_container_width=True, height=700, hide_index=True)
    else:
        st.info(f"No data available for {selected_date.strftime('%d-%m-%Y')}. Example data is for 17-03-2026.")

# ── 3) Solar ─────────────────────────────────────────────────────────────
with tab_solar:
    if has_data:
        df_src = raw["Solar"].copy()

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
        for col in solar_cols:
            if col in df_src.columns:
                series = df_src[col].reindex(range(96))
                df_s[col] = pd.to_numeric(series, errors="coerce").fillna(0).astype(float)
            else:
                df_s[col] = 0.0

        st.dataframe(df_s, use_container_width=True, height=700, hide_index=True)
    else:
        st.info(f"No data available for {selected_date.strftime('%d-%m-%Y')}. Example data is for 17-03-2026.")

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
        st.info(f"No data available for {selected_date.strftime('%d-%m-%Y')}. Example data is for 17-03-2026.")
