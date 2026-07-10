"""
Quant-Core AI — bot.py (Phase 2)
----------------------------------
Changes from Phase 1:
  - /analyze now calls data.fetch_analysis_data() via asyncio.to_thread()
    (keeps the blocking yfinance calls off the Discord event loop)
  - Builds and posts a rich Discord Embed with all indicator values,
    fundamentals, and signal tags
  - Full graceful error handling per PRD §9

Pipeline so far:
  /analyze → data.py (fetch + indicators) → Discord Embed  ✅
  chart.py  (Phase 3)                                       ⏳
  llm.py    (Phase 4)                                       ⏳

Run:
    python bot.py

Requirements:
    pip install discord.py python-dotenv yfinance pandas pandas-ta
"""

import asyncio
import os
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from data import AnalysisData, fetch_analysis_data
from chart import generate_candlestick_chart

# ── Load environment variables from .env ──────────────────────────────────────
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError(
        "DISCORD_TOKEN not found. "
        "Create a .env file with DISCORD_TOKEN=your_token_here"
    )

# ── Intents ───────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True

# ── Bot ───────────────────────────────────────────────────────────────────────
bot = commands.Bot(command_prefix="!", intents=intents)


# ── Events ────────────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    print(f"✅  Logged in as: {bot.user.name} (ID: {bot.user.id})")
    print(f"    discord.py version: {discord.__version__}")
    print("─" * 40)
    try:
        synced = await bot.tree.sync()
        print(f"✅  Synced {len(synced)} slash command(s) globally.")
        for cmd in synced:
            print(f"    /{cmd.name}")
    except Exception as e:
        print(f"❌  Failed to sync slash commands: {e}")
    print("─" * 40)
    print("    Quant-Core is online. Waiting for commands...")


@bot.event
async def on_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError,
):
    msg = f"❌ An unexpected error occurred: `{error}`"
    if interaction.response.is_done():
        await interaction.followup.send(msg, ephemeral=True)
    else:
        await interaction.response.send_message(msg, ephemeral=True)


# ── /analyze ──────────────────────────────────────────────────────────────────
@bot.tree.command(
    name="analyze",
    description="Run a full quantitative analysis on a stock ticker.",
)
@app_commands.describe(
    ticker="The stock ticker symbol to analyze (e.g. AAPL, TSLA, INFY.NS)"
)
async def analyze(interaction: discord.Interaction, ticker: str):
    ticker = ticker.upper().strip()
    await interaction.response.defer(thinking=True)

    # ── Run blocking I/O on a thread pool so the event loop stays free ────────
    data: AnalysisData | None = await asyncio.to_thread(fetch_analysis_data, ticker)

    # ── PRD §9: Graceful failure ──────────────────────────────────────────────
    if data is None:
        await interaction.followup.send(
            f"❌ **Error:** Could not fetch data for `{ticker}`. "
            "The ticker may be invalid, or the Yahoo Finance API is temporarily down. "
            "Try again in a moment."
        )
        return

    # ── Generate chart ────────────────────────────────────────────────────────
    chart_buf = await asyncio.to_thread(generate_candlestick_chart, data.df, ticker)
    chart_file = discord.File(chart_buf, filename="chart.png")

    # ── Build the Discord Embed ───────────────────────────────────────────────
    embed = _build_data_embed(data)
    embed.set_image(url="attachment://chart.png")

    await interaction.followup.send(embed=embed, file=chart_file)


# ── Embed Builder ─────────────────────────────────────────────────────────────

