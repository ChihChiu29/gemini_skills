---
name: chinese-forum-sentiment
description: Scans Chinese retail trading forums (Eastmoney Guba, PTT Stock) for real-time sentiment, crowd bias, and expected price target ranges for US-traded stocks (US equities & Chinese ADRs) heading into next week's Friday close.
---

# Chinese Forum Stock Sentiment & Price Range Scanner

This skill monitors and extracts crowd sentiment from high-activity, free-to-participate Chinese retail investor boards (Eastmoney Guba / 东方财富股吧, PTT Stock / 批踢踢股板) to gauge short-term sentiment and predict expected price ranges through next week's Friday close.

## Workflow

1. **Verify Environment**: Uses standard Python 3 with `yfinance` (for live quotes) and `beautifulsoup4` (for PTT HTML parsing).
2. **Execute Scanner**: Run `scripts/stock_sentiment_scanner.py [TICKER]` (e.g. `BIDU`, `TSLA`, `NVDA`, `BABA`).
3. **Review Output**: Generates an actionable terminal summary and a Markdown report under `OUTPUT/`.

## Usage Instructions

### Multi-Symbol Sentiment Scan
Scan sentiment for any list of US stocks or Chinese ADRs (default is `BIDU` if not specified):

```bash
python skill_src/chinese-forum-sentiment/scripts/stock_sentiment_scanner.py BIDU NKE PCG VTKX
```

Or run via the repository batch shortcut:
```bat
.\run_sentiment_skill.bat BIDU NKE PCG VTKX
```

### Options & Arguments

- `symbols`: List of stock ticker symbols separated by space (e.g. `BIDU NKE PCG VTKX`). Auto-maps to Chinese aliases.
- `--pages N`: Number of pages to scan on Eastmoney Guba per symbol (default: `2`).
- `--ptt-max N`: Max discussion threads to scan on PTT Stock per symbol (default: `10`).
- `--force-refresh`: Bypasses daily cache and fetches fresh forum data.
- `--no-cache`: Disables saving scraped results to the daily cache.
- `--output-dir PATH`: Directory where generated HTML and Markdown reports are saved (defaults to `OUTPUT/forum_sentiment/`).

## Analysis Features

- **Daily Smart Caching**: Automatically saves forum results under `CACHE/forum_sentiment/<TICKER>_YYYYMMDD.json`. Consecutive runs on the same day complete in seconds without hitting external rate limits.
- **Table-First HTML Report**: Generates an interactive, dark-mode comparison table complete with sentiment distribution bars, expected price ranges, and thread highlights.
- **Next Friday Target Horizon**: Automatically aligns the forecast window from the current day to next week's Friday close (4:00 PM EST).
- **Dual Forum Sourcing**:
  - **Eastmoney Guba (东财股吧)**: High-volume retail opinions, hype, and panic commentary for US stocks and ADRs.
  - **PTT Stock (批踢踢股板)**: Retail discussion threads and comment "pushes" (推/噓/箭頭), known for high retail price targets and call/put debates.
- **Sentiment & Target Range Engine**:
  - Classifies posts and comment pushes into **Bullish (看多)**, **Bearish (看空)**, and **Neutral (觀望)**.
  - Detects explicit retail price targets (`上看 100`, `跌到 70`) and percentage shifts (`+15%`, `-5%`).
  - Handles delisted / unlisted tickers cleanly (e.g., `VTKX`).
