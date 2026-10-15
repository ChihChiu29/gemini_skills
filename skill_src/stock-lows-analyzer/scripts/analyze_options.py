"""
Options Analysis Script - Fetches live PUT option chain data for the upcoming Friday
and generates an HTML report with per-symbol strike tables and a summary.
"""
import os
import sys
import json
import datetime
import re
import time
from pathlib import Path
import pandas as pd

try:
    import yfinance as yf
except ImportError:
    print("Error: 'yfinance' library not found. Please install it using 'pip install yfinance'.")
    sys.exit(1)

PROJECT_ROOT = Path(__file__).resolve().parents[3]

OUTPUT_DIR = PROJECT_ROOT / "OUTPUT" / "stock_options"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

NUM_STRIKES_ABOVE = 5
NUM_STRIKES_BELOW = 5


# ---------------------------------------------------------------------------
import argparse


# ---------------------------------------------------------------------------
# CLI Argument and Symbol loading
# ---------------------------------------------------------------------------

def parse_cli_args():
    """Parse CLI arguments for option type, target day selection, and optional symbol list."""
    parser = argparse.ArgumentParser(
        description="Fetch live option chains (PUT / Covered CALL) and generate HTML report(s)."
    )
    parser.add_argument(
        "--type",
        choices=["put", "call", "both"],
        default="both",
        help="Type of option report to generate: 'put', 'call', or 'both' (default: 'both')."
    )
    parser.add_argument(
        "--day",
        choices=["upcoming", "next", "both", "all"],
        default="both",
        help=(
            "Target expiry Friday: 'upcoming' (this Friday or today if Friday), "
            "'next' (next week's Friday), or 'both'/'all' (default: 2 Fridays for PUT, 4 Fridays for CALL)."
        )
    )
    parser.add_argument(
        "symbols",
        nargs="*",
        default=[],
        help="Optional stock symbols to analyze (overrides reference files)."
    )
    args = parser.parse_args()

    symbols = [s.upper().strip() for s in args.symbols if s.strip()]
    if not symbols:
        ref_dir = Path(__file__).parent.parent / "references"
        for fname in ["tech_stocks.md", "nontech_stocks.md", "manual_stocks.md"]:
            p = ref_dir / fname
            if p.exists():
                with open(p, "r", encoding="utf-8") as f:
                    symbols.extend(re.findall(r'^[ \t]*-[ \t]+([A-Z]+)', f.read(), re.MULTILINE))
        symbols = list(dict.fromkeys(symbols))  # deduplicate, preserve order

    return args.type.lower(), args.day, symbols


def load_symbols():
    """Backward-compatible helper to load symbols."""
    _, _, symbols = parse_cli_args()
    return symbols


# ---------------------------------------------------------------------------
# Stock price and position tags helper (live fetch)
# ---------------------------------------------------------------------------

PERIOD_CONFIGS = [
    ("1y", 365, 10),
    ("6m", 180, 10),
    ("3m", 90, 20),
    ("1m", 30, 20),
    ("7d", 7, 30),
]


def fetch_stock_price_and_tags(symbol):
    """Fetch current stock price and 5 range-position tags (1y, 6m, 3m, 1m, 7d)."""
    import math
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="1y")
        if hist.empty:
            return None, []

        price = ticker.fast_info.get('lastPrice')
        if price is None or (isinstance(price, float) and math.isnan(price)):
            price = float(hist['Close'].iloc[-1])
        price = round(float(price), 2)

        today = datetime.date.today()
        tags = []
        for label, days, threshold in PERIOD_CONFIGS:
            cutoff = (today - datetime.timedelta(days=days)).isoformat()
            if hist.index.tz is not None:
                sub = hist[hist.index >= pd.Timestamp(cutoff).tz_localize(hist.index.tz)]
            else:
                sub = hist[hist.index >= pd.Timestamp(cutoff)]

            if not sub.empty:
                high = max(float(sub['High'].max()), price)
                low = min(float(sub['Low'].min()), price)
                pos = (price - low) / (high - low) * 100 if high > low else 0.0
            else:
                pos = 0.0

            pos = round(pos, 1)
            is_red = pos < threshold
            tags.append({
                "label": f"{label}:{int(round(pos))}%",
                "is_red": is_red,
                "pos": pos,
                "key": label,
            })

        # Fetch next earnings date from calendar if available
        earnings_date = None
        try:
            cal = ticker.calendar
            if cal and isinstance(cal, dict):
                ed_list = cal.get('Earnings Date')
                if ed_list and len(ed_list) > 0 and ed_list[0]:
                    raw_ed = ed_list[0]
                    if hasattr(raw_ed, 'date'):
                        earnings_date = raw_ed.date()
                    elif isinstance(raw_ed, datetime.date):
                        earnings_date = raw_ed
                    elif isinstance(raw_ed, str):
                        earnings_date = datetime.datetime.strptime(raw_ed[:10], "%Y-%m-%d").date()
        except Exception:
            pass

        return price, tags, earnings_date
    except Exception as e:
        print(f"  Warning: could not get price/history for {symbol}: {e}")
        return None, [], None


# ---------------------------------------------------------------------------
# Upcoming Friday calculation
# ---------------------------------------------------------------------------

def get_upcoming_friday():
    """Return the upcoming Friday as a datetime.date. If today is Friday, return today."""
    today = datetime.date.today()
    days_until = (4 - today.weekday()) % 7
    if days_until == 0 and today.weekday() != 4:
        days_until = 7  # safety
    return today + datetime.timedelta(days=days_until)


