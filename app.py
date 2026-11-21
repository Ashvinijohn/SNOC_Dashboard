import math
import os

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="SNOC Legacy Well Log Recovery", layout="wide",
                   initial_sidebar_state="collapsed")

BASE = os.path.dirname(os.path.abspath(__file__))
LOGO = os.path.join(BASE, "assets", "logo.png")

# ------------------------------------------------------------------
# Colours (sampled from the Power BI report)
# ------------------------------------------------------------------
MAROON = "#6B2226"   # KPI cards, main pie slices
ORANGE = "#A9522A"   # secondary pie slices, onshore wells
BROWN = "#52301F"    # bar chart
BLACK = "#000000"    # Acquisition & Data Management slice
NAVY = "#3D3F78"     # offshore wells, G&G slice
PANEL = "#F7F7F7"    # chart panel background
TEXT = "#444444"

SOURCE_COLORS = {"SNOC": MAROON, "SPC": ORANGE}
STATUS_COLORS = {"Scanned": MAROON, "Duplicates": ORANGE}
DOMAIN_COLORS = {
    "Well Engineering & Operations": MAROON,
    "Formation Evaluation": ORANGE,
    "Acquisition & Data Management": BLACK,
    "G&G": NAVY,
}
MAP_COLORS = {"Offshore": NAVY, "Onshore": ORANGE}

st.markdown(
    f"""
    <style>
    .block-container {{padding-top: 1.5rem; padding-bottom: 1rem; max-width: 1500px;}}
    header[data-testid="stHeader"] {{background: transparent;}}
    .kpi {{background:{MAROON}; color:#fff; border-radius:4px; padding:14px 6px;
           text-align:center; box-shadow:3px 3px 6px rgba(0,0,0,.35);}}
    .kpi .v {{font-size:30px; font-weight:700; line-height:1.15;}}
    .kpi .l {{font-size:15px;}}
    </style>
    """,
    unsafe_allow_html=True,
)

# ------------------------------------------------------------------
# Data (bundled in the repo - nothing to upload)
# ------------------------------------------------------------------
def _clean_key(s: pd.Series) -> pd.Series:
    return s.astype("string").str.strip().str.upper()


def _read(name: str) -> pd.DataFrame:
    # only truly empty cells are missing values ("NA" etc. stay as text)
    return pd.read_csv(os.path.join(BASE, "data", name), keep_default_na=False, na_values=[""])


def prepare_tables(logs, cur, wells):
    # --- LogsInventory (no rows removed: the DAX measures do the filtering) ---
    logs["STATUS"] = logs["STATUS"].astype("string").str.strip()
    logs["Scans"] = pd.to_numeric(logs["NO OF SCANS"], errors="coerce").fillna(0)   # [Scanned Images]
    logs["IsCopy"] = (logs["STATUS"] == "Copy").astype(int)                          # [Duplicates]
    logs["TotalLogs"] = logs["Scans"] + logs["IsCopy"]                               # [Total Logs]
    logs["Field"] = _clean_key(logs["Name_Lookup.Correct Field"])
    logs["Well"] = _clean_key(logs["Name_Lookup.Correct Well Name"])
    logs["RawWell"] = _clean_key(logs["WELL NAME"])   # LogsInventory[WELL NAME] -> Map wells relationship

    # --- Indexing_and_QC ---
    cur["Field"] = _clean_key(cur["Name_Lookup.Correct Field"])
    cur["Well"] = _clean_key(cur["Name_Lookup.Correct Well Name"])
    cur["IsOK"] = cur["Depth Check"].astype("string").str.strip() == "OK"

    # --- Map wells ---
    wells["Field"] = _clean_key(wells["Field name"])
    wells["Well"] = _clean_key(wells["Well name (project)"])
    wells = wells.dropna(subset=["Latitude", "Longitude"])
    return logs, cur, wells


# ------------------------------------------------------------------
# DAX measures translated to pandas
# ------------------------------------------------------------------
def total_logs(logs):        # [Total Logs] = [Scanned Images] + [Duplicates]
    return int(logs["TotalLogs"].sum())


def total_fields(logs):      # DISTINCTCOUNTNOBLANK(Correct Field) with STATUS = "Scanned"
    return int(logs.loc[logs["STATUS"] == "Scanned", "Field"].nunique())


