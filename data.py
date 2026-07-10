"""
Quant-Core AI — data.py (Phase 2)
-----------------------------------
Responsible for ALL data fetching and indicator math.
Nothing in this file touches Discord — it is pure data logic,
making it easy to test independently and reuse in later phases.

Public API (what bot.py imports):
    fetch_analysis_data(ticker: str) -> AnalysisData | None

Internal helpers:
    _fetch_ohlcv()
    _calculate_indicators()
    _fetch_fundamentals()
    _classify_signals()
"""

from __future__ import annotations

import traceback
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd
import yfinance as yf


# ── Output Data Structure ─────────────────────────────────────────────────────

@dataclass
class AnalysisData:
    """
    Single container that carries every piece of data the bot needs.
    Passed from data.py → bot.py (Phase 2) → chart.py (Phase 3) → llm.py (Phase 4).
    """
    ticker: str

    # Price snapshot
    current_price: float = 0.0
    prev_close: float = 0.0
    price_change_pct: float = 0.0

    # Indicators (latest bar values)
    rsi: Optional[float] = None
    sma_50: Optional[float] = None
    sma_200: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_hist: Optional[float] = None

    # Fundamentals
    pe_ratio: Optional[float] = None
    market_cap: Optional[str] = None   # human-readable, e.g. "$2.87T"
    sector: Optional[str] = None
    industry: Optional[str] = None
    fifty_two_week_high: Optional[float] = None
    fifty_two_week_low: Optional[float] = None
    short_name: Optional[str] = None

    # Signal tags produced by _classify_signals()
    # e.g. ["OVERSOLD", "BELOW_200_SMA", "MACD_BEARISH"]
    signal_tags: list[str] = field(default_factory=list)
    signal_summary: str = ""

    # LLM Verdict & Rationale (Phase 4)
    llm_verdict: Optional[str] = None
    llm_rationale: Optional[str] = None

    # Raw DataFrame (needed by chart.py in Phase 3)
    df: Optional[pd.DataFrame] = None


# ── Public Entry Point ────────────────────────────────────────────────────────

def fetch_analysis_data(ticker: str) -> Optional[AnalysisData]:
    """
    Master function. Orchestrates all fetching and calculations.
    Returns a populated AnalysisData or None if the ticker is invalid / API down.

    Deliberately synchronous — called inside asyncio.to_thread() in bot.py
    so it never blocks the Discord event loop.
    """
    ticker = ticker.upper().strip()
    result = AnalysisData(ticker=ticker)

    try:
        # ── Step 1: Fetch 6 months of OHLCV ──────────────────────────────────
        df = _fetch_ohlcv(ticker)
        if df is None or df.empty:
            return None

        # ── Step 2: Calculate indicators onto the DataFrame ───────────────────
        df = _calculate_indicators(df)
        result.df = df

        # ── Step 3: Extract latest-bar scalar values ──────────────────────────
        latest = df.iloc[-1]
        prev   = df.iloc[-2] if len(df) >= 2 else latest

        result.current_price    = float(latest["Close"])
        result.prev_close       = float(prev["Close"])
        result.price_change_pct = (
            (result.current_price - result.prev_close) / result.prev_close * 100
        )

        result.rsi         = _safe_float(latest.get("RSI_14"))
        result.sma_50      = _safe_float(latest.get("SMA_50"))
        result.sma_200     = _safe_float(latest.get("SMA_200"))
        result.macd        = _safe_float(latest.get("MACD_12_26_9"))
        result.macd_signal = _safe_float(latest.get("MACDs_12_26_9"))
        result.macd_hist   = _safe_float(latest.get("MACDh_12_26_9"))

        # ── Step 4: Fetch fundamentals ────────────────────────────────────────
        _fetch_fundamentals(ticker, result)

        # ── Step 5: Classify signals into human-readable tags ─────────────────
        _classify_signals(result)

        return result

    except Exception:
        # Print full traceback to terminal for debugging; bot.py handles user message.
        traceback.print_exc()
        return None


# ── Internal Helpers ──────────────────────────────────────────────────────────

