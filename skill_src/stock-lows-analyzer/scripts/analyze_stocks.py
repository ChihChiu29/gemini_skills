import os
import sys
import json
import datetime
import re
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

def fetch_data(symbol, period="max"):
    """Fetch historical data and update cache."""
    cache_path = get_cache_path(symbol)
    
    if cache_path.exists():
        mtime = datetime.datetime.fromtimestamp(cache_path.stat().st_mtime)
        if datetime.datetime.now() - mtime < datetime.timedelta(hours=24):
            with open(cache_path, 'r') as f:
                cached = json.load(f)
                if len(cached.get('history', [])) > 0:
                    return cached

    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period)
        if hist.empty:
            return None
        
        data = {
            "symbol": symbol.upper(),
            "last_price": float(hist['Close'].iloc[-1]),
            "history": [
                {"date": str(d.date()), "close": float(c), "high": float(h), "low": float(l)} 
                for d, c, h, l in zip(hist.index, hist['Close'], hist['High'], hist['Low'])
            ],
            "updated_at": str(datetime.datetime.now())
        }
        
        with open(cache_path, 'w') as f:
            json.dump(data, f)
        return data
    except Exception as e:
        print(f"Error fetching {symbol}: {e}")
        return None

def fetch_live_info(symbols):
    """Fetch latest intraday data including off-hours in one batch."""
    if not symbols:
        return {}
    try:
        print(f"Fetching live intraday data for {len(symbols)} symbols...")
        # Use 5m interval for intraday data
        data = yf.download(symbols, period="1d", interval="5m", prepost=True, progress=False)
        if data.empty:
            return {}
        
        live_info = {}
        if len(symbols) > 1:
            for sym in symbols:
                sym_up = sym.upper()
                try:
                    close_series = data['Close'][sym_up].dropna()
                    if close_series.empty: continue
                    
                    price = float(close_series.iloc[-1])
                    intraday = [{"time": str(t), "price": float(p)} for t, p in close_series.items()]
                    
                    live_info[sym_up] = {
                        "price": price,
                        "intraday": intraday,
                        "high": float(data['High'][sym_up].max()),
                        "low": float(data['Low'][sym_up].min())
                    }
                except:
                    continue
        else:
            sym = symbols[0].upper()
            close_series = data['Close'].dropna()
            if not close_series.empty:
                price = float(close_series.iloc[-1])
                intraday = [{"time": str(t), "price": float(p)} for t, p in close_series.items()]
                live_info[sym] = {
                    "price": price,
                    "intraday": intraday,
                    "high": float(data['High'].max()),
                    "low": float(data['Low'].min())
                }
            
        return live_info
    except Exception as e:
        print(f"Error fetching live prices: {e}")
        return {}

def fetch_option_premium(symbol, current_price):
    """Fetch ATM Call premium for expiry nearest to 30 days."""
    try:
        ticker = yf.Ticker(symbol)
        options = ticker.options
        if not options:
            return None
        
        today = datetime.date.today()
        target_date = today + datetime.timedelta(days=30)
        best_expiry = min(options, key=lambda x: abs(datetime.datetime.strptime(x, "%Y-%m-%d").date() - target_date))
        
        chain = ticker.option_chain(best_expiry)
        calls = chain.calls
        
        calls['diff'] = (calls['strike'] - current_price).abs()
        atm_call = calls.sort_values('diff').iloc[0]
        
        return {
            "premium": float(atm_call['lastPrice']),
            "strike": float(atm_call['strike']),
            "expiry": best_expiry
        }
    except Exception as e:
        print(f"Error fetching options for {symbol}: {e}")
        return None

