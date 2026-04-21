---
name: stock-lows-analyzer
description: Analyzes major U.S. stocks to find those trading near historical lows (3m, 6m, 3y). Generates an interactive HTML report with price charts and a summary table highlighting buying opportunities.
---

# Stock Multi-Period Grid & Grouped Watchlist Analyzer

This skill provides a comprehensive grid analysis of stocks across four key time periods (3Y, 6M, 3M, 7D) with tiered recommendations.

## Workflow

1.  **Identify Symbols**: By default, the script reads all symbols from `references/tech_stocks.md`. You can also provide a specific list as arguments.
2.  **Environment Check**: Verify `yfinance` is installed (`pip install yfinance`).
3.  **Run Analysis**: Execute `scripts/analyze_stocks.py`.
4.  **Open Report**: The script generates a timestamped report in the `OUTPUT/` directory.

## Using the Script

Run the script to analyze all default symbols:

```bash
python scripts/analyze_stocks.py
```

Or analyze specific symbols:

```bash
python scripts/analyze_stocks.py TSLA NVDA AMZN
```

### Analysis Features
- **Automatic Symbol Fetching**: If no symbols are provided, it automatically reads the curated list from `references/tech_stocks.md`.
- **Categorized BUY Targets**:
    - **Long Term BUY**: Triggered if at least 2 long-term periods (3Y, 6M, 3M) are near their lows (<15% for 3Y/6M, <20% for 3M).
    - **Short Term BUY**: Triggered if 7D Pos% is low (<25%) AND 7D Volatility is significant (>=10%).
- **Categorized SELL Targets**: Triggered if price is near multi-period highs (>95% for 3Y/6M/3M/7D).
- **Categorized WATCHLIST**: Triggered by high volatility (3M > 50% or 7D > 20%).
- **Grouped Results**: Stocks are categorized into **BUY TARGETS**, **SELL TARGETS**, **WATCHLIST**, and **OTHER STOCKS**.
- **Alphabetical Sorting**: Each category is sorted alphabetically.
- **Precision Highlighting**: Red (BUY signal), Green (SELL signal), and Orange (WATCH signal) cell backgrounds.
- **Caching**: Historical data (Close, High, Low) is cached for 24 hours.

## Output
- **Organized Storage**: All reports are stored in the `OUTPUT/` directory.
- **Grouped Interface**: Interactive reports feature categorized tables followed by price charts.

## Reference Material
- [references/tech_stocks.md](references/tech_stocks.md): Curated list of major U.S. tech and growth stocks.