def get_target_fridays_for_type(option_type, day_mode="both"):
    """
    Return target Friday dates based on option_type and day_mode:
    - 'upcoming': Upcoming Friday (or today if Friday)
    - 'next': Next week's Friday (upcoming Friday + 7 days)
    - 'both' / 'all': 2 Fridays for PUT, 4 Fridays for CALL.
    """
    upcoming = get_upcoming_friday()
    if day_mode == "upcoming":
        return [upcoming]
    elif day_mode == "next":
        return [upcoming + datetime.timedelta(days=7)]

    count = 4 if option_type.upper() == "CALL" else 2
    return [upcoming + datetime.timedelta(days=7 * i) for i in range(count)]


def get_target_fridays(day_mode="both"):
    """Backward-compatible helper returning 2 Fridays for PUT."""
    return get_target_fridays_for_type("PUT", day_mode)


def find_best_expiry(expiries_or_symbol, target_friday):
    """Find the available expiry date closest to target_friday."""
    if isinstance(expiries_or_symbol, (list, tuple)):
        expiries = expiries_or_symbol
    else:
        try:
            ticker = yf.Ticker(expiries_or_symbol)
            expiries = ticker.options
        except Exception:
            return None

    if not expiries:
        return None
    target_str = target_friday.isoformat()
    if target_str in expiries:
        return target_str
    try:
        return min(expiries, key=lambda x: abs(
            datetime.datetime.strptime(x, "%Y-%m-%d").date() - target_friday
        ))
    except Exception as e:
        print(f"  Warning: could not match expiry date: {e}")
        return None


# ---------------------------------------------------------------------------
# Fetch and process option chain
# ---------------------------------------------------------------------------

def process_option_chain(symbol, expiry_str, current_price, contracts_df, tags=None, earnings_date=None, option_type="PUT"):
    """Process an option contracts DataFrame around current_price, returning structured rows."""
    if contracts_df is None or contracts_df.empty:
        return None

    contracts = contracts_df.dropna(subset=['strike']).sort_values('strike').reset_index(drop=True)
    if contracts.empty:
        return None

    contracts['diff'] = (contracts['strike'] - current_price).abs()
    closest_idx = contracts['diff'].idxmin()

    start = max(0, closest_idx - NUM_STRIKES_BELOW)
    end = min(len(contracts) - 1, closest_idx + NUM_STRIKES_ABOVE)
    window = contracts.iloc[start:end + 1]

    rows = []
    for orig_idx, row in window.iterrows():
        offset = orig_idx - closest_idx
        bid = float(row['bid']) if pd.notna(row['bid']) and row['bid'] > 0 else 0.0
        ask = float(row['ask']) if pd.notna(row['ask']) and row['ask'] > 0 else 0.0
        last = float(row['lastPrice']) if pd.notna(row['lastPrice']) else 0.0
        strike = round(float(row['strike']), 2)
        bid_pct = round(bid / current_price * 100, 3) if current_price > 0 else 0.0
        vol = int(row['volume']) if pd.notna(row['volume']) else 0
        oi = int(row['openInterest']) if pd.notna(row['openInterest']) else 0

        if option_type.upper() == "CALL" and current_price > 0:
            max_return_pct = round(((strike - current_price) + bid) / current_price * 100, 3)
        else:
            max_return_pct = 0.0

        rows.append({
            "offset": offset,
            "strike": strike,
            "bid": round(bid, 2),
            "bid_pct": bid_pct,
            "max_return_pct": max_return_pct,
            "ask": round(ask, 2),
            "last_price": round(last, 2),
            "volume": vol,
            "open_interest": oi,
        })

    if option_type.upper() == "PUT":
        # Order rows from +5 down to -5 (like Robinhood: +5 is most expensive PUT at the top)
        rows.sort(key=lambda r: r['offset'], reverse=True)
    else:
        # Order rows from -5 up to +5 (like Robinhood: ascending strike, most expensive ITM call at top, OTM calls below)
        rows.sort(key=lambda r: r['offset'])

    return {
        "symbol": symbol.upper(),
        "expiry": expiry_str,
        "current_price": current_price,
        "tags": tags or [],
        "earnings_date": earnings_date,
        "rows": rows,
        "option_type": option_type.upper(),
        "fetched_at": datetime.datetime.now().isoformat()
    }


def fetch_option_chain(symbol, expiry_str, current_price, tags=None, earnings_date=None, option_type="PUT"):
    """Backward-compatible helper to fetch and process option chain."""
    try:
        ticker = yf.Ticker(symbol)
        chain = ticker.option_chain(expiry_str)
        contracts_df = chain.puts if option_type.upper() == "PUT" else chain.calls
        return process_option_chain(symbol, expiry_str, current_price, contracts_df, tags, earnings_date, option_type)
    except Exception as e:
        import traceback
        print(f"  Error fetching options for {symbol}: {e}")
        traceback.print_exc()
        return None


# ---------------------------------------------------------------------------
# HTML report generation
# ---------------------------------------------------------------------------

def pct_cell_class(bid_pct, offset=None, option_type="PUT"):
    """Return CSS class for highlighting bid_pct cells."""
    if option_type.upper() == "PUT":
        if offset is not None and offset not in (-2, -3, -4, -5):
            return ""
    else:
        if offset is not None and offset not in (1, 2, 3, 4, 5):
            return ""
    if bid_pct >= 0.5:
        return "green-cell"
    return ""