def calculate_lows(data, live_info=None):
    history = data['history']
    current_price = live_info['price'] if live_info else data['last_price']
    
    def get_period_stats(days):
        cutoff = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
        relevant = [h for h in history if h['date'] >= cutoff]
        if not relevant: return None
        
        highs = [h.get('high', h['close']) for h in relevant]
        lows = [h.get('low', h['close']) for h in relevant]
        p_high = max(max(highs), current_price)
        p_low = min(min(lows), current_price)
        
        vol = (p_high / p_low - 1) * 100 if p_low > 0 else 0
        pos_pct = (current_price - p_low) / (p_high - p_low) * 100 if p_high > p_low else 0
        
        return {"high": p_high, "low": p_low, "vol": vol, "pos_pct": pos_pct}

    period_1d = None
    if live_info:
        p_high, p_low = live_info['high'], live_info['low']
        vol = (p_high / p_low - 1) * 100 if p_low > 0 else 0
        pos_pct = (current_price - p_low) / (p_high - p_low) * 100 if p_high > p_low else 0
        period_1d = {"high": p_high, "low": p_low, "vol": vol, "pos_pct": pos_pct}

    return {
        "symbol": data["symbol"],
        "data": data,
        "current": current_price,
        "intraday": live_info['intraday'] if live_info else [],
        "is_off_hour": live_info is not None and abs(current_price - data['last_price']) > 0.001,
        "regular_close": data['last_price'],
        "3y": get_period_stats(3 * 365),
        "6m": get_period_stats(180),
        "3m": get_period_stats(90),
        "7d": get_period_stats(7),
        "1d": period_1d
    }

