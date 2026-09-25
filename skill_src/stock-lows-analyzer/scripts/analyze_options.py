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
# Symbol loading
# ---------------------------------------------------------------------------

def load_symbols():
    """Load symbols from reference files (or optional CLI arguments)."""
    if len(sys.argv) >= 2:
        return sys.argv[1:]
    ref_dir = Path(__file__).parent.parent / "references"
    symbols = []
    for fname in ["tech_stocks.md", "nontech_stocks.md", "manual_stocks.md"]:
        p = ref_dir / fname
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                symbols.extend(re.findall(r'- ([A-Z]+)', f.read()))
    return list(dict.fromkeys(symbols))  # deduplicate, preserve order


# ---------------------------------------------------------------------------
# Stock price helper (live fetch)
# ---------------------------------------------------------------------------

def get_current_price(symbol):
    """Fetch current stock price live via yfinance."""
    import math
    try:
        ticker = yf.Ticker(symbol)
        price = ticker.fast_info.get('lastPrice')
        if price is not None and not (isinstance(price, float) and math.isnan(price)):
            return round(float(price), 2)
    except Exception as e:
        print(f"  Warning: could not get price for {symbol}: {e}")
    return None


# ---------------------------------------------------------------------------
# Upcoming Friday calculation
# ---------------------------------------------------------------------------

def get_upcoming_friday():
    """Return the upcoming Friday as a datetime.date. If today is Friday, return today."""
    today = datetime.date.today()
    days_until = (4 - today.weekday()) % 7
    if days_until == 0 and today.weekday() != 4:
        days_until = 7  # shouldn't happen, but safety
    return today + datetime.timedelta(days=days_until)


def find_best_expiry(symbol, target_friday):
    """Find the available expiry date closest to target_friday."""
    try:
        ticker = yf.Ticker(symbol)
        expiries = ticker.options
        if not expiries:
            return None
        target_str = target_friday.isoformat()
        # Prefer exact match, else closest
        if target_str in expiries:
            return target_str
        return min(expiries, key=lambda x: abs(
            datetime.datetime.strptime(x, "%Y-%m-%d").date() - target_friday
        ))
    except Exception as e:
        print(f"  Warning: could not get expiry dates for {symbol}: {e}")
        return None


# ---------------------------------------------------------------------------
# Fetch option chain
# ---------------------------------------------------------------------------

def fetch_option_chain(symbol, expiry_str, current_price):
    """Fetch put options chain around current_price, returning structured rows ordered +5 to -5."""
    try:
        ticker = yf.Ticker(symbol)
        chain = ticker.option_chain(expiry_str)
        puts = chain.puts

        if puts.empty:
            return None

        # Sort by strike, drop any rows with NaN strike
        puts = puts.dropna(subset=['strike']).sort_values('strike').reset_index(drop=True)

        if puts.empty:
            return None

        # Find closest strike to current_price (ATM)
        puts['diff'] = (puts['strike'] - current_price).abs()
        closest_idx = puts['diff'].idxmin()

        # Select window: NUM_STRIKES_BELOW below, NUM_STRIKES_ABOVE above
        start = max(0, closest_idx - NUM_STRIKES_BELOW)
        end = min(len(puts) - 1, closest_idx + NUM_STRIKES_ABOVE)
        window = puts.iloc[start:end + 1]

        rows = []
        for orig_idx, row in window.iterrows():
            offset = orig_idx - closest_idx  # negative = below ATM, 0 = ATM, positive = above ATM
            bid = float(row['bid']) if pd.notna(row['bid']) and row['bid'] > 0 else 0.0
            ask = float(row['ask']) if pd.notna(row['ask']) and row['ask'] > 0 else 0.0
            last = float(row['lastPrice']) if pd.notna(row['lastPrice']) else 0.0
            avg_price = round((bid + ask) / 2, 2) if (bid + ask) > 0 else round(last, 2)
            strike = round(float(row['strike']), 2)
            avg_pct = round(avg_price / current_price * 100, 3) if current_price > 0 else 0.0
            vol = int(row['volume']) if pd.notna(row['volume']) else 0
            oi = int(row['openInterest']) if pd.notna(row['openInterest']) else 0
            rows.append({
                "offset": offset,
                "strike": strike,
                "avg_price": avg_price,
                "avg_pct": avg_pct,
                "bid": round(bid, 2),
                "ask": round(ask, 2),
                "last_price": round(last, 2),
                "volume": vol,
                "open_interest": oi,
            })

        # Order rows from +5 down to -5 (like Robinhood: +5 is most expensive PUT at the top)
        rows.sort(key=lambda r: r['offset'], reverse=True)

        return {
            "symbol": symbol.upper(),
            "expiry": expiry_str,
            "current_price": current_price,
            "rows": rows,
            "fetched_at": datetime.datetime.now().isoformat()
        }

    except Exception as e:
        import traceback
        print(f"  Error fetching options for {symbol}: {e}")
        traceback.print_exc()
        return None


