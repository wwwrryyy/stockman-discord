# Quant-Core AI — Build Log

## Current Status: ✅ Phase 2 Complete

| Phase | Feature | Status |
|-------|---------|--------|
| 1 | Bot boilerplate + `/analyze` stub | ✅ Done |
| 2 | yfinance data + pandas-ta indicators | ✅ Done |
| 3 | mplfinance candlestick chart | ⏳ Next |
| 4 | LLM API verdict engine | ⏳ Pending |
| 5 | SQLite DB + `/watchlist` commands | ⏳ Pending |
| 6 | Background scanner + auto-alerts | ⏳ Pending |
| 7 | News API + sentiment scoring | ⏳ Pending |
| 8 | Paper trading + `/portfolio` P&L | ⏳ Pending |

## Phase 2 — New Files

| File | Purpose |
|------|---------|
| `data.py` | All yfinance fetching + pandas-ta indicator math |
| `bot.py` | Updated: `/analyze` now calls `data.py` and posts a real embed |

### Install Phase 2 Dependencies

```bash
pip install yfinance pandas pandas-ta
```

### File Structure (Phase 2)

```
quant_core/
├── bot.py          ← updated
├── data.py         ← new: all data & indicator logic
├── requirements.txt
├── .env
└── README.md
```

### What `/analyze AAPL` Now Returns

A rich Discord embed containing:
- Current price + % change vs previous close
- RSI-14 with oversold/overbought label
- SMA-50 and SMA-200 values
- MACD, MACD Signal, MACD Histogram
- P/E ratio, Market Cap, Sector, Industry, 52-week range
- Signal tags (e.g. `OVERSOLD`, `BELOW_200_SMA`, `COMPOSITE_BUY_SIGNAL`)
- Plain-English signal detail summary
- Placeholder fields for chart (Phase 3) and LLM verdict (Phase 4)

### Key Design Decisions

**`asyncio.to_thread()`** — yfinance is a blocking synchronous library. Calling it directly inside an `async` Discord handler freezes the entire bot. `to_thread()` offloads it to a thread pool, keeping the event loop free.

**`data.py` has zero Discord imports** — independently testable. Run `python -c "from data import fetch_analysis_data; print(fetch_analysis_data('AAPL'))"` to debug data issues without needing the bot online.

**8 months of OHLCV requested, 6 months displayed** — the 200-day SMA needs ~200 bars of history. Requesting only 6 months (~126 bars) would make SMA_200 return NaN for all rows.

---

## Phase 1 Setup — Get the Bot Online

### Step 1 — Create the Discord Application

1. Go to https://discord.com/developers/applications
2. Click **New Application** → name it `Quant-Core`
3. Sidebar → **Bot** → click **Add Bot**
4. Under **Token** → click **Reset Token** → **copy it immediately** (shown once)
5. Scroll down to **Privileged Gateway Intents** → enable:
   - ✅ Message Content Intent
   - ✅ Server Members Intent (for tagging yourself in alerts later)

### Step 2 — Invite the Bot to Your Server

1. Sidebar → **OAuth2** → **URL Generator**
2. Scopes: ✅ `bot` ✅ `applications.commands`
3. Bot Permissions: ✅ Send Messages ✅ Embed Links ✅ Attach Files ✅ Read Message History ✅ Mention Everyone
4. Copy the generated URL → open in browser → select your private server → **Authorize**

### Step 3 — Configure Environment

```bash
cd quant_core
cp .env.example .env
# Open .env and paste your DISCORD_TOKEN
```

### Step 4 — Install & Run

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install discord.py python-dotenv
python bot.py
```

### Step 5 — Verify

You should see in your terminal:
```
✅  Logged in as: Quant-Core#XXXX (ID: ...)
✅  Synced 1 slash command(s) globally.
    /analyze
    Quant-Core is online. Waiting for commands...
```

In Discord, type `/analyze AAPL` — the bot should reply:
> 📡 Fetching data for **AAPL**...
> *(Full analysis pipeline coming in Phase 2)*

---

## Notes on Slash Command Sync

`bot.tree.sync()` called in `on_ready` syncs commands **globally**.
Global sync can take up to **1 hour** to propagate to all servers.

For instant testing during development, switch to guild-specific sync by replacing:
```python
synced = await bot.tree.sync()
```
with:
```python
MY_GUILD = discord.Object(id=YOUR_SERVER_ID_HERE)
bot.tree.copy_global_to(guild=MY_GUILD)
synced = await bot.tree.sync(guild=MY_GUILD)
```
Commands synced to a specific guild appear **instantly**.

---

*Say "Phase 2" when you're ready to add yfinance + pandas-ta indicators.*