def _fetch_ohlcv(ticker: str) -> Optional[pd.DataFrame]:
    """
    Pull 6 months of daily OHLCV from Yahoo Finance.
    Returns None if the ticker is invalid or yfinance returns empty data.

    Note: We request 8 months so the 200-day SMA has enough history to be
    non-NaN in the most recent rows. The chart will still only show 6 months.
    """
    try:
        stock = yf.Ticker(ticker)
        # auto_adjust=True folds splits/dividends into OHLC automatically.
        df = stock.history(period="8mo", interval="1d", auto_adjust=True)

        if df is None or df.empty:
            print(f"[data] yfinance returned empty DataFrame for '{ticker}'")
            return None

        df.index = pd.to_datetime(df.index)

        # Ensure columns exist and are numeric
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            if col not in df.columns:
                print(f"[data] Missing column '{col}' for '{ticker}'")
                return None
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df.dropna(subset=["Close"], inplace=True)
        return df

    except Exception as e:
        print(f"[data] _fetch_ohlcv error for '{ticker}': {e}")
        return None


def _calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add RSI-14, SMA-50, SMA-200, and MACD(12,26,9) to the DataFrame
    using pandas-ta. All columns are added in-place to the same df.

    pandas-ta column naming conventions used here:
        RSI   → RSI_14
        SMA   → SMA_50, SMA_200
        MACD  → MACD_12_26_9, MACDs_12_26_9, MACDh_12_26_9
    """
    try:
        import pandas_ta as ta  # imported here so error is clear if not installed
    except ImportError:
        raise ImportError(
            "pandas-ta is not installed. Run: pip install pandas-ta"
        )

    df = df.copy()

    # RSI — 14-period Relative Strength Index
    df.ta.rsi(length=14, append=True)

    # Simple Moving Averages
    df.ta.sma(length=50, append=True)
    df.ta.sma(length=200, append=True)

    # MACD — standard 12/26/9 settings
    # Appends 3 columns: MACD_12_26_9, MACDs_12_26_9, MACDh_12_26_9
    df.ta.macd(fast=12, slow=26, signal=9, append=True)

    return df


def _fetch_fundamentals(ticker: str, result: AnalysisData) -> None:
    """
    Populate fundamental fields on result in-place.
    Uses yfinance .info dict. Silently skips fields that are missing —
    yfinance .info is notoriously inconsistent across ticker types.
    """
    try:
        info = yf.Ticker(ticker).info

        # P/E ratio — prefer trailing, fall back to forward
        pe = info.get("trailingPE") or info.get("forwardPE")
        result.pe_ratio = round(float(pe), 2) if pe else None

        # Market cap — format to human-readable string
        mc = info.get("marketCap")
        if mc:
            if mc >= 1_000_000_000_000:
                result.market_cap = f"${mc / 1_000_000_000_000:.2f}T"
            elif mc >= 1_000_000_000:
                result.market_cap = f"${mc / 1_000_000_000:.2f}B"
            elif mc >= 1_000_000:
                result.market_cap = f"${mc / 1_000_000:.2f}M"
            else:
                result.market_cap = f"${mc:,.0f}"

        result.sector              = info.get("sector")
        result.industry            = info.get("industry")
        result.fifty_two_week_high = info.get("fiftyTwoWeekHigh")
        result.fifty_two_week_low  = info.get("fiftyTwoWeekLow")
        result.short_name          = info.get("shortName") or ticker

    except Exception as e:
        # Fundamentals failing should NOT abort the whole analysis.
        print(f"[data] _fetch_fundamentals non-fatal error for '{ticker}': {e}")


def _classify_signals(result: AnalysisData) -> None:
    """
    Apply the PRD's hardcoded quant rules to produce signal_tags and
    a plain-English signal_summary string.

    Tags are consumed by:
      - bot.py (Phase 2)  → displayed in the data embed
      - llm.py (Phase 4)  → injected into the LLM prompt
      - cogs/scanner.py   → alert trigger logic
    """
    tags: list[str] = []
    notes: list[str] = []

    rsi    = result.rsi
    price  = result.current_price
    sma50  = result.sma_50
    sma200 = result.sma_200
    macd   = result.macd
    macdS  = result.macd_signal
    pe     = result.pe_ratio

    # ── RSI ──────────────────────────────────────────────────────────────────
    if rsi is not None:
        if rsi < 30:
            tags.append("OVERSOLD")
            notes.append(f"RSI {rsi:.1f} — deeply oversold (< 30).")
        elif rsi < 35:
            tags.append("RSI_NEAR_OVERSOLD")
            notes.append(f"RSI {rsi:.1f} — approaching oversold territory (< 35).")
        elif rsi > 70:
            tags.append("OVERBOUGHT")
            notes.append(f"RSI {rsi:.1f} — overbought (> 70).")
        elif rsi > 65:
            tags.append("RSI_NEAR_OVERBOUGHT")
            notes.append(f"RSI {rsi:.1f} — approaching overbought territory (> 65).")
        else:
            tags.append("RSI_NEUTRAL")

    # ── Price vs SMAs ─────────────────────────────────────────────────────────
    if price and sma200 is not None:
        if price < sma200:
            tags.append("BELOW_200_SMA")
            notes.append(f"Price ${price:.2f} is below the 200-day SMA (${sma200:.2f}) — bearish long-term structure.")
        else:
            tags.append("ABOVE_200_SMA")
            notes.append(f"Price ${price:.2f} is above the 200-day SMA (${sma200:.2f}) — bullish long-term structure.")

    if price and sma50 is not None:
        if price < sma50:
            tags.append("BELOW_50_SMA")
            notes.append(f"Price is below the 50-day SMA (${sma50:.2f}) — near-term bearish.")
        else:
            tags.append("ABOVE_50_SMA")

    # ── Golden / Death Cross ──────────────────────────────────────────────────
    if sma50 is not None and sma200 is not None:
        if sma50 > sma200:
            tags.append("GOLDEN_CROSS_ZONE")
            notes.append("50-day SMA is above 200-day SMA — golden cross zone (bullish).")
        else:
            tags.append("DEATH_CROSS_ZONE")
            notes.append("50-day SMA is below 200-day SMA — death cross zone (bearish).")

    # ── MACD ─────────────────────────────────────────────────────────────────
    if macd is not None and macdS is not None:
        if macd > macdS:
            tags.append("MACD_BULLISH")
            notes.append("MACD line is above signal line — bullish momentum.")
        else:
            tags.append("MACD_BEARISH")
            notes.append("MACD line is below signal line — bearish momentum.")

    # ── P/E Valuation ─────────────────────────────────────────────────────────
    if pe is not None:
        if pe < 15:
            tags.append("LOW_PE")
            notes.append(f"P/E of {pe} — potentially undervalued.")
        elif pe > 40:
            tags.append("HIGH_PE")
            notes.append(f"P/E of {pe} — potentially overvalued or growth-priced.")

    # ── Composite PRD Rules ───────────────────────────────────────────────────
    # Rule 1 (from PRD §4): RSI < 35 AND price near/below 200 SMA → BUY lean
    buy_rsi   = "OVERSOLD" in tags or "RSI_NEAR_OVERSOLD" in tags
    buy_price = "BELOW_200_SMA" in tags
    if buy_rsi and buy_price:
        tags.append("COMPOSITE_BUY_SIGNAL")
        notes.append("🟢 COMPOSITE BUY: oversold RSI + price below 200-day SMA.")

    # Rule 2 (from PRD §4): RSI > 70 → SELL lean
    if "OVERBOUGHT" in tags:
        tags.append("COMPOSITE_SELL_SIGNAL")
        notes.append("🔴 COMPOSITE SELL: RSI overbought (> 70).")

    result.signal_tags    = tags
    result.signal_summary = " | ".join(notes) if notes else "No strong directional signals."


# ── Utility ───────────────────────────────────────────────────────────────────

def _safe_float(val) -> Optional[float]:
    """Convert a value to float, return None if NaN or unconvertible."""
    try:
        f = float(val)
        return None if pd.isna(f) else round(f, 4)
    except (TypeError, ValueError):
        return None