# ---------------------------------------------------------------------------
# HTML report generation
# ---------------------------------------------------------------------------

def pct_cell_class(avg_pct, offset=None):
    """Return CSS class for highlighting avg_pct cells (only for offsets -2 to -5)."""
    if offset is not None and offset not in (-2, -3, -4, -5):
        return ""
    if avg_pct >= 0.5:
        return "green-cell"
    return ""


def render_symbol_table(opt_data):
    """Render a per-symbol option table as HTML."""
    sym = opt_data['symbol']
    expiry = opt_data['expiry']
    current_price = opt_data['current_price']
    rows = opt_data['rows']

    html = f"""
    <div class="stock-card" id="options-{sym}">
        <h3>{sym} — Put Options for {expiry}
            <span style="font-size: 0.7em; color: #666;"> | Stock: ${current_price:.2f}</span>
            <a href='#top' style='font-size: 0.5em; vertical-align: middle;'>[Top]</a>
        </h3>
        <table>
            <thead>
                <tr>
                    <th class="col-idx">#</th>
                    <th class="col-strike">Strike</th>
                    <th class="col-avg">Avg (Bid/Ask)</th>
                    <th class="col-pct">Avg / Stock %</th>
                    <th class="col-bid">Bid</th>
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
        pct_cls = pct_cell_class(row['avg_pct'], offset)
        pct_td_class = f' class="{pct_cls}"' if pct_cls else ""

        html += f"""
                <tr{row_class}>
                    <td style="text-align:center; font-weight:bold;">{offset_label}</td>
                    <td>${row['strike']:.2f}</td>
                    <td>${row['avg_price']:.2f}</td>
                    <td{pct_td_class}>{row['avg_pct']:.3f}%</td>
                    <td>${row['bid']:.2f}</td>
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


def get_summary_rows(opt_data):
    """Extract the -2 and -3 rows (2nd and 3rd strikes below ATM) for the summary table."""
    rows = opt_data['rows']
    result = {-2: None, -3: None}
    for row in rows:
        if row.get('offset') == -2:
            result[-2] = row
        elif row.get('offset') == -3:
            result[-3] = row
    return result


