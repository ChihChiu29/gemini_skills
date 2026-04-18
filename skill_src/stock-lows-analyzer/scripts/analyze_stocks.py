import os
import sys
import json
import datetime
from pathlib import Path

# Try to import yfinance, handle missing library gracefully
try:
    import yfinance as yf
except ImportError:
    print("Error: 'yfinance' library not found. Please install it using 'pip install yfinance'.")
    sys.exit(1)

CACHE_DIR = Path("CACHE/stock_cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_DIR = Path("OUTPUT")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def get_cache_path(symbol):
    return CACHE_DIR / f"{symbol.upper()}.json"

def fetch_data(symbol, period="3y"):
    """Fetch historical data and update cache."""
    cache_path = get_cache_path(symbol)
    
    if cache_path.exists():
        mtime = datetime.datetime.fromtimestamp(cache_path.stat().st_mtime)
        if datetime.datetime.now() - mtime < datetime.timedelta(hours=24):
            with open(cache_path, 'r') as f:
                return json.load(f)

    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period)
        if hist.empty:
            return None
        
        data = {
            "symbol": symbol.upper(),
            "last_price": float(hist['Close'].iloc[-1]),
            "history": [
                {"date": str(d.date()), "close": float(c)} 
                for d, c in zip(hist.index, hist['Close'])
            ],
            "updated_at": str(datetime.datetime.now())
        }
        
        with open(cache_path, 'w') as f:
            json.dump(data, f)
        return data
    except Exception as e:
        print(f"Error fetching {symbol}: {e}")
        return None

def calculate_lows(data):
    history = data['history']
    current_price = data['last_price']
    
    def get_low_info(days):
        cutoff = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
        prices = [h['close'] for h in history if h['date'] >= cutoff]
        if not prices: return None, None
        low = min(prices)
        proximity = (current_price / low - 1) * 100
        return low, proximity

    low_3y, prox_3y = get_low_info(3 * 365)
    low_6m, prox_6m = get_low_info(180)
    low_3m, prox_3m = get_low_info(90)
    low_7d, prox_7d = get_low_info(7)

    # Trend Analysis
    daily_change = 0
    avg_7d_change = 0
    if len(history) >= 8:
        last_closes = [h['close'] for h in history[-8:]]
        daily_change = (last_closes[-1] / last_closes[-2] - 1) * 100
        
        # Calculate daily % changes for last 7 sessions
        changes = [(last_closes[i] / last_closes[i-1] - 1) * 100 for i in range(1, 8)]
        avg_7d_change = sum(changes) / len(changes)

    return {
        "current": current_price,
        "low_3y": low_3y, "prox_3y": prox_3y,
        "low_6m": low_6m, "prox_6m": prox_6m,
        "low_3m": low_3m, "prox_3m": prox_3m,
        "low_7d": low_7d, "prox_7d": prox_7d,
        "daily_change": daily_change,
        "avg_7d_change": avg_7d_change
    }