def _build_data_embed(data: AnalysisData) -> discord.Embed:
    """
    Constructs the Phase 2 data embed.
    In Phase 3 a chart image will be attached; in Phase 4 the LLM verdict
    field replaces the placeholder. The embed structure is intentionally
    built now so those phases only ADD content, not restructure the embed.
    """

    # ── Colour: driven by composite signal tags ───────────────────────────────
    if "COMPOSITE_BUY_SIGNAL" in data.signal_tags:
        colour = discord.Colour.green()
        verdict_placeholder = "🟢 Likely **BUY** — awaiting LLM verdict (Phase 4)"
    elif "COMPOSITE_SELL_SIGNAL" in data.signal_tags:
        colour = discord.Colour.red()
        verdict_placeholder = "🔴 Likely **SELL** — awaiting LLM verdict (Phase 4)"
    else:
        colour = discord.Colour.yellow()
        verdict_placeholder = "🟡 Likely **HOLD** — awaiting LLM verdict (Phase 4)"

    # ── Price change formatting ───────────────────────────────────────────────
    pct   = data.price_change_pct
    arrow = "▲" if pct >= 0 else "▼"
    pct_str = f"{arrow} {abs(pct):.2f}%"

    # ── Embed header ─────────────────────────────────────────────────────────
    name = data.short_name or data.ticker
    embed = discord.Embed(
        title=f"📊 Quant-Core Analysis — {data.ticker}",
        description=(
            f"**{name}**\n"
            f"Current Price: **${data.current_price:,.2f}** ({pct_str} vs prev close)\n\n"
            f"{verdict_placeholder}"
        ),
        colour=colour,
        timestamp=datetime.now(tz=timezone.utc),
    )

    # ── Field 1: Technical Indicators ────────────────────────────────────────
    def _fmt(val, prefix="", suffix="", decimals=2):
        if val is None:
            return "*N/A*"
        return f"{prefix}{val:,.{decimals}f}{suffix}"

    rsi_bar = _rsi_bar(data.rsi)
    embed.add_field(
        name="📈 Technical Indicators",
        value=(
            f"**RSI (14):** {_fmt(data.rsi)} {rsi_bar}\n"
            f"**SMA 50:** {_fmt(data.sma_50, '$')}\n"
            f"**SMA 200:** {_fmt(data.sma_200, '$')}\n"
            f"**MACD:** {_fmt(data.macd, decimals=4)}\n"
            f"**MACD Signal:** {_fmt(data.macd_signal, decimals=4)}\n"
            f"**MACD Hist:** {_fmt(data.macd_hist, decimals=4)}"
        ),
        inline=True,
    )

    # ── Field 2: Fundamentals ────────────────────────────────────────────────
    embed.add_field(
        name="🏦 Fundamentals",
        value=(
            f"**P/E Ratio:** {data.pe_ratio if data.pe_ratio else '*N/A*'}\n"
            f"**Market Cap:** {data.market_cap or '*N/A*'}\n"
            f"**Sector:** {data.sector or '*N/A*'}\n"
            f"**Industry:** {data.industry or '*N/A*'}\n"
            f"**52W High:** {_fmt(data.fifty_two_week_high, '$')}\n"
            f"**52W Low:** {_fmt(data.fifty_two_week_low, '$')}"
        ),
        inline=True,
    )

    # ── Field 3: Signal Tags ─────────────────────────────────────────────────
    if data.signal_tags:
        tag_str = "  ".join(f"`{t}`" for t in data.signal_tags)
    else:
        tag_str = "*No signals fired.*"

    embed.add_field(name="🏷️ Signal Tags", value=tag_str, inline=False)

    # ── Field 4: Signal Summary ───────────────────────────────────────────────
    embed.add_field(
        name="🔍 Signal Detail",
        value=data.signal_summary[:1024],  # Discord field limit
        inline=False,
    )

    # The real chart image is now attached to the embed via embed.set_image()

    embed.set_footer(text="Quant-Core AI  •  Data: Yahoo Finance  •  Phase 2")
    return embed


def _rsi_bar(rsi: float | None) -> str:
    """Return a small emoji indicator showing where RSI sits on the scale."""
    if rsi is None:
        return ""
    if rsi < 30:
        return "🟢 *Oversold*"
    if rsi < 35:
        return "🟩 *Near Oversold*"
    if rsi > 70:
        return "🔴 *Overbought*"
    if rsi > 65:
        return "🟧 *Near Overbought*"
    return "⚪ *Neutral*"


# ── Entry Point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    bot.run(TOKEN)