def render_symbol_table(opt_data, target_friday_str=None, option_type="PUT"):
    """Render a per-symbol option table as HTML."""
    sym = opt_data['symbol']
    expiry = opt_data['expiry']
    current_price = opt_data['current_price']
    rows = opt_data['rows']
    opt_type = opt_data.get('option_type', option_type).upper()

    is_mismatched = bool(target_friday_str and expiry != target_friday_str)
    badge_html = ""
    if is_mismatched:
        try:
            today = datetime.date.today()
            exp_date = datetime.datetime.strptime(expiry, "%Y-%m-%d").date()
            dte = (exp_date - today).days
            badge_html = f' <span class="badge-monthly">⚠️ Non-Weekly / Monthly ({dte}d DTE)</span>'
        except Exception:
            badge_html = ' <span class="badge-monthly">⚠️ Non-Weekly Expiry</span>'

    type_title = "Put Options" if opt_type == "PUT" else "Covered Call Options"
    extra_th = '<th class="col-pct">Max Return %</th>' if opt_type == "CALL" else ''

    html = f"""
    <div class="stock-card" id="options-{sym}">
        <h3>{sym} — {type_title} for {expiry}{badge_html}
            <span style="font-size: 0.7em; color: #666;"> | Stock: ${current_price:.2f}</span>
            <a href='#top' style='font-size: 0.5em; vertical-align: middle;'>[Top]</a>
        </h3>
        <table>
            <thead>
                <tr>
                    <th class="col-idx">#</th>
                    <th class="col-strike">Strike</th>
                    <th class="col-bid">Bid</th>
                    <th class="col-pct">Bid / Stock %</th>
                    {extra_th}
                    <th class="col-ask">Ask</th>
                    <th class="col-last">Last Price</th>
                    <th class="col-vol">Volume</th>
                    <th class="col-oi">Open Int.</th>
                </tr>
            </thead>
            <tbody>
    """

    for row in rows:
        offset = row.get('offset', 0)
        offset_label = f"{offset:+d}" if offset != 0 else "ATM"
        row_class = ' style="background-color: #fffbe6;"' if offset == 0 else ""
        pct_cls = pct_cell_class(row['bid_pct'], offset, option_type=opt_type)
        pct_td_class = f' class="{pct_cls}"' if pct_cls else ""

        if opt_type == "CALL":
            max_ret = row.get('max_return_pct', 0.0)
            extra_td = f'<td style="font-weight: 500;">{max_ret:.2f}%</td>'
        else:
            extra_td = ''

        html += f"""
                <tr{row_class}>
                    <td style="text-align:center; font-weight:bold;">{offset_label}</td>
                    <td>${row['strike']:.2f}</td>
                    <td>${row['bid']:.2f}</td>
                    <td{pct_td_class}>{row['bid_pct']:.3f}%</td>
                    {extra_td}
                    <td>${row['ask']:.2f}</td>
                    <td>${row['last_price']:.2f}</td>
                    <td>{row['volume']:,}</td>
                    <td>{row['open_interest']:,}</td>
                </tr>
        """

    html += """
            </tbody>
        </table>
    </div>
    """
    return html


def get_summary_rows(opt_data, option_type="PUT"):
    """Extract summary rows: -2 and -3 for PUT; +1, +2, and +3 for CALL."""
    rows = opt_data['rows']
    opt_type = opt_data.get('option_type', option_type).upper()
    if opt_type == "PUT":
        result = {-2: None, -3: None}
        for row in rows:
            if row.get('offset') in (-2, -3):
                result[row.get('offset')] = row
        return result
    else:
        result = {1: None, 2: None, 3: None}
        for row in rows:
            if row.get('offset') in (1, 2, 3):
                result[row.get('offset')] = row
        return result


def format_pos_tags(tags):
    """Format position tags HTML: colored red if threshold met, otherwise normal gray badge."""
    if not tags:
        return ""
    tag_spans = []
    for t in tags:
        cls = "pos-tag pos-tag-red" if t.get("is_red") else "pos-tag"
        tag_spans.append(f'<span class="{cls}">{t["label"]}</span>')
    return "".join(tag_spans)