def total_wells(logs):       # DISTINCTCOUNTNOBLANK(Correct Well Name) with STATUS = "Scanned"
    return int(logs.loc[logs["STATUS"] == "Scanned", "Well"].nunique())


def indexed_curves(cur):     # COUNTROWS(Indexing_and_QC)
    return len(cur)


def curve_footage(cur):      # per (tag_id, Curve Names) on OK rows: MAX(bottom) - MIN(top), summed
    ok = cur[cur["IsOK"]]
    if ok.empty:
        return 0.0
    g = ok.groupby(["tag_id", "Curve Names"], dropna=False).agg(
        top=("Top Depth Cleaned", "min"), bot=("Bottom Depth Cleaned", "max"))
    return float((g["bot"] - g["top"]).sum())


@st.cache_data(show_spinner="Loading data...")
def load_tables():
    return prepare_tables(_read("logs.csv.gz"), _read("curves.csv.gz"), _read("wells.csv.gz"))


logs, cur, wells = load_tables()

# ------------------------------------------------------------------
# Header: logo | title | Field / Well filters
# ------------------------------------------------------------------
h1, h2, h3 = st.columns([1.6, 4.6, 1.6], vertical_alignment="center")
with h1:
    if os.path.exists(LOGO):
        st.image(LOGO, width=230)
    else:
        st.markdown(f"<h2 style='color:{MAROON};margin:0'>PetroLead</h2>", unsafe_allow_html=True)
with h2:
    st.markdown(
        "<div style='text-align:center;font-size:36px;font-weight:800;color:#222;"
        "letter-spacing:.5px;line-height:1.2;'>SNOC LEGACY WELL LOG RECOVERY</div>",
        unsafe_allow_html=True)

fields = sorted(logs["Field"].dropna().unique())
with h3:
    sel_field = st.selectbox("Field", ["All"] + fields)
    pool = logs if sel_field == "All" else logs[logs["Field"] == sel_field]
    sel_well = st.selectbox("Well", ["All"] + sorted(pool["Well"].dropna().unique()))

# Same filter behaviour as the Power BI report:
#  * the Field / Well slicers filter LogsInventory only
#  * Map wells is filtered through the LogsInventory[WELL NAME] relationship
#  * Indexing_and_QC is NOT connected to the slicers, so curve KPIs / domain pie never change
f_logs = logs
if sel_field != "All":
    f_logs = f_logs[f_logs["Field"] == sel_field]
if sel_well != "All":
    f_logs = f_logs[f_logs["Well"] == sel_well]
f_cur = cur
f_wells = wells[wells["Well"].isin(set(f_logs["RawWell"].dropna()))]

# ------------------------------------------------------------------
# KPI cards
# ------------------------------------------------------------------
def kpi(col, value, label):
    col.markdown(f'<div class="kpi"><div class="v">{value}</div><div class="l">{label}</div></div>',
                 unsafe_allow_html=True)


k = st.columns(5)
kpi(k[0], f"{total_logs(f_logs):,}", "Logs")
kpi(k[1], f"{total_fields(f_logs):,}", "Fields")
kpi(k[2], f"{total_wells(f_logs):,}", "Wells")
kpi(k[3], f"{indexed_curves(f_cur):,}", "Indexed Curves")
kpi(k[4], f"{curve_footage(f_cur) / 1e6:.2f}M", "Curve Footage (ft)")
st.write("")


# ------------------------------------------------------------------
# Charts
# ------------------------------------------------------------------
def show(fig):
    try:
        st.plotly_chart(fig, theme=None, width="stretch")   # theme=None keeps our colours
    except Exception:
        st.plotly_chart(fig, theme=None, use_container_width=True)


def short(label: str, n: int = 28) -> str:
    return label if len(label) <= n else label[: n - 1] + "…"


