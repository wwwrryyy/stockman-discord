"""
Quant-Core AI — chart.py (Phase 3)
-----------------------------------
Responsible for generating high-quality candlestick charts with volume
and SMA overlays. Uses mplfinance and outputs to an in-memory buffer.
"""

import io
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import mplfinance as mpf

def generate_candlestick_chart(df: pd.DataFrame, ticker: str) -> io.BytesIO:
    """
    Generates a 6-month candlestick chart for the given ticker, with SMA-50
    and SMA-200 lines overlayed (if available), and volume bars at the bottom.
    
    Returns:
        io.BytesIO: A buffer containing the generated PNG image.
    """
    # ── 1. Subset Data ────────────────────────────────────────────────────────
    # 6 months of trading days is approximately 126 days.
    df_plot = df.iloc[-126:].copy()
    
    # Ensure the index is a DatetimeIndex as required by mplfinance
    df_plot.index = pd.to_datetime(df_plot.index)

    # ── 2. Configure Overlays (SMAs) ──────────────────────────────────────────
    ap = []
    # Plot SMA_50 if it exists and has non-null data
    if "SMA_50" in df_plot.columns and not df_plot["SMA_50"].dropna().empty:
        ap.append(
            mpf.make_addplot(
                df_plot["SMA_50"],
                color="#2196F3",  # Cool blue
                width=1.5,
            )
        )
    
    # Plot SMA_200 if it exists and has non-null data
    if "SMA_200" in df_plot.columns and not df_plot["SMA_200"].dropna().empty:
        ap.append(
            mpf.make_addplot(
                df_plot["SMA_200"],
                color="#FF9800",  # Amber/orange
                width=1.5,
            )
        )

    # ── 3. Build Custom Dark Style ────────────────────────────────────────────
    # Follows the UX Pro Max chart guidelines:
    # Bullish: #26A69A (teal), Bearish: #EF5350 (soft red)
    mc = mpf.make_marketcolors(
        up="#26a69a",
        down="#ef5350",
        edge="inherit",
        wick="inherit",
        volume="inherit",
        inherit=True,
    )

    custom_style = mpf.make_mpf_style(
        base_mpf_style="charles",
        marketcolors=mc,
        gridcolor="#2b2b36",
        gridstyle="--",
        facecolor="#12121c",  # Dark premium card color
        figcolor="#0f0f15",   # Dark page background color
        rc={
            "text.color": "#ffffff",
            "axes.labelcolor": "#cccccc",
            "xtick.color": "#cccccc",
            "ytick.color": "#cccccc",
            "axes.edgecolor": "#2b2b36",
            "font.size": 9,
        },
    )

    # ── 4. Generate & Save Plot to Buffer ─────────────────────────────────────
    buf = io.BytesIO()
    
    plot_kwargs = {
        "type": "candle",
        "volume": True,
        "style": custom_style,
        "figsize": (10, 6),
        "title": f"\n{ticker} — 6-Month Chart",
        "savefig": dict(fname=buf, format="png", dpi=150, bbox_inches="tight"),
    }
    
    # Add SMA overlays if any exist
    if ap:
        plot_kwargs["addplot"] = ap

    # mplfinance plot call
    mpf.plot(df_plot, **plot_kwargs)
    
    # Rewind buffer to start
    buf.seek(0)
    return buf