def render_single_summary_table(items, table_id, title, target_friday_str=None, is_secondary=False, option_type="PUT"):
    """Render a single summary table block with its own sorting and Recommend button."""
    if not items:
        return ""

    card_id = "top" if not is_secondary else "top-monthly"
    badge_note = ""
    if is_secondary:
        badge_note = '<span class="legend-item"><span class="badge-monthly" style="font-size: 0.85em;">Monthly / Later</span> <strong>Non-weekly contract:</strong> Longer DTE, premiums not directly comparable to weekly</span>'

    opt_type = items[0].get('option_type', option_type).upper() if items else option_type.upper()

    if opt_type == "CALL":
        legend_html = f"""
        <div class="color-legend">
            <strong>🎨 Color Legend:</strong>
            <span class="legend-item"><span class="legend-box" style="background-color: #ccffcc; border: 1px solid #a3e6a3;"></span> <strong>Green cell:</strong> Bid/Stock% &ge; 0.5% (attractive premium yield)</span>
            <span class="legend-item"><span class="legend-box" style="background-color: #fff3cd; border: 1px solid #ffeeba;"></span> <strong>Yellow row:</strong> Stock price under $40 (affordable 100 shares)</span>
            <span class="legend-item"><span class="legend-box" style="background-color: #ffebee; border: 1px solid #ffcdd2;"></span> <strong>Red tag:</strong> Near multi-period low (1y/6m &lt;10%, 3m/1m &lt;20%, 7d &lt;30%)</span>
            <span class="legend-item">📈 <strong>Max Ret%:</strong> Return if assigned: ((Strike - Stock Price) + Bid) / Stock Price</span>
            {badge_note}
        </div>
        <p style="font-size: 0.85em; color: #666; margin-top: -2px; margin-bottom: 12px;">
            💡 <em>Click headers to sort: <strong>Symbol</strong>, <strong>Position Tags (Red Tag Count)</strong>, <strong>Stock Price</strong>, <strong>Bid/Stk%</strong>, or <strong>Max Ret%</strong>. Or click <strong>⭐ Recommend</strong> for top picks.</em>
        </p>
        """
        table_headers = f"""
                <tr>
                    <th rowspan="2" class="col-sym sortable" onclick="sortSummaryTable('{table_id}', 0, 'text')" title="Sort by Symbol">Symbol <span class="sort-arrow"></span></th>
                    <th rowspan="2" class="col-target sortable" onclick="sortSummaryTable('{table_id}', 1, 'num')" title="Sort by Red Tag Count (Ties broken by Symbol)">Position Tags <span class="sort-arrow"></span></th>
                    <th rowspan="2" class="col-price sortable" onclick="sortSummaryTable('{table_id}', 2, 'num')" title="Sort by Stock Price">Stock Price <span class="sort-arrow"></span></th>
                    <th rowspan="2" class="col-earnings sortable" onclick="sortSummaryTable('{table_id}', 3, 'text')" title="Sort by Earnings Date">Earnings Date <span class="sort-arrow"></span></th>
                    <th rowspan="2" class="col-exp sortable" onclick="sortSummaryTable('{table_id}', 4, 'text')" title="Sort by Expiry">Expiry <span class="sort-arrow"></span></th>
                    <th colspan="5" class="period-hdr" style="text-align:center;">Strike +1</th>
                    <th colspan="5" class="period-hdr" style="text-align:center;">Strike +2</th>
                    <th colspan="5" class="period-hdr" style="text-align:center;">Strike +3</th>
                </tr>
                <tr>
                    <th class="period-sep col-stat">Strike</th>
                    <th class="col-stat">Bid</th>
                    <th class="col-stat sortable" onclick="sortSummaryTable('{table_id}', 7, 'num')" title="Sort by Strike +1 Bid/Stk%">Bid/Stk% <span class="sort-arrow"></span></th>
                    <th class="col-stat sortable" onclick="sortSummaryTable('{table_id}', 8, 'num')" title="Sort by Strike +1 Max Return%">Max Ret% <span class="sort-arrow"></span></th>
                    <th class="col-stat">Last</th>

                    <th class="period-sep col-stat">Strike</th>
                    <th class="col-stat">Bid</th>
                    <th class="col-stat sortable" onclick="sortSummaryTable('{table_id}', 12, 'num')" title="Sort by Strike +2 Bid/Stk%">Bid/Stk% <span class="sort-arrow"></span></th>
                    <th class="col-stat sortable" onclick="sortSummaryTable('{table_id}', 13, 'num')" title="Sort by Strike +2 Max Return%">Max Ret% <span class="sort-arrow"></span></th>
                    <th class="col-stat">Last</th>

                    <th class="period-sep col-stat">Strike</th>
                    <th class="col-stat">Bid</th>
                    <th class="col-stat sortable" onclick="sortSummaryTable('{table_id}', 17, 'num')" title="Sort by Strike +3 Bid/Stk%">Bid/Stk% <span class="sort-arrow"></span></th>
                    <th class="col-stat sortable" onclick="sortSummaryTable('{table_id}', 18, 'num')" title="Sort by Strike +3 Max Return%">Max Ret% <span class="sort-arrow"></span></th>
                    <th class="col-stat">Last</th>
                </tr>
        """
        target_offsets = [1, 2, 3]
    else:
        legend_html = f"""
        <div class="color-legend">
            <strong>🎨 Color Legend:</strong>
            <span class="legend-item"><span class="legend-box" style="background-color: #ccffcc; border: 1px solid #a3e6a3;"></span> <strong>Green cell:</strong> Bid/Stock% &ge; 0.5% (attractive premium)</span>
            <span class="legend-item"><span class="legend-box" style="background-color: #fff3cd; border: 1px solid #ffeeba;"></span> <strong>Yellow row:</strong> Stock price under $40</span>
            <span class="legend-item"><span class="legend-box" style="background-color: #ffebee; border: 1px solid #ffcdd2;"></span> <strong>Red tag:</strong> Near multi-period low (1y/6m &lt;10%, 3m/1m &lt;20%, 7d &lt;30%)</span>
            {badge_note}
        </div>
        <p style="font-size: 0.85em; color: #666; margin-top: -2px; margin-bottom: 12px;">
            💡 <em>Click headers to sort: <strong>Symbol</strong>, <strong>Position Tags (Red Tag Count)</strong>, <strong>Stock Price</strong>, <strong>Strike -2 Bid/Stk%</strong>, <strong>Strike -3 Bid/Stk%</strong>. Or click <strong>⭐ Recommend</strong> for top picks.</em>
        </p>
        """
        table_headers = f"""
                <tr>
                    <th rowspan="2" class="col-sym sortable" onclick="sortSummaryTable('{table_id}', 0, 'text')" title="Sort by Symbol">Symbol <span class="sort-arrow"></span></th>
                    <th rowspan="2" class="col-target sortable" onclick="sortSummaryTable('{table_id}', 1, 'num')" title="Sort by Red Tag Count (Ties broken by Symbol)">Position Tags <span class="sort-arrow"></span></th>
                    <th rowspan="2" class="col-price sortable" onclick="sortSummaryTable('{table_id}', 2, 'num')" title="Sort by Stock Price">Stock Price <span class="sort-arrow"></span></th>
                    <th rowspan="2" class="col-earnings sortable" onclick="sortSummaryTable('{table_id}', 3, 'text')" title="Sort by Earnings Date">Earnings Date <span class="sort-arrow"></span></th>
                    <th rowspan="2" class="col-exp sortable" onclick="sortSummaryTable('{table_id}', 4, 'text')" title="Sort by Expiry">Expiry <span class="sort-arrow"></span></th>
                    <th colspan="4" class="period-hdr" style="text-align:center;">Strike -2</th>
                    <th colspan="4" class="period-hdr" style="text-align:center;">Strike -3</th>
                </tr>
                <tr>
                    <th class="period-sep col-stat">Strike</th>
                    <th class="col-stat">Bid</th>
                    <th class="col-stat sortable" onclick="sortSummaryTable('{table_id}', 7, 'num')" title="Sort by Strike -2 Bid/Stk%">Bid/Stk% <span class="sort-arrow"></span></th>
                    <th class="col-stat">Last</th>
                    <th class="period-sep col-stat">Strike</th>
                    <th class="col-stat">Bid</th>
                    <th class="col-stat sortable" onclick="sortSummaryTable('{table_id}', 11, 'num')" title="Sort by Strike -3 Bid/Stk%">Bid/Stk% <span class="sort-arrow"></span></th>
                    <th class="col-stat">Last</th>
                </tr>
        """
        target_offsets = [-2, -3]

    html = f"""
    <div class="stock-card" id="{card_id}">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
            <h2 style="margin: 0;">{title} ({len(items)} symbols)</h2>
            <button class="btn-recommend" onclick="sortRecommended('{table_id}')" title="Sort: 1) Yellow row (<$40), 2) Avg green cell Bid/Stk%, 3) Red tag count, 4) Symbol">
                ⭐ Recommend
            </button>
        </div>
        {legend_html}
        <table id="{table_id}">
            <thead>
                {table_headers}
            </thead>
            <tbody>
    """

    sorted_data = sorted(items, key=lambda d: d['symbol'])
    today = datetime.date.today()

    for opt_data in sorted_data:
        sym = opt_data['symbol']
        current_price = opt_data['current_price']
        expiry = opt_data['expiry']
        tags = opt_data.get('tags', [])
        summary = get_summary_rows(opt_data, option_type=opt_type)

        # Expiry formatting with badge if not matching target Friday
        is_mismatched = bool(target_friday_str and expiry != target_friday_str)
        if is_mismatched:
            try:
                exp_date = datetime.datetime.strptime(expiry, "%Y-%m-%d").date()
                dte = (exp_date - today).days
                expiry_display = f'{expiry}<br><span class="badge-monthly">{dte}d DTE</span>'
            except Exception:
                expiry_display = f'{expiry}<br><span class="badge-monthly">Monthly</span>'
        else:
            expiry_display = expiry

        sym_link = f'<a href="#options-{sym}" style="text-decoration:none; color:#2c3e50; font-weight:bold;">{sym}</a>'
        tags_html = format_pos_tags(tags)
        red_count = sum(1 for t in tags if t.get('is_red'))
        is_yellow = 1 if current_price < 40.0 else 0
        row_cls = ' class="price-low"' if is_yellow else ""

        cells = ""
        green_values = []
        for offset in target_offsets:
            row = summary.get(offset)
            sep = ' class="period-sep"'
            if row:
                pct_cls = pct_cell_class(row['bid_pct'], offset, option_type=opt_type)
                if pct_cls == "green-cell":
                    green_values.append(row['bid_pct'])
                pct_td_class = f' class="{pct_cls}"' if pct_cls else ""

                if opt_type == "CALL":
                    max_ret = row.get('max_return_pct', 0.0)
                    cells += f"""
                        <td{sep}>${row['strike']:.2f}</td>
                        <td>${row['bid']:.2f}</td>
                        <td{pct_td_class} data-val="{row['bid_pct']}">{row['bid_pct']:.3f}%</td>
                        <td style="font-weight: 500;" data-val="{max_ret}">{max_ret:.2f}%</td>
                        <td>${row['last_price']:.2f}</td>
                    """
                else:
                    cells += f"""
                        <td{sep}>${row['strike']:.2f}</td>
                        <td>${row['bid']:.2f}</td>
                        <td{pct_td_class} data-val="{row['bid_pct']}">{row['bid_pct']:.3f}%</td>
                        <td>${row['last_price']:.2f}</td>
                    """
            else:
                if opt_type == "CALL":
                    cells += f"""
                        <td{sep}>—</td><td>—</td><td data-val="-999">—</td><td data-val="-999">—</td><td>—</td>
                    """
                else:
                    cells += f"""
                        <td{sep}>—</td><td>—</td><td data-val="-999">—</td><td>—</td>
                    """

        green_avg = sum(green_values) / len(green_values) if green_values else 0.0

        # Earnings Date formatting
        ed = opt_data.get('earnings_date')
        if ed:
            ed_str = ed.strftime("%Y-%m-%d") if hasattr(ed, 'strftime') else str(ed)[:10]
            is_upcoming_before_expiry = False
            is_past = False
            try:
                exp_d = datetime.datetime.strptime(expiry, "%Y-%m-%d").date()
                if isinstance(ed, datetime.date):
                    if ed < today:
                        is_past = True
                    elif today <= ed <= exp_d:
                        is_upcoming_before_expiry = True
            except Exception:
                pass

            if is_upcoming_before_expiry:
                earnings_display = f'<span class="badge-earnings-alert" title="Upcoming earnings date on or before option expiry!">⚠️ {ed_str}</span>'
            elif is_past:
                earnings_display = f'<span class="badge-earnings" style="opacity: 0.6;" title="Past earnings call ({ed_str})">{ed_str}</span>'
            else:
                earnings_display = f'<span class="badge-earnings">{ed_str}</span>'
            ed_sort_val = ed_str
        else:
            earnings_display = '<span style="color:#a0aec0;">—</span>'
            ed_sort_val = "9999-99-99"

        html += f"""
                <tr{row_cls} data-yellow="{is_yellow}" data-red="{red_count}" data-green-avg="{green_avg:.4f}" data-sym="{sym}">
                    <td style="text-align:left;">{sym_link}</td>
                    <td style="text-align:center;" data-val="{red_count}">{tags_html}</td>
                    <td>${current_price:.2f}</td>
                    <td style="text-align:center;" data-val="{ed_sort_val}">{earnings_display}</td>
                    <td style="text-align:center;" data-val="{expiry}">{expiry_display}</td>
                    {cells}
                </tr>
        """

    html += """
            </tbody>
        </table>
    </div>
    """
    return html