def generate_html_report(results, output_path=None):
    now = datetime.datetime.now()
    if output_path is None:
        filename = f"stock_report_{now.strftime('%Y%m%d_%H%M%S')}.html"
        output_path = OUTPUT_DIR / filename
    else:
        output_path = Path(output_path)

    thresholds = {
        "3y": {"low": 15, "high": 95},
        "6m": {"low": 15, "high": 95},
        "3m": {"low": 20, "high": 95},
        "7d": {"low": 25, "high": 95},
        "1d": {"low": 25, "high": 95}
    }

    buy_group, sell_group, watch_group, other_group = [], [], [], []

    for item in results:
        stats = item
        lt_hits = 0
        for p_key in ['3y', '6m', '3m']:
            if stats[p_key] and stats[p_key]['pos_pct'] < thresholds[p_key]['low']: lt_hits += 1
        is_lt_buy = lt_hits >= 2
        is_st_buy_7d = stats['7d'] and stats['7d']['pos_pct'] < thresholds['7d']['low'] and stats['7d']['vol'] >= 10.0
        is_st_buy_3m = stats['3m'] and stats['3m']['vol'] > 50.0 and stats['3m']['pos_pct'] < 20.0
        is_buy = is_lt_buy or is_st_buy_7d or is_st_buy_3m
        
        is_sell = False
        is_watch = False
        for p_key in ["3y", "6m", "3m", "7d", "1d"]:
            p = stats[p_key]
            if p:
                if p['pos_pct'] > thresholds[p_key]["high"]: is_sell = True
                if (p_key == "3m" and p['vol'] > 50) or (p_key == "7d" and p['vol'] > 20): is_watch = True

        if is_buy: buy_group.append(item)
        if is_sell: sell_group.append(item)
        if is_watch: watch_group.append(item)
        if not (is_buy or is_sell or is_watch): other_group.append(item)

    buy_group.sort(key=lambda x: x['symbol'])
    sell_group.sort(key=lambda x: x['symbol'])
    watch_group.sort(key=lambda x: x['symbol'])
    other_group.sort(key=lambda x: x['symbol'])

    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Stock Multi-Period Analysis</title>
        <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #333; max-width: 1800px; margin: 0 auto; padding: 20px; background-color: #f4f7f6; }
            h1, h2 { color: #2c3e50; }
            .stock-card { background: white; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); margin-bottom: 30px; padding: 20px; overflow-x: auto; }
            table { width: 100%; border-collapse: collapse; margin-bottom: 20px; background: white; border-radius: 8px; overflow: hidden; font-size: 0.8em; }
            th, td { padding: 8px 10px; text-align: right; border: 1px solid #eee; }
            th { background-color: #34495e; color: white; text-align: center; }
            tbody td:first-child { text-align: left; font-weight: bold; background-color: #f9f9f9; }
            .red-cell { background-color: #ffcccc; color: #cc0000; font-weight: bold; }
            .green-cell { background-color: #ccffcc; color: #006600; font-weight: bold; }
            .orange-cell { background-color: #ffe5cc; color: #e67e22; font-weight: bold; }
            .off-hour-text { color: #8e44ad; font-weight: bold; font-size: 0.85em; }
            .watch-reason { font-size: 0.85em; list-style-type: none; padding: 0; margin: 0; }
            .group-header { background-color: #2c3e50; color: white; padding: 10px; margin-top: 40px; border-radius: 8px 8px 0 0; }
            .buy-header { background-color: #e74c3c; }
            .sell-header { background-color: #27ae60; }
            .watch-header { background-color: #e67e22; }
            .chart-container { height: 450px; width: 100%; margin-bottom: 20px; }
            .buy-text { color: #cc0000; font-weight: bold; }
            .sell-text { color: #006600; font-weight: bold; }
            .watch-text { color: #e67e22; font-weight: bold; }
            .charts-row { display: flex; flex-wrap: wrap; gap: 20px; }
            .chart-box { flex: 1; min-width: 600px; }
        </style>
        <script>
            function autoScaleY(gd) {
                const xRange = gd.layout.xaxis.range;
                const data = gd.data[0];
                let minVal = Infinity, maxVal = -Infinity, found = false;
                const minX = new Date(xRange[0]).getTime(), maxX = new Date(xRange[1]).getTime();
                for (let i = 0; i < data.x.length; i++) {
                    const xDate = new Date(data.x[i]).getTime();
                    if (xDate >= minX && xDate <= maxX) {
                        if (data.y[i] < minVal) minVal = data.y[i];
                        if (data.y[i] > maxVal) maxVal = data.y[i];
                        found = true;
                    }
                }
                if (found) {
                    const range = maxVal - minVal;
                    const margin = range === 0 ? 1 : range * 0.1;
                    Plotly.relayout(gd, { 'yaxis.range': [minVal - margin, maxVal + margin] });
                }
            }
        </script>
    </head>
    <body>
        <h1>Stock Analysis: Grouped Watchlist (Including Off-Hours)</h1>
        <p>Generated on: {timestamp}</p>
        {content}
        <script>{charts_js}</script>
    </body>
    </html>
    """

    def render_table(group_results, group_name, header_class):
        if not group_results: return ""
        is_buy_table = "BUY" in group_name
        table_html = f'<div class="group-header {header_class}"><h2>{group_name}</h2></div>'
        table_html += f"""
        <div class="stock-card">
            <table>
                <thead>
                    <tr>
                        <th rowspan="2">Symbol</th>
                        <th rowspan="2">Price</th>
                        {"<th rowspan='2'>Option Insights</th>" if is_buy_table else ""}
                        <th colspan="4">3 Year Period</th>
                        <th colspan="4">6 Month Period</th>
                        <th colspan="4">3 Month Period</th>
                        <th colspan="4">7 Day Period</th>
                        <th colspan="4">1 Day Period</th>
                        <th rowspan="2">Watch Reasons</th>
                    </tr>
                    <tr>
                        <th>High</th><th>Low</th><th>Vol</th><th>Pos%</th>
                        <th>High</th><th>Low</th><th>Vol</th><th>Pos%</th>
                        <th>High</th><th>Low</th><th>Vol</th><th>Pos%</th>
                        <th>High</th><th>Low</th><th>Vol</th><th>Pos%</th>
                        <th>High</th><th>Low</th><th>Vol</th><th>Pos%</th>
                    </tr>
                </thead>
                <tbody>
        """
        for item in group_results:
            sym, stats = item['symbol'], item
            reasons = []
            lt_hits = sum(1 for p in ['3y', '6m', '3m'] if stats[p] and stats[p]['pos_pct'] < thresholds[p]['low'])
            if lt_hits >= 2: reasons.append('<span class="buy-text">BUY (Long Term)</span>: Multi-period low')
            if stats['7d'] and stats['7d']['pos_pct'] < thresholds['7d']['low'] and stats['7d']['vol'] >= 10.0: reasons.append('<span class="buy-text">BUY (Short Term)</span>: 7D Low + Vol')
            if stats['3m'] and stats['3m']['vol'] > 50.0 and stats['3m']['pos_pct'] < 20.0: reasons.append('<span class="buy-text">BUY (Short Term)</span>: 3M Vol Bottom')

            option_html = ""
            if is_buy_table:
                if stats.get('option_data'):
                    opt = stats['option_data']
                    option_html = f"<td><div style='font-size: 0.9em; text-align: left;'><strong>Ceiling: ${stats['current']+opt['premium']:.2f}</strong><br><span style='color: #666;'>Strike: ${opt['strike']:.2f}</span><br><span style='color: #666;'>Cost: ${opt['premium']:.2f}/sh</span><br><small>Exp: {opt['expiry']}</small></div></td>"
                else: option_html = "<td>-</td>"

            price_display = f"${stats['current']:.2f}"
            if stats.get('is_off_hour'): price_display += f"<br><span class='off-hour-text'>LIVE (Off-Hours)</span><br><small style='color:#999'>Close: ${stats['regular_close']:.2f}</small>"

            row_html = f"<tr><td><a href='#chart-{sym}' style='text-decoration:none; color:inherit;'>{sym} 📈</a></td><td>{price_display}</td>{option_html}"
            for p_key in ["3y", "6m", "3m", "7d", "1d"]:
                p = stats[p_key]
                if p:
                    pos_cls = "red-cell" if p['pos_pct'] < thresholds[p_key]["low"] else ("green-cell" if p['pos_pct'] > thresholds[p_key]["high"] else "")
                    if p['pos_pct'] < thresholds[p_key]["low"] and not any("BUY" in r for r in reasons): reasons.append(f'<span class="buy-text">BUY</span>: {p_key.upper()} Low')
                    elif p['pos_pct'] > thresholds[p_key]["high"]: reasons.append(f'<span class="sell-text">SELL</span>: {p_key.upper()} High')
                    vol_cls = "orange-cell" if ((p_key == "3m" and p['vol'] > 50) or (p_key == "7d" and p['vol'] > 20)) else ""
                    if vol_cls: reasons.append(f'<span class="watch-text">WATCH</span>: {p_key.upper()} Vol')
                    row_html += f"<td>${p['high']:.2f}</td><td>${p['low']:.2f}</td><td class='{vol_cls}'>{p['vol']:.1f}%</td><td class='{pos_cls}'>{p['pos_pct']:.1f}%</td>"
                else: row_html += "<td>-</td><td>-</td><td>-</td><td>-</td>"
            
            seen_lt_st = any("BUY (" in r for r in reasons)
            unique_reasons = [r for r in list(dict.fromkeys(reasons)) if not ("BUY" in r and "BUY (" not in r and seen_lt_st)]
            row_html += f'<td><ul class="watch-reason">{"".join([f"<li>{r}</li>" for r in unique_reasons])}</ul></td></tr>'
            table_html += row_html
        return table_html + "</tbody></table></div>"

    content = render_table(buy_group, "BUY TARGETS (Long/Short Term Opportunities)", "buy-header")
    content += render_table(sell_group, "SELL TARGETS (Near Historical Highs)", "sell-header")
    content += render_table(watch_group, "WATCHLIST (High Volatility)", "watch-header")
    content += render_table(other_group, "OTHER STOCKS", "")

    charts_js, stock_details_html, seen_symbols = "", "", set()
    all_analyzed = buy_group + sell_group + watch_group + other_group
    for item in all_analyzed:
        sym = item['symbol']
        if sym in seen_symbols: continue
        seen_symbols.add(sym)
        stock_details_html += f"<div id='chart-{sym}' class='stock-card'><h2>{sym} - Performance Analysis <a href='#' style='font-size: 0.5em; vertical-align: middle;'>[Top]</a></h2><div class='charts-row'><div class='chart-box'><h3>Full History</h3><div id='plot-max-{sym}' class='chart-container'></div></div><div class='chart-box'><h3>Intraday (1D incl. Off-Hours)</h3><div id='plot-1d-{sym}' class='chart-container'></div></div></div></div>"
        
        hist_data = item['data']
        dates_max, prices_max = [h['date'] for h in hist_data['history']], [h['close'] for h in hist_data['history']]
        times_1d, prices_1d = [h['time'] for h in item['intraday']], [h['price'] for h in item['intraday']]
        
        charts_js += f"""
        var plotMax_{sym} = document.getElementById('plot-max-{sym}');
        Plotly.newPlot(plotMax_{sym}, [{{ x: {json.dumps(dates_max)}, y: {json.dumps(prices_max)}, type: 'scatter', mode: 'lines', name: '{sym} Hist', line: {{color: '#3498db'}} }}], {{
            title: 'Historical', xaxis: {{ title: 'Date', rangeselector: {{ buttons: [ {{ count: 7, label: '7d', step: 'day', stepmode: 'backward' }}, {{ count: 3, label: '3m', step: 'month', stepmode: 'backward' }}, {{ count: 6, label: '6m', step: 'month', stepmode: 'backward' }}, {{ count: 1, label: '1y', step: 'year', stepmode: 'backward' }}, {{ count: 3, label: '3y', step: 'year', stepmode: 'backward' }}, {{ step: 'all', label: 'max' }} ] }}, rangeslider: {{ visible: true }}, type: 'date' }},
            yaxis: {{ title: 'Price', autorange: true }}, margin: {{ t: 40, b: 40, l: 60, r: 20 }}
        }});
        plotMax_{sym}.on('plotly_relayout', function(ed) {{ if (ed['xaxis.range[0]'] || ed['xaxis.range'] || ed['xaxis.autorange']) {{ autoScaleY(plotMax_{sym}); }} }});

        var plot1d_{sym} = document.getElementById('plot-1d-{sym}');
        Plotly.newPlot(plot1d_{sym}, [{{ x: {json.dumps(times_1d)}, y: {json.dumps(prices_1d)}, type: 'scatter', mode: 'lines+markers', name: '{sym} 1D', line: {{color: '#8e44ad'}} }}], {{
            title: 'Intraday (Live)', xaxis: {{ title: 'Time', rangeslider: {{ visible: true }} }},
            yaxis: {{ title: 'Price', autorange: true }}, margin: {{ t: 40, b: 40, l: 60, r: 20 }}
        }});
        """
    full_html = html_template.replace("{timestamp}", datetime.datetime.now().strftime("%Y-%m-%d %H:%M")).replace("{content}", content + stock_details_html).replace("{charts_js}", charts_js)
    with open(output_path, 'w', encoding='utf-8') as f: f.write(full_html)
    print(f"Report generated: {os.path.abspath(output_path)}")

def main():
    if len(sys.argv) < 2:
        ref_path = Path(__file__).parent.parent / "references" / "tech_stocks.md"
        if ref_path.exists():
            print(f"Reading default symbols from {ref_path}...")
            with open(ref_path, 'r') as f:
                content = f.read()
                symbols = list(dict.fromkeys(re.findall(r'- ([A-Z]+)', content)))
        else: sys.exit(1)
    else: symbols = sys.argv[1:]

    live_info = fetch_live_info(symbols)
    results = []
    for sym in symbols:
        print(f"Analyzing {sym}...")
        data = fetch_data(sym)
        if data:
            res = calculate_lows(data, live_info=live_info.get(sym.upper()))
            # Manual hits calculation to avoid logic complexity in sum
            lt_hits = 0
            if res['3y'] and res['3y']['pos_pct'] < 15: lt_hits += 1
            if res['6m'] and res['6m']['pos_pct'] < 15: lt_hits += 1
            if res['3m'] and res['3m']['pos_pct'] < 20: lt_hits += 1
            
            is_st_buy = (res['7d'] and res['7d']['pos_pct'] < 25 and res['7d']['vol'] >= 10.0) or (res['3m'] and res['3m']['vol'] > 50.0 and res['3m']['pos_pct'] < 20.0)
            if lt_hits >= 2 or is_st_buy:
                print(f"  > Fetching options for BUY target {sym}...")
                res['option_data'] = fetch_option_premium(sym, res['current'])
            else: res['option_data'] = None
            results.append(res)
    if results: generate_html_report(results)

if __name__ == "__main__":
    main()
