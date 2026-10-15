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
Run the options analysis script to fetch put option chains and/or covered call chains:

```bash
# Default: generates reports for both PUT (2 upcoming Fridays) and Covered CALL (next 4 Fridays)
python scripts/analyze_options.py

# Select option type using --type:
python scripts/analyze_options.py --type put
python scripts/analyze_options.py --type call
python scripts/analyze_options.py --type both

# Target a specific Friday using the --day flag
python scripts/analyze_options.py --day upcoming
python scripts/analyze_options.py --day next
python scripts/analyze_options.py --type both --day both AAPL NVDA TSLA
```

Or execute via the batch script:

```bash
.\run_option_skill.bat
.\run_option_skill.bat --type call AAPL NVDA
```

### Analysis Features
- **Automatic Symbol Fetching**: Automatically reads curated lists from `references/` or accepts custom symbols on CLI.
- **PUT Options Analysis**:
  - Generates reports for 2 upcoming Fridays by default.
  - Slices 5 strikes above and 5 strikes below the ATM strike (11 contracts), ordered from +5 down to -5.
  - Summary table spotlights Strike -2 and Strike -3 (OTM puts) with Bid, Bid/Stock %, and Last price.
  - Highlights Bid / Stock % in green when >= 0.5%.
- **Covered Calls Analysis**:
  - Generates reports for the next 4 Fridays by default.
  - Evaluates out-of-the-money call selling opportunities for income generation and upside capture.
  - Summary table features 3 strikes: **Strike +1**, **Strike +2**, and **Strike +3**.
  - Displays **Bid / Stock %** (flat premium yield) and **Max Return %** (return if assigned: `((Strike - Stock Price) + Bid) / Stock Price`).
  - Slices ATM ± 5 strikes, ordered from lowest strike to highest strike with ATM highlighted in yellow.
- **Earnings Date Tracking**: Includes an interactive sortable **Earnings Date** column with warning badges (`⚠️ YYYY-MM-DD`) if earnings announcement occurs on or before option expiration.
- **Stock Grid Analysis (`analyze_stocks.py`)**:
    - **Earnings Date Tracking**: Features an **Earnings Date** column with warning badges (`⚠️ YYYY-MM-DD`) highlighting events within 14 days.
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
  - `OUTPUT/stock_options/`: Options trading reports organized by target date and type:
    - `<YYYYMMDD>_PUT/put_<YYYYMMDD>_<HHMM>.html`
    - `<YYYYMMDD>_CALL/call_<YYYYMMDD>_<HHMM>.html`
    - `old_results/`: Archived historical options reports.
- **Grouped Interface**: Interactive reports feature categorized tables, summary cards, and price charts.

## Reference Material
- [references/tech_stocks.md](references/tech_stocks.md): Curated list of major U.S. tech and growth stocks.
- [references/nontech_stocks.md](references/nontech_stocks.md): Non-tech curated stocks.
- [references/manual_stocks.md](references/manual_stocks.md): Manually tracked stocks.