def render_summary_table(all_opt_data, target_friday=None, option_type="PUT"):
    """Split option data into weekly (target Friday) and non-weekly/monthly tables."""
    target_friday_str = target_friday.isoformat() if target_friday else None

    weekly_data = []
    other_data = []

    for opt_data in all_opt_data:
        if target_friday_str and opt_data.get('expiry') == target_friday_str:
            weekly_data.append(opt_data)
        elif not target_friday_str:
            weekly_data.append(opt_data)
        else:
            other_data.append(opt_data)

    target_label = target_friday.strftime('%Y-%m-%d (%A)') if target_friday else "Upcoming Friday"
    type_label = "Put Options" if option_type.upper() == "PUT" else "Covered Calls"
    weekly_title = f"📋 Upcoming Friday {type_label} Expiry Summary — {target_label}"
    weekly_html = render_single_summary_table(
        weekly_data,
        table_id="summary-table-weekly",
        title=weekly_title,
        target_friday_str=target_friday_str,
        is_secondary=False,
        option_type=option_type
    )

    other_html = ""
    if other_data:
        other_title = f"📆 Non-Weekly / Monthly {type_label} Expiries Summary (Next Available Expiry)"
        other_html = render_single_summary_table(
            other_data,
            table_id="summary-table-monthly",
            title=other_title,
            target_friday_str=target_friday_str,
            is_secondary=True,
            option_type=option_type
        )

    return weekly_html + other_html


