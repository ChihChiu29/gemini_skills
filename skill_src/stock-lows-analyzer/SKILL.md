---
name: stock-lows-analyzer
description: Analyzes major U.S. stocks to find those trading near historical lows (3m, 6m, 3y). Generates an interactive HTML report with price charts and a summary table highlighting buying opportunities.
---

# Stock Volatility & Lows Analyzer

This skill provides a deep analysis of stocks relative to historical lows, recent price trends, and market volatility.

## Workflow

1.  **Identify Symbols**: Use `references/tech_stocks.md` for major tech tickers or ask the user for a list.
2.  **Environment Check**: Verify `yfinance` is installed (`pip install yfinance`).
3.  **Run Analysis**: Execute `scripts/analyze_stocks.py` with the chosen symbols.
4.  **Open Report**: The script generates a timestamped report in the `OUTPUT/` directory (e.g., `OUTPUT/stock_report_20260417_235959.html`).

## Using the Script

Run the script with stock symbols:

```bash
python scripts/analyze_stocks.py TSLA NVDA AMZN GOOGL
```

### Analysis Features
- **Historical Proximity (4 Columns)**: Proximity to 3-year, 6-month, 3-month, and 7-day lows.
- **Trend Analysis (2 Columns)**: Daily price change (%) and 7-day average daily change (%).
- **Volatility Analysis (2 Columns)**: High-Low price spread for the last 7 days and 30 days (%).
- **Highlighting Logic**:
    - **Orange**: Stock is within 15% of a historical low OR shows high volatility (>7% in 7D or >15% in 30D).
    - **Red**: Stock meets the "Orange" criteria AND is currently dropping (negative daily or 7D average trend).
- **Caching**: Historical data (Close, High, Low) is cached in `CACHE/stock_cache/` for 24 hours.

## Output
- **Organized Storage**: All reports are stored in the `OUTPUT/` directory.
- **Dynamic Filenames**: Reports are named `stock_report_<YYYYMMDD>_<HHMMSS>.html`.
- **Status Indicators**: Explicit labels for "Near Support", "High Volatility", and "CRITICAL" states.

## Reference Material
- [references/tech_stocks.md](references/tech_stocks.md): Curated list of major U.S. tech and growth stocks.