def pie(counts: pd.Series, colors, template, title):
    """counts: Series indexed by label, values = slice size."""
    counts = counts[counts > 0].sort_values(ascending=False)
    if counts.empty:
        st.caption(f"{title}: no data for this selection")
        return
    vc = counts.rename_axis("label").reset_index(name="value")
    fig = px.pie(vc, names="label", values="value", color="label", color_discrete_map=colors)
    fig.update_traces(text=vc["label"].map(short), texttemplate=template, textposition="outside",
                      sort=False, automargin=True, marker=dict(line=dict(width=0)),
                      textfont=dict(color=TEXT, size=11))
    fig.update_layout(title=dict(text=f"<b>{title}</b>", x=0.5, font=dict(color="#222", size=15)),
                      showlegend=False, height=330, margin=dict(l=30, r=30, t=50, b=20),
                      paper_bgcolor=PANEL, font=dict(color=TEXT))
    show(fig)


grid, map_col = st.columns([2, 1.15])
LABEL_VAL_PCT = "%{text} %{value:.0f} (%{percent:.0%})"

with grid:
    a, b = st.columns(2)
    with a:   # Total Logs by Source
        pie(f_logs.groupby("Source")["TotalLogs"].sum(), SOURCE_COLORS, LABEL_VAL_PCT, "Logs Source")
    with b:   # % of total curves by Domain Trimmed
        pie(f_cur["Domain Trimmed"].dropna().value_counts(), DOMAIN_COLORS,
            "%{text}<br>%{percent:.2%}", "Curves per Domain")

    c, d = st.columns(2)
    with c:   # [Scanned Images] vs [Duplicates]
        pie(pd.Series({"Scanned": f_logs["Scans"].sum(), "Duplicates": f_logs["IsCopy"].sum()}),
            STATUS_COLORS, LABEL_VAL_PCT, "Logs Status")
    with d:   # Total Logs by Survey_Decade
        bar = (f_logs.dropna(subset=["Survey_Decade"]).groupby("Survey_Decade")["TotalLogs"]
               .sum().sort_index().reset_index())
        bar.columns = ["Decade", "Logs"]
        bar = bar[bar["Logs"] > 0]
        if bar.empty:
            st.caption("Log per Survey Year: no data for this selection")
        else:
            fig = px.bar(bar, x="Decade", y="Logs", text="Logs", color_discrete_sequence=[BROWN])
            fig.update_traces(textposition="outside", texttemplate="%{y:.0f}",
                              textfont=dict(color=TEXT, size=11))
            fig.update_layout(title=dict(text="<b>Log per Survey Year</b>", x=0.5,
                                         font=dict(color="#222", size=15)),
                              height=330, margin=dict(l=10, r=10, t=50, b=20), xaxis_title=None,
                              yaxis=dict(visible=False), xaxis=dict(tickfont=dict(color=TEXT)),
                              paper_bgcolor=PANEL, plot_bgcolor=PANEL, font=dict(color=TEXT))
            show(fig)

with map_col:
    if f_wells.empty:
        st.caption("Well Location: no wells for this selection")
    else:
        lat_min, lat_max = f_wells["Latitude"].min(), f_wells["Latitude"].max()
        lon_min, lon_max = f_wells["Longitude"].min(), f_wells["Longitude"].max()
        span = max(lat_max - lat_min, lon_max - lon_min, 0.02)
        zoom = max(3.0, min(12.0, math.log2(360 / span) - 0.6))
        center = dict(lat=(lat_min + lat_max) / 2, lon=(lon_min + lon_max) / 2)
        kw = dict(lat="Latitude", lon="Longitude", color="Onshore / Offshore",
                  color_discrete_map=MAP_COLORS, hover_name="Well name (project)",
                  hover_data={"Field name": True, "Logs": True, "Latitude": False,
                              "Longitude": False, "Onshore / Offshore": False},
                  zoom=zoom, height=680, center=center)
        try:
            fig = px.scatter_map(f_wells, **kw)
            fig.update_layout(map_style="carto-positron")          # grayscale light basemap
        except AttributeError:                                       # older plotly
            fig = px.scatter_mapbox(f_wells, **kw)
            fig.update_layout(mapbox_style="carto-positron")
        fig.update_traces(marker=dict(size=11, opacity=0.9))
        fig.update_layout(title=dict(text="<b>Well Location</b>", x=0.5,
                                     font=dict(color="#222", size=15)),
                          margin=dict(l=0, r=0, t=50, b=0), paper_bgcolor=PANEL,
                          font=dict(color=TEXT),
                          legend=dict(title=None, orientation="h", y=0.02, x=0.02,
                                      bgcolor="rgba(255,255,255,.8)"))
        show(fig)