def generate_html_report(all_opt_data, target_friday=None, output_path=None, option_type="PUT"):
    """Generate the complete HTML report."""
    now = datetime.datetime.now()
    if output_path is None:
        target_str = target_friday.strftime("%Y%m%d") if target_friday else "all"
        gen_date_str = now.strftime("%Y%m%d")
        gen_time_str = now.strftime("%H%M")
        folder_name = f"{target_str}_{option_type.upper()}"
        target_dir = OUTPUT_DIR / folder_name
        target_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{option_type.lower()}_{gen_date_str}_{gen_time_str}.html"
        output_path = target_dir / filename
    else:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

    target_friday_str = target_friday.isoformat() if target_friday else None
    opt_type = option_type.upper()
    summary_html = render_summary_table(all_opt_data, target_friday=target_friday, option_type=opt_type)

    tables_html = ""
    for opt_data in sorted(all_opt_data, key=lambda d: d['symbol']):
        tables_html += render_symbol_table(opt_data, target_friday_str=target_friday_str, option_type=opt_type)

    type_title = "Put Options" if opt_type == "PUT" else "Covered Calls"
    type_emoji = "📉" if opt_type == "PUT" else "📈"
    expiry_label = f"Target Friday: {target_friday.strftime('%Y-%m-%d (%A)')}" if target_friday else "Upcoming Friday Expiry"

    full_html = f"""<!DOCTYPE html>
<html>
<head>
    <title>{type_title} Analysis Report — {expiry_label}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            line-height: 1.6; color: #333; max-width: 1550px; margin: 0 auto; padding: 10px;
            background-color: #f4f7f6;
        }}
        h1, h2, h3 {{ color: #2c3e50; }}
        .stock-card {{
            background: white; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            margin-bottom: 25px; padding: 15px; overflow-x: auto;
        }}
        table {{
            width: 100%; border-collapse: separate; border-spacing: 0; margin-bottom: 15px;
            background: white; border-radius: 8px; font-size: 0.85em;
        }}
        th, td {{
            padding: 6px 8px; text-align: right; border-bottom: 1px solid #e2e8f0;
            border-right: 1px solid #e2e8f0;
        }}
        thead th {{
            background-color: #34495e; color: white; text-align: center; padding: 8px 6px;
        }}
        tbody td:first-child {{ text-align: center; }}
        .col-sym {{ width: 70px; }}
        .col-target {{ width: 230px; text-align: center; white-space: nowrap; }}
        .col-price {{ width: 85px; }}
        .col-earnings {{ width: 105px; text-align: center; }}
        .col-exp {{ width: 105px; text-align: center; }}
        .col-idx {{ width: 50px; }}
        .col-strike {{ width: 85px; }}
        .col-pct {{ width: 95px; }}
        .col-bid {{ width: 75px; }}
        .col-ask {{ width: 70px; }}
        .col-last {{ width: 85px; }}
        .col-vol {{ width: 75px; }}
        .col-oi {{ width: 80px; }}
        .col-stat {{ width: 70px; font-size: 0.95em; }}
        .color-legend {{
            background-color: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 6px;
            padding: 8px 12px;
            font-size: 0.85em;
            color: #4a5568;
            margin-bottom: 10px;
            display: flex;
            align-items: center;
            gap: 16px;
            flex-wrap: wrap;
        }}
        .legend-item {{ display: inline-flex; align-items: center; gap: 5px; }}
        .legend-box {{
            display: inline-block;
            width: 14px;
            height: 14px;
            border-radius: 3px;
            vertical-align: middle;
        }}
        .green-cell {{ background-color: #ccffcc !important; color: #006600; font-weight: bold; }}
        .red-cell {{ background-color: #ffcccc !important; color: #cc0000; font-weight: bold; }}
        .period-sep {{ border-left: 2.5px solid #2c3e50 !important; }}
        .period-hdr {{ border-left: 2.5px solid #1a252f !important; }}
        .pos-tag {{
            display: inline-block;
            font-size: 0.80em;
            padding: 1px 4px;
            margin: 1px 2px;
            border-radius: 3px;
            background-color: #edf2f7;
            color: #4a5568;
            font-weight: 500;
        }}
        .pos-tag-red {{
            background-color: #ffebee !important;
            color: #c62828 !important;
            font-weight: bold !important;
            border: 1px solid #ffcdd2;
        }}
        .badge-monthly {{
            display: inline-block;
            background-color: #fff3cd;
            color: #b78103;
            border: 1px solid #ffeeba;
            border-radius: 4px;
            padding: 1px 5px;
            font-size: 0.80em;
            font-weight: bold;
            margin-top: 2px;
        }}
        .badge-earnings {{
            display: inline-block;
            background-color: #e2e8f0;
            color: #334155;
            border: 1px solid #cbd5e1;
            border-radius: 4px;
            padding: 1px 5px;
            font-size: 0.85em;
            font-weight: 600;
            white-space: nowrap;
        }}
        .badge-earnings-alert {{
            display: inline-block;
            background-color: #fef3c7;
            color: #92400e;
            border: 1px solid #fde68a;
            border-radius: 4px;
            padding: 1px 5px;
            font-size: 0.85em;
            font-weight: bold;
            white-space: nowrap;
        }}
        .price-low {{ background-color: #fff3cd !important; color: #856404; }}
        .btn-recommend {{
            background: linear-gradient(135deg, #f1c40f, #f39c12);
            color: #2c3e50;
            border: 1px solid #d68910;
            padding: 6px 14px;
            font-size: 0.9em;
            font-weight: bold;
            border-radius: 6px;
            cursor: pointer;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            transition: all 0.2s ease;
        }}
        .btn-recommend:hover {{
            background: linear-gradient(135deg, #f39c12, #e67e22);
            color: white;
            box-shadow: 0 3px 6px rgba(0,0,0,0.15);
            transform: translateY(-1px);
        }}
        .btn-recommend:active {{
            transform: translateY(0);
        }}
        .sortable {{ cursor: pointer; user-select: none; transition: background-color 0.15s; }}
        .sortable:hover {{ background-color: #2c3e50; text-decoration: underline; }}
        .sort-arrow {{ font-size: 0.8em; margin-left: 3px; color: #f1c40f; }}
        a {{ color: #3498db; }}
    </style>
</head>
<body>
    <h1>{type_emoji} {type_title} Analysis Report ({expiry_label})</h1>
    <p>Generated on: {now.strftime("%Y-%m-%d %H:%M")} | Target Option Expiry: <strong>{expiry_label}</strong></p>
    {summary_html}
    <h2>Per-Symbol {type_title} Chains</h2>
    {tables_html}

    <script>
    let sortDirectionsByTable = {{}};

    function sortRecommended(tableId) {{
        const table = document.getElementById(tableId);
        if (!table) return;
        const tbody = table.querySelector("tbody");
        const rows = Array.from(tbody.querySelectorAll("tr"));

        rows.sort((a, b) => {{
            // 1. Yellow row first (<$40) -> 1 before 0
            const yA = parseInt(a.getAttribute('data-yellow') || '0', 10);
            const yB = parseInt(b.getAttribute('data-yellow') || '0', 10);
            if (yA !== yB) return yB - yA;

            // 2. Average of values in green cells -> descending (highest avg first, 0 if none)
            const gA = parseFloat(a.getAttribute('data-green-avg') || '0');
            const gB = parseFloat(b.getAttribute('data-green-avg') || '0');
            if (Math.abs(gA - gB) > 0.00001) return gB - gA;

            // 3. Red tag count -> descending (highest count first)
            const rA = parseInt(a.getAttribute('data-red') || '0', 10);
            const rB = parseInt(b.getAttribute('data-red') || '0', 10);
            if (rA !== rB) return rB - rA;

            // 4. Symbol name -> ascending (A-Z)
            const symA = (a.getAttribute('data-sym') || a.children[0].innerText).trim();
            const symB = (b.getAttribute('data-sym') || b.children[0].innerText).trim();
            return symA.localeCompare(symB);
        }});

        rows.forEach(r => tbody.appendChild(r));

        table.querySelectorAll('.sort-arrow').forEach(el => el.innerText = '');
        if (sortDirectionsByTable[tableId]) {{
            sortDirectionsByTable[tableId] = {{}};
        }}
    }}

    function sortSummaryTable(tableId, colIndex, type) {{
        const table = document.getElementById(tableId);
        if (!table) return;
        const tbody = table.querySelector("tbody");
        const rows = Array.from(tbody.querySelectorAll("tr"));
        
        if (!sortDirectionsByTable[tableId]) {{
            sortDirectionsByTable[tableId] = {{}};
        }}
        const tableSort = sortDirectionsByTable[tableId];

        const defaultDir = (colIndex === 1 || type === 'num') ? 'asc' : 'desc';
        const currentDir = tableSort[colIndex] || defaultDir;
        const newDir = currentDir === 'asc' ? 'desc' : 'asc';
        sortDirectionsByTable[tableId] = {{}};
        sortDirectionsByTable[tableId][colIndex] = newDir;

        rows.sort((a, b) => {{
            let cellA = a.children[colIndex];
            let cellB = b.children[colIndex];
            let valA = cellA ? (cellA.getAttribute('data-val') !== null ? cellA.getAttribute('data-val') : cellA.innerText.trim()) : '';
            let valB = cellB ? (cellB.getAttribute('data-val') !== null ? cellB.getAttribute('data-val') : cellB.innerText.trim()) : '';
            
            let diff = 0;
            if (type === 'num') {{
                let numA = parseFloat(valA.replace(/[^0-9.-]/g, ''));
                let numB = parseFloat(valB.replace(/[^0-9.-]/g, ''));
                if (isNaN(numA)) numA = -Infinity;
                if (isNaN(numB)) numB = -Infinity;
                diff = newDir === 'asc' ? numA - numB : numB - numA;
            }} else {{
                diff = newDir === 'asc' ? valA.localeCompare(valB) : valB.localeCompare(valA);
            }}

            if (diff === 0 && colIndex !== 0) {{
                let symA = a.children[0] ? a.children[0].innerText.trim() : '';
                let symB = b.children[0] ? b.children[0].innerText.trim() : '';
                return symA.localeCompare(symB);
            }}
            return diff;
        }});

        rows.forEach(r => tbody.appendChild(r));

        table.querySelectorAll('.sort-arrow').forEach(el => el.innerText = '');
        const sortableHeaders = table.querySelectorAll('.sortable');
        sortableHeaders.forEach(th => {{
            if (th.getAttribute('onclick') && th.getAttribute('onclick').includes(colIndex + ',')) {{
                const arrow = th.querySelector('.sort-arrow');
                if (arrow) arrow.innerText = newDir === 'asc' ? ' ▲' : ' ▼';
            }}
        }});
    }}
    </script>
</body>
</html>"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(full_html)
    print(f"Report generated: {os.path.abspath(output_path)}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    opt_type_arg, day_mode, symbols = parse_cli_args()
    if not symbols:
        print("No symbols found. Pass symbols as arguments or add them to references/*.md")
        sys.exit(1)

    types_to_run = ["PUT", "CALL"] if opt_type_arg == "both" else [opt_type_arg.upper()]

    # Collect target fridays for each type
    fridays_by_type = {}
    for ot in types_to_run:
        fridays_by_type[ot] = get_target_fridays_for_type(ot, day_mode)

    print(f"Option Type(s): {', '.join(types_to_run)} | Day Mode: '{day_mode}'")
    for ot in types_to_run:
        print(f"  {ot}: {len(fridays_by_type[ot])} target Friday(s) -> {', '.join(str(f) for f in fridays_by_type[ot])}")
    print(f"Analyzing {len(symbols)} symbols...\n")

    # Options data structure: options_data[type][target_friday] = [list of opt_data]
    options_data = {ot: {tf: [] for tf in fridays_by_type[ot]} for ot in types_to_run}

    BATCH_SIZE = 50
    BATCH_DELAY = 2  # seconds

    for i, sym in enumerate(symbols):
        if i != 0 and i % BATCH_SIZE == 0:
            batch_num = i // BATCH_SIZE
            print(f"Batch {batch_num} completed, sleeping {BATCH_DELAY}s...")
            time.sleep(BATCH_DELAY)

        print(f"  [{i+1}/{len(symbols)}] {sym}...", end=" ")

        # 1. Get current stock price, range-position tags, and next earnings date once per symbol
        price, tags, earnings_date = fetch_stock_price_and_tags(sym)
        if price is None:
            print("SKIP (no price)")
            continue

        try:
            ticker = yf.Ticker(sym)
            available_expiries = ticker.options
        except Exception as e:
            print(f"SKIP (cannot fetch options: {e})")
            continue

        if not available_expiries:
            print("SKIP (no options available)")
            continue

        # Map: best_expiry -> dict mapping option_type to list of target_fridays requesting it
        expiry_map = {}
        for ot in types_to_run:
            for tf in fridays_by_type[ot]:
                best_exp = find_best_expiry(available_expiries, tf)
                if best_exp:
                    if best_exp not in expiry_map:
                        expiry_map[best_exp] = {t: [] for t in types_to_run}
                    expiry_map[best_exp][ot].append(tf)

        if not expiry_map:
            print("SKIP (no matching expiries)")
            continue

        expiries_logged = []
        for best_exp, reqs in expiry_map.items():
            chain = None
            try:
                chain = ticker.option_chain(best_exp)
            except Exception:
                continue

            if chain is None:
                continue

            if "PUT" in types_to_run and reqs.get("PUT") and hasattr(chain, 'puts') and chain.puts is not None and not chain.puts.empty:
                put_data = process_option_chain(sym, best_exp, price, chain.puts, tags=tags, earnings_date=earnings_date, option_type="PUT")
                if put_data:
                    for tf in reqs["PUT"]:
                        options_data["PUT"][tf].append(put_data)
                    expiries_logged.append(f"PUT:{best_exp}")

            if "CALL" in types_to_run and reqs.get("CALL") and hasattr(chain, 'calls') and chain.calls is not None and not chain.calls.empty:
                call_data = process_option_chain(sym, best_exp, price, chain.calls, tags=tags, earnings_date=earnings_date, option_type="CALL")
                if call_data:
                    for tf in reqs["CALL"]:
                        options_data["CALL"][tf].append(call_data)
                    expiries_logged.append(f"CALL:{best_exp}")

        if expiries_logged:
            print(f"OK ({', '.join(expiries_logged)})")
        else:
            print("SKIP (no chain data)")

    print("\n" + "=" * 60)
    for ot in types_to_run:
        for tf in fridays_by_type[ot]:
            data = options_data[ot][tf]
            print(f"{ot} - Target Friday {tf}: Collected data for {len(data)} symbols.")
            if data:
                generate_html_report(data, target_friday=tf, option_type=ot)
            else:
                print(f"No {ot} data collected for target Friday {tf}; report skipped.")
    print("=" * 60)


if __name__ == "__main__":
    main()