def get_latest_buy_targets():
    """Extract set of BUY TARGET symbols from the most recent stock_report_*.html in OUTPUT/stock_prices/."""
    stock_dir = PROJECT_ROOT / "OUTPUT" / "stock_prices"
    if not stock_dir.exists():
        return set()
    reports = sorted(stock_dir.glob("stock_report_*.html"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not reports:
        return set()
    latest_report = reports[0]
    try:
        html = latest_report.read_text(encoding="utf-8")
        m = re.search(r'buy-header.*?<table.*?>(.*?)</table>', html, re.DOTALL)
        if m:
            symbols = re.findall(r"<td class='col-sym'><a href='#chart-([A-Z]+)'", m.group(1))
            return set(symbols)
    except Exception as e:
        print(f"  Warning: could not read buy targets from {latest_report.name}: {e}")
    return set()


def render_summary_table(all_opt_data, buy_targets=None):
    """Render the summary table at the top, one row per symbol, showing -2 and -3 strike data."""
    if buy_targets is None:
        buy_targets = set()

    html = """
    <div class="stock-card" id="top">
        <h2>📋 Options Summary (Strikes -2 and -3 below ATM)</h2>
        <p style="font-size: 0.85em; color: #666; margin-top: -5px; margin-bottom: 12px;">
            💡 <em>Click headers to sort: <strong>Symbol</strong>, <strong>Signal</strong>, <strong>Stock Price</strong>, <strong>Strike -2 Avg/Stk%</strong>, <strong>Strike -3 Avg/Stk%</strong>. Stocks under $30 are highlighted in yellow.</em>
        </p>
        <table id="summary-table">
            <thead>
                <tr>
                    <th rowspan="2" class="col-sym sortable" onclick="sortSummaryTable(0, 'text')" title="Sort by Symbol">Symbol <span class="sort-arrow"></span></th>
                    <th rowspan="2" class="col-target sortable" onclick="sortSummaryTable(1, 'text')" title="Sort by Signal">Signal <span class="sort-arrow"></span></th>
                    <th rowspan="2" class="col-price sortable" onclick="sortSummaryTable(2, 'num')" title="Sort by Stock Price">Stock Price <span class="sort-arrow"></span></th>
                    <th rowspan="2" class="col-exp">Expiry</th>
                    <th colspan="4" class="period-hdr" style="text-align:center;">Strike -2</th>
                    <th colspan="4" class="period-hdr" style="text-align:center;">Strike -3</th>
                </tr>
                <tr>
                    <th class="period-sep col-stat">Strike</th>
                    <th class="col-stat">Avg</th>
                    <th class="col-stat sortable" onclick="sortSummaryTable(6, 'num')" title="Sort by Strike -2 Avg/Stk%">Avg/Stk% <span class="sort-arrow"></span></th>
                    <th class="col-stat">Last</th>
                    <th class="period-sep col-stat">Strike</th>
                    <th class="col-stat">Avg</th>
                    <th class="col-stat sortable" onclick="sortSummaryTable(10, 'num')" title="Sort by Strike -3 Avg/Stk%">Avg/Stk% <span class="sort-arrow"></span></th>
                    <th class="col-stat">Last</th>
                </tr>
            </thead>
            <tbody>
    """

    sorted_data = sorted(all_opt_data, key=lambda d: d['symbol'])

    for opt_data in sorted_data:
        sym = opt_data['symbol']
        current_price = opt_data['current_price']
        expiry = opt_data['expiry']
        summary = get_summary_rows(opt_data)

        sym_link = f'<a href="#options-{sym}" style="text-decoration:none; color:#2c3e50; font-weight:bold;">{sym}</a>'
        buy_badge = '<span class="buy-badge">BUY</span>' if sym in buy_targets else ""
        row_cls = ' class="price-low"' if current_price < 30.0 else ""

        cells = ""
        for offset in [-2, -3]:
            row = summary.get(offset)
            sep = ' class="period-sep"'
            if row:
                pct_cls = pct_cell_class(row['avg_pct'], offset)
                pct_td_class = f' class="{pct_cls}"' if pct_cls else ""
                cells += f"""
                    <td{sep}>${row['strike']:.2f}</td>
                    <td>${row['avg_price']:.2f}</td>
                    <td{pct_td_class}>{row['avg_pct']:.3f}%</td>
                    <td>${row['last_price']:.2f}</td>
                """
            else:
                cells += f"""
                    <td{sep}>—</td><td>—</td><td>—</td><td>—</td>
                """

        html += f"""
                <tr{row_cls}>
                    <td style="text-align:left;">{sym_link}</td>
                    <td style="text-align:center;">{buy_badge}</td>
                    <td>${current_price:.2f}</td>
                    <td>{expiry}</td>
                    {cells}
                </tr>
        """

    html += """
            </tbody>
        </table>
    </div>
    """
    return html


def generate_html_report(all_opt_data, output_path=None):
    """Generate the complete HTML report."""
    now = datetime.datetime.now()
    if output_path is None:
        filename = f"options_report_{now.strftime('%Y%m%d_%H%M%S')}.html"
        output_path = OUTPUT_DIR / filename
    else:
        output_path = Path(output_path)

    buy_targets = get_latest_buy_targets()
    summary_html = render_summary_table(all_opt_data, buy_targets)

    tables_html = ""
    for opt_data in sorted(all_opt_data, key=lambda d: d['symbol']):
        tables_html += render_symbol_table(opt_data)

    full_html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Put Options Analysis Report</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            line-height: 1.6; color: #333; max-width: 1400px; margin: 0 auto; padding: 10px;
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
        .col-target {{ width: 65px; text-align: center; }}
        .col-price {{ width: 85px; }}
        .col-exp {{ width: 90px; }}
        .col-idx {{ width: 50px; }}
        .col-strike {{ width: 85px; }}
        .col-avg {{ width: 90px; }}
        .col-pct {{ width: 95px; }}
        .col-bid {{ width: 70px; }}
        .col-ask {{ width: 70px; }}
        .col-last {{ width: 85px; }}
        .col-vol {{ width: 75px; }}
        .col-oi {{ width: 80px; }}
        .col-stat {{ width: 70px; font-size: 0.95em; }}
        .green-cell {{ background-color: #ccffcc !important; color: #006600; font-weight: bold; }}
        .red-cell {{ background-color: #ffcccc !important; color: #cc0000; font-weight: bold; }}
        .period-sep {{ border-left: 2.5px solid #2c3e50 !important; }}
        .period-hdr {{ border-left: 2.5px solid #1a252f !important; }}
        .buy-badge {{ background-color: #e74c3c; color: white; font-weight: bold; padding: 2px 6px; border-radius: 4px; font-size: 0.85em; display: inline-block; }}
        .price-low {{ background-color: #fff3cd !important; color: #856404; }}
        .sortable {{ cursor: pointer; user-select: none; transition: background-color 0.15s; }}
        .sortable:hover {{ background-color: #2c3e50; text-decoration: underline; }}
        .sort-arrow {{ font-size: 0.8em; margin-left: 3px; color: #f1c40f; }}
        a {{ color: #3498db; }}
    </style>
</head>
<body>
    <h1>📊 Put Options Analysis Report</h1>
    <p>Generated on: {now.strftime("%Y-%m-%d %H:%M")} | Showing put options for upcoming Friday expiry</p>
    {summary_html}
    <h2>Per-Symbol Put Option Chains</h2>
    {tables_html}

    <script>
    let sortDirections = {{}};
    function sortSummaryTable(colIndex, type) {{
        const table = document.getElementById("summary-table");
        if (!table) return;
        const tbody = table.querySelector("tbody");
        const rows = Array.from(tbody.querySelectorAll("tr"));
        
        // For numbers default to descending (highest first), for text default to ascending
        const defaultDir = (type === 'num') ? 'asc' : 'desc';
        const currentDir = sortDirections[colIndex] || defaultDir;
        const newDir = currentDir === 'asc' ? 'desc' : 'asc';
        sortDirections = {{}};
        sortDirections[colIndex] = newDir;

        rows.sort((a, b) => {{
            let valA = a.children[colIndex] ? a.children[colIndex].innerText.trim() : '';
            let valB = b.children[colIndex] ? b.children[colIndex].innerText.trim() : '';
            
            if (type === 'num') {{
                let numA = parseFloat(valA.replace(/[^0-9.-]/g, ''));
                let numB = parseFloat(valB.replace(/[^0-9.-]/g, ''));
                if (isNaN(numA)) numA = -Infinity;
                if (isNaN(numB)) numB = -Infinity;
                return newDir === 'asc' ? numA - numB : numB - numA;
            }} else {{
                return newDir === 'asc' ? valA.localeCompare(valB) : valB.localeCompare(valA);
            }}
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
    symbols = load_symbols()
    if not symbols:
        print("No symbols found. Pass symbols as arguments or add them to references/*.md")
        sys.exit(1)

    target_friday = get_upcoming_friday()
    print(f"Target expiry Friday: {target_friday}")
    print(f"Analyzing {len(symbols)} symbols...\n")

    all_opt_data = []
    BATCH_SIZE = 50
    BATCH_DELAY = 2  # seconds

    for i, sym in enumerate(symbols):
        if i != 0 and i % BATCH_SIZE == 0:
            batch_num = i // BATCH_SIZE
            print(f"Batch {batch_num} completed, sleeping {BATCH_DELAY}s...")
            time.sleep(BATCH_DELAY)

        print(f"  [{i+1}/{len(symbols)}] {sym}...", end=" ")

        # 1. Get current stock price
        price = get_current_price(sym)
        if price is None:
            print("SKIP (no price)")
            continue

        # 2. Find best expiry near target Friday
        expiry = find_best_expiry(sym, target_friday)
        if expiry is None:
            print("SKIP (no expiry)")
            continue

        # 3. Fetch option chain
        opt_data = fetch_option_chain(sym, expiry, price)
        if opt_data is None:
            print("SKIP (no chain)")
            continue

        all_opt_data.append(opt_data)
        print(f"OK ({len(opt_data['rows'])} strikes, expiry={expiry})")

    print(f"\nCollected option data for {len(all_opt_data)} symbols.")

    if all_opt_data:
        generate_html_report(all_opt_data)
    else:
        print("No option data collected; no report generated.")


if __name__ == "__main__":
    main()
