#!/usr/bin/env python3
"""
Geographic Distribution of Addresses by Country
=================================================
Generates a combined horizontal bar chart + choropleth world map
from a CSV file containing a 'country' column.

Usage:
    python geo_distribution_chart.py data.csv
    python geo_distribution_chart.py data.csv --column country_name --top 10 --output chart.png

Requirements:
    pip install pandas matplotlib geopandas numpy matplotlib-inline
"""

import argparse
import sys
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.gridspec as gridspec
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
# Rich navy-to-sky palette
PALETTE = [
    "#08153D", "#0B2060", "#0F3B8A", "#1456B0", "#1B6FD0",
    "#2D8BE6", "#4DA3F0", "#7ABDF5", "#A8D5FA", "#D4ECFF",
]
BG_COLOR     = "#FAFCFF"
TEXT_COLOR    = "#0A1628"
ACCENT_DARK  = "#08153D"
ACCENT_MID   = "#1456B0"
GRID_COLOR   = "#D8E3F0"
BAR_EDGE     = "#06102E"

# Country name normalization → ISO alpha-3
COUNTRY_ALIASES = {
    "united states": "USA", "usa": "USA", "us": "USA", "united states of america": "USA",
    "deutschland": "DEU", "germany": "DEU",
    "nederland": "NLD", "netherlands": "NLD", "the netherlands": "NLD",
    "united kingdom": "GBR", "uk": "GBR", "great britain": "GBR", "england": "GBR",
    "france": "FRA",
    "italia": "ITA", "italy": "ITA",
    "canada": "CAN",
    "österreich": "AUT", "austria": "AUT", "osterreich": "AUT",
    "españa": "ESP", "spain": "ESP", "espana": "ESP",
    "polska": "POL", "poland": "POL",
    "brasil": "BRA", "brazil": "BRA",
    "china": "CHN", "peoples republic of china": "CHN",
    "japan": "JPN",
    "australia": "AUS",
    "india": "IND",
    "mexico": "MEX", "méxico": "MEX",
    "russia": "RUS", "russian federation": "RUS",
    "south korea": "KOR", "korea": "KOR", "republic of korea": "KOR",
    "south africa": "ZAF",
    "argentina": "ARG",
    "sweden": "SWE", "sverige": "SWE",
    "norway": "NOR", "norge": "NOR",
    "denmark": "DNK", "danmark": "DNK",
    "finland": "FIN", "suomi": "FIN",
    "switzerland": "CHE", "schweiz": "CHE", "suisse": "CHE",
    "belgium": "BEL", "belgique": "BEL", "belgië": "BEL",
    "portugal": "PRT",
    "czech republic": "CZE", "czechia": "CZE",
    "ireland": "IRL",
    "new zealand": "NZL",
    "turkey": "TUR", "türkiye": "TUR",
    "indonesia": "IDN",
    "thailand": "THA",
    "philippines": "PHL",
    "colombia": "COL",
    "chile": "CHL",
    "peru": "PER",
    "egypt": "EGY",
    "nigeria": "NGA",
    "kenya": "KEN",
    "ukraine": "UKR",
    "romania": "ROU",
    "hungary": "HUN", "magyarország": "HUN",
    "greece": "GRC",
    "israel": "ISR",
    "singapore": "SGP",
    "malaysia": "MYS",
    "taiwan": "TWN",
    "vietnam": "VNM",
    "saudi arabia": "SAU",
    "united arab emirates": "ARE", "uae": "ARE",
    "pakistan": "PAK",
    "bangladesh": "BGD",
    "croatia": "HRV", "hrvatska": "HRV",
    "slovakia": "SVK",
    "slovenia": "SVN",
    "serbia": "SRB",
    "bulgaria": "BGR",
    "lithuania": "LTU",
    "latvia": "LVA",
    "estonia": "EST",
    "luxembourg": "LUX",
    "iceland": "ISL",
    "malta": "MLT",
    "cyprus": "CYP",
}

# Try to load iso3166 for extra coverage
try:
    import pycountry
    def _resolve_iso3(name: str) -> str | None:
        low = name.strip().lower()
        if low in COUNTRY_ALIASES:
            return COUNTRY_ALIASES[low]
        try:
            c = pycountry.countries.lookup(name)
            return c.alpha_3
        except LookupError:
            return None
