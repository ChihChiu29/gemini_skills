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

        return price, tags
    except Exception as e:
        print(f"  Warning: could not get price/history for {symbol}: {e}")
        return None, []


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

def fetch_option_chain(symbol, expiry_str, current_price, tags=None):
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
            strike = round(float(row['strike']), 2)
            bid_pct = round(bid / current_price * 100, 3) if current_price > 0 else 0.0
            vol = int(row['volume']) if pd.notna(row['volume']) else 0
            oi = int(row['openInterest']) if pd.notna(row['openInterest']) else 0
            rows.append({
                "offset": offset,
                "strike": strike,
                "bid": round(bid, 2),
                "bid_pct": bid_pct,
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
            "tags": tags or [],
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

def pct_cell_class(bid_pct, offset=None):
    """Return CSS class for highlighting bid_pct cells (only for offsets -2 to -5)."""
    if offset is not None and offset not in (-2, -3, -4, -5):
        return ""
    if bid_pct >= 0.5:
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
                    <th class="col-bid">Bid</th>
                    <th class="col-pct">Bid / Stock %</th>
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
        pct_cls = pct_cell_class(row['bid_pct'], offset)
        pct_td_class = f' class="{pct_cls}"' if pct_cls else ""

        html += f"""
                <tr{row_class}>
                    <td style="text-align:center; font-weight:bold;">{offset_label}</td>
                    <td>${row['strike']:.2f}</td>
                    <td>${row['bid']:.2f}</td>
                    <td{pct_td_class}>{row['bid_pct']:.3f}%</td>
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


def format_pos_tags(tags):
    """Format position tags HTML: colored red if threshold met, otherwise normal gray badge."""
    if not tags:
        return ""
    tag_spans = []
    for t in tags:
        cls = "pos-tag pos-tag-red" if t.get("is_red") else "pos-tag"
        tag_spans.append(f'<span class="{cls}">{t["label"]}</span>')
    return "".join(tag_spans)


def render_summary_table(all_opt_data):
    """Render the summary table at the top, one row per symbol, showing -2 and -3 strike data."""
    html = """
    <div class="stock-card" id="top">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
            <h2 style="margin: 0;">📋 Options Summary (Strikes -2 and -3 below ATM)</h2>
            <button class="btn-recommend" onclick="sortRecommended()" title="Sort: 1) Yellow row (<$30), 2) Avg green cell Bid/Stk%, 3) Red tag count, 4) Symbol">
                ⭐ Recommend
            </button>
        </div>
        <div class="color-legend">
            <strong>🎨 Color Legend:</strong>
            <span class="legend-item"><span class="legend-box" style="background-color: #ccffcc; border: 1px solid #a3e6a3;"></span> <strong>Green cell:</strong> Bid/Stock% &ge; 0.5% (attractive premium)</span>
            <span class="legend-item"><span class="legend-box" style="background-color: #fff3cd; border: 1px solid #ffeeba;"></span> <strong>Yellow row:</strong> Stock price under $30</span>
            <span class="legend-item"><span class="legend-box" style="background-color: #ffebee; border: 1px solid #ffcdd2;"></span> <strong>Red tag:</strong> Near multi-period low (1y/6m &lt;10%, 3m/1m &lt;20%, 7d &lt;30%)</span>
        </div>
        <p style="font-size: 0.85em; color: #666; margin-top: -2px; margin-bottom: 12px;">
            💡 <em>Click headers to sort: <strong>Symbol</strong>, <strong>Position Tags (Red Tag Count)</strong>, <strong>Stock Price</strong>, <strong>Strike -2 Bid/Stk%</strong>, <strong>Strike -3 Bid/Stk%</strong>. Or click <strong>⭐ Recommend</strong> for top picks.</em>
        </p>
        <table id="summary-table">
            <thead>
                <tr>
                    <th rowspan="2" class="col-sym sortable" onclick="sortSummaryTable(0, 'text')" title="Sort by Symbol">Symbol <span class="sort-arrow"></span></th>
                    <th rowspan="2" class="col-target sortable" onclick="sortSummaryTable(1, 'num')" title="Sort by Red Tag Count (Ties broken by Symbol)">Position Tags <span class="sort-arrow"></span></th>
                    <th rowspan="2" class="col-price sortable" onclick="sortSummaryTable(2, 'num')" title="Sort by Stock Price">Stock Price <span class="sort-arrow"></span></th>
                    <th rowspan="2" class="col-exp">Expiry</th>
                    <th colspan="4" class="period-hdr" style="text-align:center;">Strike -2</th>
                    <th colspan="4" class="period-hdr" style="text-align:center;">Strike -3</th>
                </tr>
                <tr>
                    <th class="period-sep col-stat">Strike</th>
                    <th class="col-stat">Bid</th>
                    <th class="col-stat sortable" onclick="sortSummaryTable(6, 'num')" title="Sort by Strike -2 Bid/Stk%">Bid/Stk% <span class="sort-arrow"></span></th>
                    <th class="col-stat">Last</th>
                    <th class="period-sep col-stat">Strike</th>
                    <th class="col-stat">Bid</th>
                    <th class="col-stat sortable" onclick="sortSummaryTable(10, 'num')" title="Sort by Strike -3 Bid/Stk%">Bid/Stk% <span class="sort-arrow"></span></th>
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
        tags = opt_data.get('tags', [])
        summary = get_summary_rows(opt_data)

        sym_link = f'<a href="#options-{sym}" style="text-decoration:none; color:#2c3e50; font-weight:bold;">{sym}</a>'
        tags_html = format_pos_tags(tags)
        # Store count of red tags
        red_count = sum(1 for t in tags if t.get('is_red'))
        is_yellow = 1 if current_price < 30.0 else 0
        row_cls = ' class="price-low"' if is_yellow else ""

        cells = ""
        green_values = []
        for offset in [-2, -3]:
            row = summary.get(offset)
            sep = ' class="period-sep"'
            if row:
                pct_cls = pct_cell_class(row['bid_pct'], offset)
                if pct_cls == "green-cell":
                    green_values.append(row['bid_pct'])
                pct_td_class = f' class="{pct_cls}"' if pct_cls else ""
                cells += f"""
                    <td{sep}>${row['strike']:.2f}</td>
                    <td>${row['bid']:.2f}</td>
                    <td{pct_td_class}>{row['bid_pct']:.3f}%</td>
                    <td>${row['last_price']:.2f}</td>
                """
            else:
                cells += f"""
                    <td{sep}>—</td><td>—</td><td>—</td><td>—</td>
                """

        # Average of green cell values (0 if none)
        green_avg = sum(green_values) / len(green_values) if green_values else 0.0

        html += f"""
                <tr{row_cls} data-yellow="{is_yellow}" data-red="{red_count}" data-green-avg="{green_avg:.4f}" data-sym="{sym}">
                    <td style="text-align:left;">{sym_link}</td>
                    <td style="text-align:center;" data-val="{red_count}">{tags_html}</td>
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


def generate_html_report(all_opt_data, target_friday=None, output_path=None):
    """Generate the complete HTML report."""
    now = datetime.datetime.now()
    if output_path is None:
        filename = f"options_report_{now.strftime('%Y%m%d_%H%M%S')}.html"
        output_path = OUTPUT_DIR / filename
    else:
        output_path = Path(output_path)

    summary_html = render_summary_table(all_opt_data)

    tables_html = ""
    for opt_data in sorted(all_opt_data, key=lambda d: d['symbol']):
        tables_html += render_symbol_table(opt_data)

    expiry_label = f"Expiry {target_friday.strftime('%Y-%m-%d (%A)')}" if target_friday else "Upcoming Friday Expiry"

    full_html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Put Options Analysis Report — {expiry_label}</title>
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
        .col-target {{ width: 230px; text-align: center; white-space: nowrap; }}
        .col-price {{ width: 85px; }}
        .col-exp {{ width: 90px; }}
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
    <h1>📊 Put Options Analysis Report ({expiry_label})</h1>
    <p>Generated on: {now.strftime("%Y-%m-%d %H:%M")} | Target Option Expiry: <strong>{expiry_label}</strong></p>
    {summary_html}
    <h2>Per-Symbol Put Option Chains</h2>
    {tables_html}

    <script>
    let sortDirections = {{}};

    function sortRecommended() {{
        const table = document.getElementById("summary-table");
        if (!table) return;
        const tbody = table.querySelector("tbody");
        const rows = Array.from(tbody.querySelectorAll("tr"));

        rows.sort((a, b) => {{
            // 1. Yellow row first (<$30) -> 1 before 0
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

        // Clear header arrows since custom multi-level sort was applied
        table.querySelectorAll('.sort-arrow').forEach(el => el.innerText = '');
        sortDirections = {{}};
    }}

    function sortSummaryTable(colIndex, type) {{
        const table = document.getElementById("summary-table");
        if (!table) return;
        const tbody = table.querySelector("tbody");
        const rows = Array.from(tbody.querySelectorAll("tr"));
        
        // For column 1 (red tag count) and numbers default to descending (highest first)
        const defaultDir = (colIndex === 1 || type === 'num') ? 'asc' : 'desc';
        const currentDir = sortDirections[colIndex] || defaultDir;
        const newDir = currentDir === 'asc' ? 'desc' : 'asc';
        sortDirections = {{}};
        sortDirections[colIndex] = newDir;

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

            // Tie-breaker using Symbol (column 0) ascending
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

        # 1. Get current stock price and range-position tags
        price, tags = fetch_stock_price_and_tags(sym)
        if price is None:
            print("SKIP (no price)")
            continue

        # 2. Find best expiry near target Friday
        expiry = find_best_expiry(sym, target_friday)
        if expiry is None:
            print("SKIP (no expiry)")
            continue

        # 3. Fetch option chain
        opt_data = fetch_option_chain(sym, expiry, price, tags=tags)
        if opt_data is None:
            print("SKIP (no chain)")
            continue

        all_opt_data.append(opt_data)
        print(f"OK ({len(opt_data['rows'])} strikes, expiry={expiry})")

    print(f"\nCollected option data for {len(all_opt_data)} symbols.")

    if all_opt_data:
        generate_html_report(all_opt_data, target_friday=target_friday)
    else:
        print("No option data collected; no report generated.")


if __name__ == "__main__":
    main()
