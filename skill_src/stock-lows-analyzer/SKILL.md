---
name: stock-lows-analyzer
description: Analyzes major U.S. stocks to find those trading near historical lows (3m, 6m, 3y). Generates an interactive HTML report with price charts and a summary table highlighting buying opportunities.
---

# Stock Trend & Lows Analyzer

This skill provides a deep analysis of stocks relative to historical lows and recent price trends.

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
- **Highlighting Logic**:
    - **Orange**: Stock is within 15% of its 3-year, 6-month, or 3-month low.
    - **Red**: Stock is in the "Orange" zone AND either its daily price or 7-day average is negative (dropping).
- **Caching**: Historical data is cached in `CACHE/stock_cache/` for 24 hours to reduce API fetching.

## Output
- **Organized Storage**: All reports are stored in the `OUTPUT/` directory.
- **Dynamic Filenames**: Reports are named `stock_report_<YYYYMMDD>_<HHMMSS>.html`.
- **Status Indicators**: Explicit labels for "Near Support" or "CRITICAL (Dropping at Low)".

## Reference Material
- [references/tech_stocks.md](references/tech_stocks.md): Curated list of major U.S. tech and growth stocks.