except ImportError:
    def _resolve_iso3(name: str) -> str | None:
        low = name.strip().lower()
        return COUNTRY_ALIASES.get(low)


def load_and_count(csv_path: str, column: str) -> pd.DataFrame:
    """Read CSV → count rows per country → return sorted DataFrame."""
    # Peek at headers only to find the matching column name
    header_df = pd.read_csv(csv_path, nrows=0)
    col_match = [c for c in header_df.columns if c.strip().lower() == column.lower()]
    if not col_match:
        col_match = [c for c in header_df.columns if column.lower() in c.strip().lower()]
    if not col_match:
        print(f"[ERROR] No column matching '{column}' found.")
        print(f"  Available columns: {list(header_df.columns)}")
        sys.exit(1)

    col = col_match[0]
    # Read only the one needed column — much faster on large files
    series = pd.read_csv(csv_path, usecols=[col], low_memory=True)[col]
    counts = series.dropna().value_counts().reset_index()
    counts.columns = ["country", "count"]
    counts["iso3"] = counts["country"].apply(_resolve_iso3)
    return counts.sort_values("count", ascending=False).reset_index(drop=True)


def build_figure(counts: pd.DataFrame, top_n: int, title: str, output: str):
    """Render the combined bar chart + choropleth map."""

    top = counts.head(top_n).copy()
    top = top.iloc[::-1]  # reverse for horizontal bar (top country on top)

    # ---- Figure layout ----
    fig = plt.figure(figsize=(18, 9), facecolor=BG_COLOR, dpi=180)
    gs = gridspec.GridSpec(
        1, 2, width_ratios=[1, 1.3], wspace=0.05,
        left=0.07, right=0.97, top=0.88, bottom=0.10,
    )
    ax_bar = fig.add_subplot(gs[0])
    ax_map = fig.add_subplot(gs[1])

    # ---- Title ----
    fig.text(
        0.50, 0.95, title,
        ha="center", va="center",
        fontsize=22, fontweight="bold", color=TEXT_COLOR,
        fontfamily="serif",
    )
    fig.text(
        0.50, 0.91,
        f"Top {top_n} countries shown  ·  {counts['count'].sum():,.0f} total addresses across {len(counts)} countries",
        ha="center", va="center",
        fontsize=11, color="#5A6B82", fontfamily="sans-serif",
    )

    # ==================================================================
    # BAR CHART
    # ==================================================================
    max_val = top["count"].max()
    bar_colors = [
        mcolors.to_hex(
            np.array(mcolors.to_rgb(ACCENT_DARK)) * (0.35 + 0.65 * v / max_val)
            + np.array(mcolors.to_rgb("#4DA3F0")) * (1 - 0.35 - 0.65 * v / max_val)
        )
        for v in top["count"]
    ]

    bars = ax_bar.barh(
        range(len(top)), top["count"],
        color=bar_colors, edgecolor=BAR_EDGE, linewidth=0.5,
        height=0.72, zorder=3,
    )
    ax_bar.set_yticks(range(len(top)))
    ax_bar.set_yticklabels(top["country"], fontsize=12, fontweight="bold", color=TEXT_COLOR)
    ax_bar.set_xlabel("Number of Addresses", fontsize=12, color=TEXT_COLOR, labelpad=10)
    ax_bar.set_ylabel("Top {} Countries".format(top_n), fontsize=12, color=TEXT_COLOR, labelpad=10)

    # Value labels
    for i, (val, bar) in enumerate(zip(top["count"], bars)):
        ax_bar.text(
            val + max_val * 0.015, i,
            f"{val:,.0f}",
            va="center", ha="left",
            fontsize=10, fontweight="bold", color=TEXT_COLOR,
        )

    ax_bar.set_xlim(0, max_val * 1.22)
    ax_bar.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x/1e6:.1f}M" if x >= 1e6 else f"{x/1e3:.0f}K" if x >= 1e3 else f"{x:.0f}"))
    ax_bar.xaxis.grid(True, color=GRID_COLOR, linewidth=0.6, zorder=0)
    ax_bar.set_axisbelow(True)
    ax_bar.spines["top"].set_visible(False)
    ax_bar.spines["right"].set_visible(False)
    ax_bar.spines["bottom"].set_color(GRID_COLOR)
    ax_bar.spines["left"].set_color(GRID_COLOR)
    ax_bar.tick_params(colors=TEXT_COLOR, labelsize=10)

    # ==================================================================
    # CHOROPLETH MAP
    # ==================================================================
    try:
        import geopandas as gpd
        import glob

        # Try multiple known locations for naturalearth shapefile
        candidates = [
            *glob.glob("/usr/**/naturalearth_lowres/", recursive=True),
            *glob.glob("/usr/**/naturalearth_lowres.shp", recursive=True),
        ]
        if candidates:
            world = gpd.read_file(candidates[0])
        else:
            # Fallback: try deprecated API or URL
            try:
                world = gpd.read_file(gpd.datasets.get_path("naturalearth_lowres"))
            except Exception:
                world = gpd.read_file("https://naciscdn.org/naturalearth/110m/cultural/ne_110m_admin_0_countries.zip")
    except Exception:
            # Fallback: skip the map
            ax_map.text(0.5, 0.5, "Install geopandas for\nthe world map", transform=ax_map.transAxes,
                        ha="center", va="center", fontsize=14, color="#999")
            ax_map.set_axis_off()
            plt.savefig(output, dpi=180, bbox_inches="tight", facecolor=BG_COLOR)
            print(f"[OK] Saved → {output}  (no map — install geopandas)")
            return

    # Merge counts with world geometries
    iso_counts = counts.dropna(subset=["iso3"]).groupby("iso3")["count"].sum().reset_index()
    world = world.merge(iso_counts, how="left", left_on="iso_a3", right_on="iso3")

    # Draw base (no-data countries)
    world.plot(ax=ax_map, color="#E8EDF4", edgecolor="white", linewidth=0.3)

    # Draw data countries with log-scale colour
    has_data = world.dropna(subset=["count"])
    if not has_data.empty:
        from matplotlib.colors import LogNorm
        vmin = max(has_data["count"].min(), 1)
        vmax = has_data["count"].max()
        cmap = mcolors.LinearSegmentedColormap.from_list("navy_map", ["#D4ECFF", "#7ABDF5", "#2D8BE6", "#0F3B8A", "#08153D"])
        norm = LogNorm(vmin=vmin, vmax=vmax)
        has_data.plot(ax=ax_map, column="count", cmap=cmap, norm=norm,
                      edgecolor="white", linewidth=0.3, legend=False)

        # Colourbar
        sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
        sm.set_array([])
        cbar = fig.colorbar(sm, ax=ax_map, orientation="horizontal",
                            fraction=0.035, pad=0.04, aspect=30, shrink=0.6)
        cbar.set_label("Number of Addresses (log scale)", fontsize=10, color=TEXT_COLOR, labelpad=8)
        cbar.ax.tick_params(labelsize=8, colors=TEXT_COLOR)
        cbar.outline.set_edgecolor(GRID_COLOR)

    ax_map.set_xlim(-180, 180)
    ax_map.set_ylim(-60, 85)
    ax_map.set_axis_off()

    # ---- Save ----
    plt.savefig(output, dpi=180, bbox_inches="tight", facecolor=BG_COLOR)
    plt.close()
    print(f"[OK] Saved → {output}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Generate geographic distribution chart from CSV")
    parser.add_argument("csv", help="Path to CSV file")
    parser.add_argument("--column", "-c", default="country",
                        help="Name of the country column (default: 'country')")
    parser.add_argument("--top", "-n", type=int, default=10,
                        help="Number of top countries to show (default: 10)")
    parser.add_argument("--title", "-t",
                        default="Geographic Distribution of Addresses",
                        help="Chart title")
    parser.add_argument("--output", "-o", default="geo_distribution.png",
                        help="Output file path (default: geo_distribution.png)")
    args = parser.parse_args()

    if not Path(args.csv).exists():
        print(f"[ERROR] File not found: {args.csv}")
        sys.exit(1)

    counts = load_and_count(args.csv, args.column)
    print(f"Found {len(counts)} unique countries, {counts['count'].sum():,.0f} total rows")
    print(counts.head(args.top).to_string(index=False))

    build_figure(counts, args.top, args.title, args.output)


if __name__ == "__main__":
    main()