def generate_html_report(results, output_path=None):
    now = datetime.datetime.now()
    if output_path is None:
        filename = f"stock_report_{now.strftime('%Y%m%d_%H%M%S')}.html"
        output_path = OUTPUT_DIR / filename
    else:
        output_path = Path(output_path)

    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Stock Trend & Lows Analysis</title>
        <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #333; max-width: 1400px; margin: 0 auto; padding: 20px; background-color: #f4f7f6; }
            h1, h2 { color: #2c3e50; }
            .stock-card { background: white; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); margin-bottom: 30px; padding: 20px; }
            table { width: 100%; border-collapse: collapse; margin-bottom: 20px; background: white; border-radius: 8px; overflow: hidden; font-size: 0.9em; }
            th, td { padding: 10px 12px; text-align: left; border-bottom: 1px solid #ddd; }
            th { background-color: #34495e; color: white; }
            tr:hover { background-color: #f1f1f1; }
            .orange-row { background-color: #fffaf0 !important; border-left: 5px solid #f39c12; }
            .red-row { background-color: #fff5f5 !important; border-left: 5px solid #e74c3c; }
            .trend-down { color: #e74c3c; font-weight: bold; }
            .trend-up { color: #27ae60; }
            .near-low { font-weight: bold; color: #d35400; }
            .chart-container { height: 400px; width: 100%; }
            .summary-badge { display: inline-block; padding: 4px 8px; border-radius: 4px; font-size: 0.85em; margin-right: 5px; background: #ecf0f1; }
        </style>
    </head>
    <body>
        <h1>Stock Analysis: Low Proximity & Trends</h1>
        <p>Generated on: {timestamp}</p>
        
        <div class="stock-card">
            <h2>Summary Table</h2>
            <table>
                <thead>
                    <tr>
                        <th>Symbol</th>
                        <th>Price</th>
                        <th>Near 3Y</th>
                        <th>Near 6M</th>
                        <th>Near 3M</th>
                        <th>Near 7D</th>
                        <th>Daily %</th>
                        <th>7D Avg %</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
                    {table_rows}
                </tbody>
            </table>
        </div>

        {stock_details}

        <script>
            {charts_js}
        </script>
    </body>
    </html>
    """
    
    table_rows = ""
    stock_details = ""
    charts_js = ""
    
    for idx, item in enumerate(results):
        sym = item['symbol']
        data = item['data']
        lows = item['lows']
        
        # Determine highlighting
        is_near_low = any([
            lows['prox_3y'] is not None and lows['prox_3y'] < 15,
            lows['prox_6m'] is not None and lows['prox_6m'] < 15,
            lows['prox_3m'] is not None and lows['prox_3m'] < 15
        ])
        
        is_dropping = lows['daily_change'] < 0 or lows['avg_7d_change'] < 0
        
        row_cls = ""
        if is_near_low:
            row_cls = "red-row" if is_dropping else "orange-row"
            
        def fmt_prox(val):
            if val is None: return "N/A"
            cls = "near-low" if val < 15 else ""
            return f'<span class="{cls}">{val:.2f}%</span>'

        def fmt_trend(val):
            cls = "trend-down" if val < 0 else "trend-up"
            return f'<span class="{cls}">{val:+.2f}%</span>'

        status = "Stable"
        if is_near_low and is_dropping: status = "<b>CRITICAL (Dropping at Low)</b>"
        elif is_near_low: status = "Near Support"

        table_rows += f"""
        <tr class="{row_cls}">
            <td><strong>{sym}</strong></td>
            <td>${lows['current']:.2f}</td>
            <td>{fmt_prox(lows['prox_3y'])}</td>
            <td>{fmt_prox(lows['prox_6m'])}</td>
            <td>{fmt_prox(lows['prox_3m'])}</td>
            <td>{fmt_prox(lows['prox_7d'])}</td>
            <td>{fmt_trend(lows['daily_change'])}</td>
            <td>{fmt_trend(lows['avg_7d_change'])}</td>
            <td>{status}</td>
        </tr>
        """
        
        stock_details += f"""
        <div class="stock-card">
            <h2>{sym} - Price History & Analysis</h2>
            <div id="chart-{sym}" class="chart-container"></div>
            <p>
                <strong>Current:</strong> ${lows['current']:.2f} | 
                <strong>3Y Low:</strong> ${lows['low_3y']:.2f} ({fmt_prox(lows['prox_3y'])} above) | 
                <strong>6M Low:</strong> ${lows['low_6m']:.2f} ({fmt_prox(lows['prox_6m'])} above)
            </p>
        </div>
        """
        
        dates = [h['date'] for h in data['history']]
        prices = [h['close'] for h in data['history']]
        
        charts_js += f"""
        Plotly.newPlot('chart-{sym}', [{{
            x: {json.dumps(dates)},
            y: {json.dumps(prices)},
            type: 'scatter',
            mode: 'lines',
            name: '{sym}',
            line: {{color: '#3498db'}}
        }}], {{
            title: '{sym} Price History (3 Years)',
            xaxis: {{ title: 'Date' }},
            yaxis: {{ title: 'Price (USD)' }},
            margin: {{ t: 40, b: 40, l: 60, r: 20 }}
        }});
        """

    full_html = html_template.replace("{timestamp}", datetime.datetime.now().strftime("%Y-%m-%d %H:%M")) \
                             .replace("{table_rows}", table_rows) \
                             .replace("{stock_details}", stock_details) \
                             .replace("{charts_js}", charts_js)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(full_html)
    print(f"Report generated successfully: {os.path.abspath(output_path)}")

def main():
    if len(sys.argv) < 2:
        print("Usage: python analyze_stocks.py SYMBOL1 SYMBOL2 ...")
        sys.exit(1)

    symbols = sys.argv[1:]
    results = []

    for sym in symbols:
        print(f"Analyzing {sym}...")
        data = fetch_data(sym)
        if data:
            lows = calculate_lows(data)
            results.append({"symbol": sym.upper(), "data": data, "lows": lows})

    if results:
        # Sort by proximity to 6m low
        results.sort(key=lambda x: x['lows']['prox_6m'] if x['lows']['prox_6m'] is not None else 999)
        generate_html_report(results)
    else:
        print("No data found for the provided symbols.")

if __name__ == "__main__":
    main()
