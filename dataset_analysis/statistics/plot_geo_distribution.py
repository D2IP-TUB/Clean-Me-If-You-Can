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


def _load_world():
    """Load Natural Earth low-res countries, or None if geopandas/data are missing."""
    try:
        import geopandas as gpd
    except ImportError:
        return None

    candidates = list(
        Path.home().glob(
            ".conda/envs/*/lib/python*/site-packages/pyogrio/tests/fixtures/naturalearth_lowres/naturalearth_lowres.shp"
        )
    )
    for path in candidates:
        try:
            return gpd.read_file(path)
        except Exception:
            continue
    try:
        return gpd.read_file(gpd.datasets.get_path("naturalearth_lowres"))
    except Exception:
        pass
    try:
        return gpd.read_file(
            "https://naciscdn.org/naturalearth/110m/cultural/ne_110m_admin_0_countries.zip"
        )
    except Exception:
        return None


def build_figure(counts: pd.DataFrame, top_n: int, title: str, output: str):
    """Full-width bar chart with the choropleth inset under the longest bar."""

    top = counts.head(top_n).copy()
    top = top.iloc[::-1]  # reverse for horizontal bar (top country on top)
    n_bars = len(top)

    fig, ax_bar = plt.subplots(figsize=(16.5, 8.6), facecolor=BG_COLOR, dpi=180)
    fig.subplots_adjust(left=0.17, right=0.97, top=0.97, bottom=0.12)

    max_val = float(top["count"].max())
    bar_colors = [
        mcolors.to_hex(
            np.array(mcolors.to_rgb(ACCENT_DARK)) * (0.35 + 0.65 * v / max_val)
            + np.array(mcolors.to_rgb("#4DA3F0")) * (1 - 0.35 - 0.65 * v / max_val)
        )
        for v in top["count"]
    ]

    ax_bar.barh(
        range(n_bars), top["count"],
        color=bar_colors, edgecolor=BAR_EDGE, linewidth=0.4,
        height=0.62, zorder=3,
    )
    ax_bar.set_yticks(range(n_bars))
    ax_bar.set_yticklabels(top["country"], fontsize=18, fontweight="bold", color=TEXT_COLOR)
    ax_bar.set_xlabel("Number of Addresses", fontsize=18, color=TEXT_COLOR, labelpad=12)
    ax_bar.set_ylabel("Top {} Countries".format(top_n), fontsize=16, color=TEXT_COLOR, labelpad=10)

    for i, val in enumerate(top["count"]):
        ax_bar.text(
            val + max_val * 0.012, i,
            f"{val:,.0f}",
            va="center", ha="left",
            fontsize=15, fontweight="bold", color=TEXT_COLOR, zorder=4,
        )

    ax_bar.set_xlim(0, max_val * 1.13)
    ax_bar.set_ylim(-0.55, n_bars - 0.28)
    ax_bar.xaxis.set_major_formatter(
        mticker.FuncFormatter(
            lambda x, _: f"{x/1e6:.1f}M" if x >= 1e6 else f"{x/1e3:.0f}K" if x >= 1e3 else f"{x:.0f}"
        )
    )
    ax_bar.xaxis.grid(True, color=GRID_COLOR, linewidth=0.6, zorder=0)
    ax_bar.set_axisbelow(True)
    ax_bar.spines["top"].set_visible(False)
    ax_bar.spines["right"].set_visible(False)
    ax_bar.spines["bottom"].set_color(GRID_COLOR)
    ax_bar.spines["left"].set_color(GRID_COLOR)
    ax_bar.tick_params(colors=TEXT_COLOR, labelsize=14)

    world = _load_world()
    if world is not None:
        lon0, lon1, lat0, lat1 = -170.0, 188.0, -58.0, 84.0
        map_aspect = (lon1 - lon0) / (lat1 - lat0)

        xlim0, xlim1 = ax_bar.get_xlim()
        ylim0, ylim1 = ax_bar.get_ylim()
        second = float(top["count"].iloc[:-1].max()) if n_bars > 1 else 0.0
        # Sit just to the right of the second-longest bar's count label,
        # and just under the longest (US) bar.
        x0 = second + max_val * 0.09
        us_y = n_bars - 1
        y_top = us_y - 0.40

        fig.canvas.draw()
        bbox = ax_bar.get_window_extent().transformed(fig.dpi_scale_trans.inverted())
        ax_w, ax_h = bbox.width, bbox.height
        left_frac = (x0 - xlim0) / (xlim1 - xlim0)
        top_frac = (y_top - ylim0) / (ylim1 - ylim0)
        width_frac = 0.995 - left_frac
        height_frac = (width_frac * ax_w) / map_aspect / ax_h
        bottom_frac = top_frac - height_frac
        # Drop the block a bit so it sits closer to the x-axis.
        bottom_frac = max(0.10, bottom_frac - 0.13)
        if bottom_frac + height_frac > top_frac:
            height_frac = top_frac - bottom_frac
            width_frac = height_frac * ax_h * map_aspect / ax_w

        ax_map = ax_bar.inset_axes([left_frac, bottom_frac, width_frac, height_frac])
        ax_map.set_facecolor(BG_COLOR)
        for spine in ax_map.spines.values():
            spine.set_visible(False)

        iso_counts = counts.dropna(subset=["iso3"]).groupby("iso3")["count"].sum().reset_index()
        world = world.merge(iso_counts, how="left", left_on="iso_a3", right_on="iso3")
        world.plot(ax=ax_map, color="#E8EDF4", edgecolor="white", linewidth=0.25)
        has_data = world.dropna(subset=["count"])
        if not has_data.empty:
            from matplotlib.colors import LogNorm
            vmin = max(has_data["count"].min(), 1)
            vmax = has_data["count"].max()
            cmap = mcolors.LinearSegmentedColormap.from_list(
                "navy_map", ["#D4ECFF", "#7ABDF5", "#2D8BE6", "#0F3B8A", "#08153D"]
            )
            norm = LogNorm(vmin=vmin, vmax=vmax)
            has_data.plot(
                ax=ax_map, column="count", cmap=cmap, norm=norm,
                edgecolor="white", linewidth=0.25, legend=False,
            )
            sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
            sm.set_array([])
            cax = ax_bar.inset_axes([
                left_frac + 0.16 * width_frac,
                max(0.02, bottom_frac - 0.09),
                0.68 * width_frac,
                0.05,
            ])
            cbar = fig.colorbar(sm, cax=cax, orientation="horizontal")
            cbar.set_label("Number of Addresses (log scale)", fontsize=14, color=TEXT_COLOR, labelpad=6)
            cbar.ax.tick_params(labelsize=12, colors=TEXT_COLOR, length=3)
            cbar.outline.set_edgecolor(GRID_COLOR)

        ax_map.set_xlim(lon0, lon1)
        ax_map.set_ylim(lat0, lat1)
        ax_map.set_axis_off()
        ax_map.set_aspect("equal")

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