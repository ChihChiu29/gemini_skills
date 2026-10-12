---
name: stock-lows-analyzer
description: Analyzes major U.S. stocks and ETFs to find those trading near historical lows (3m, 6m, 3y). Generates an interactive HTML report with price charts and a summary table highlighting buying opportunities.
---

# Stock Multi-Period Grid & Grouped Watchlist Analyzer

This skill provides a comprehensive grid analysis of stocks across four key time periods (3Y, 6M, 3M, 7D) with tiered recommendations.

## Workflow

1.  **Identify Symbols**: By default, the script reads all symbols from `references/tech_stocks.md`. You can also provide a specific list as arguments.
2.  **Environment Check**: Verify `yfinance` is installed (`pip install yfinance`).
3.  **Run Analysis**: Execute `scripts/analyze_stocks.py`.
4.  **Open Report**: The script generates a timestamped report in the `OUTPUT/` directory.

## Using the Scripts

### Stock Lows Analysis
Run the stock analysis script to analyze all default symbols:

```bash
python scripts/analyze_stocks.py
```

Or analyze specific symbols:

```bash
python scripts/analyze_stocks.py TSLA NVDA AMZN
```

### Options Trading Analysis
Run the options analysis script to fetch put option chains for the upcoming Friday and next Friday:

```bash
# Default: generates reports for both upcoming Friday and next Friday
python scripts/analyze_options.py

# Or target a specific Friday using the --day flag
python scripts/analyze_options.py --day upcoming
python scripts/analyze_options.py --day next
python scripts/analyze_options.py --day both AAPL NVDA TSLA
```

Or execute via the single-line batch script:

```bash
.\run_option_skill.bat
.\run_option_skill.bat --day both AAPL NVDA
```

### Analysis Features
- **Automatic Symbol Fetching**: Automatically reads curated lists from `references/` or accepts custom symbols on CLI.
- **Dual Friday Generation**: By default (`--day both`), generates two separate HTML reports—one for the upcoming Friday (or today if Friday) and one for next week's Friday.
- **Standardized Filename Format**:
  `option_price_<target_date>_<report_generation_date>_<report_generation_time>.html` (e.g. `option_price_20261009_20261009_1003.html` and `option_price_20261016_20261009_1003.html`).
- **Options Trading Analysis (`analyze_options.py`)**:
    - Fetches live **PUT** option chains for each target expiry.
    - Slices 5 strikes above and 5 strikes below the ATM strike (11 contracts), ordered from +5 down to -5.
    - Highlights Bid / Stock % in green when >= 0.5%.
    - Re-uses symbol price and historical range tags across both dates for maximum speed.
- **Categorized BUY Targets**:
    - **Long Term BUY**: Triggered if at least 2 long-term periods (3Y, 6M, 3M) are near their lows (<15% for 3Y/6M, <20% for 3M).
    - **Short Term BUY**: Triggered if 7D Pos% is low (<25%) AND 7D Volatility is significant (>=10%), OR if 3M Volatility is high (>50%) and 3M Pos% is low (<20%).
- **Categorized SELL Targets**: Triggered if price is near multi-period highs (>95% for 3Y/6M/3M/7D).
- **Categorized WATCHLIST**: Triggered by high volatility (3M > 50% or 7D > 20%).
- **Grouped Results**: Stocks are categorized into **BUY TARGETS**, **SELL TARGETS**, **WATCHLIST**, and **OTHER STOCKS**.
- **Alphabetical Sorting**: Each category is sorted alphabetically.
- **Precision Highlighting**: Red (BUY signal), Green (SELL signal), and Orange (WATCH signal) cell backgrounds.
- **Caching**: Historical data (Close, High, Low) is cached for 24 hours.

## Output
- **Organized Storage**: Reports are stored under subdirectories in `OUTPUT/`:
  - `OUTPUT/stock_prices/`: Stock grid analysis reports (`stock_report_*.html`).
  - `OUTPUT/stock_options/`: Options trading chain reports (`options_report_*.html`).
- **Grouped Interface**: Interactive reports feature categorized tables, summary cards, and price charts.

## Reference Material
- [references/tech_stocks.md](references/tech_stocks.md): Curated list of major U.S. tech and growth stocks.
- [references/nontech_stocks.md](references/nontech_stocks.md): Non-tech curated stocks.
- [references/manual_stocks.md](references/manual_stocks.md): Manually tracked stocks.
