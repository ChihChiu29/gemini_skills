#!/usr/bin/env python3
"""
Chinese Forum Stock Sentiment & Price Range Scanner
Scans Eastmoney Guba and PTT Stock for sentiment and price expectations
targeting next week's Friday close.
Supports:
- Multiple symbols on the command line
- Persistent daily caching (under CACHE/forum_sentiment/)
- Clean, responsive HTML report with comprehensive comparison tables
- Markdown summary reports under OUTPUT/
"""

import os
import sys
import re
import json
import argparse
from datetime import datetime, timedelta
import urllib.request
import urllib.parse
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Tuple, Any

try:
    import yfinance as yf
except ImportError:
    yf = None

try:
    import bs4
except ImportError:
    bs4 = None

# Ensure UTF-8 console output on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# Common Stock Alias dictionary for Chinese forums
COMMON_ALIASES = {
    "BIDU": ["百度", "BIDU", "09888"],
    "BABA": ["阿里", "阿里巴巴", "BABA", "09988"],
    "PDD": ["拼多多", "PDD"],
    "JD": ["京东", "京東", "JD", "09618"],
    "NIO": ["蔚来", "蔚來", "NIO", "09866"],
    "XPEV": ["小鹏", "小鵬", "XPEV", "09868"],
    "LI": ["理想", "LI", "02015"],
    "TSLA": ["特斯拉", "TSLA", "馬斯克"],
    "NVDA": ["英伟达", "輝達", "NVDA", "老黃", "黃仁勳"],
    "AAPL": ["苹果", "蘋果", "AAPL"],
    "MSFT": ["微软", "微軟", "MSFT"],
    "GOOGL": ["谷歌", "Google", "GOOGL", "GOOG"],
    "AMZN": ["亚马逊", "亞馬遜", "AMZN"],
    "TSM": ["台积电", "台積電", "TSM", "2330", "GG"],
    "NKE": ["耐克", "耐吉", "NIKE", "NKE"],
    "PCG": ["太平洋煤气电力", "太平洋瓦电", "PCG"],
    "VTKX": ["VTKX"],
}

# Bullish / Bearish Sentiment Lexicon
BULL_KEYWORDS = [
    "多", "涨", "看多", "做多", "大涨", "暴涨", "拉升", "抄底", "反弹", "突破",
    "买入", "加仓", "建仓", "主升浪", "喷", "噴", "上看", "噴出", "做多",
    "低估", "起飞", "起飛", "真香", "利好", "看好", "牛", "冲", "衝", "送分題", "送分题",
    "回本", "翻倍", "主力建仓", "牛市", "稳了", "穩了", "大賺", "賺爛", "賺大錢"
]

BEAR_KEYWORDS = [
    "空", "跌", "看空", "做空", "大跌", "暴跌", "崩盘", "割肉", "止损", "破位",
    "卖出", "减仓", "清仓", "崩", "爛", "烂", "倒闭", "倒閉", "下探", "回档", "回檔",
    "高估", "套牢", "被套", "凉凉", "涼涼", "利空", "看衰", "熊", "跌停", "快逃", "完蛋",
    "垃圾", "骗局", "騙局", "收割", "韭菜", "慘", "惨", "跳水", "破底", "探底", "下殺"
]

@dataclass
class ForumPost:
    source: str
    title: str
    author: str
    publish_time: str
    url: str
    sentiment: str      # "Bullish", "Bearish", "Neutral"
    confidence: float
    target_prices: List[float] = field(default_factory=list)
    target_pcts: List[float] = field(default_factory=list)
    replies_count: int = 0
    views_count: int = 0
    snippets: List[str] = field(default_factory=list)

def get_next_friday(base_date: Optional[datetime] = None) -> datetime:
    """Calculates next week's Friday target date."""
    if base_date is None:
        base_date = datetime.now()
    days_to_this_friday = 4 - base_date.weekday()
    if days_to_this_friday <= 0:
        days_to_this_friday += 7
    next_week_friday = base_date + timedelta(days=days_to_this_friday + 7)
    return next_week_friday.replace(hour=16, minute=0, second=0, microsecond=0)

def fetch_stock_meta(ticker: str) -> Dict[str, Any]:
    """Fetches real-time price, name, and currency via yfinance."""
    meta = {
        "ticker": ticker.upper(),
        "name": ticker.upper(),
        "price": 0.0,
        "currency": "USD",
        "valid": False
    }
    if yf is None:
        return meta
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="5d")
        if not hist.empty:
            meta["price"] = round(float(hist['Close'].iloc[-1]), 2)
            meta["valid"] = True
            info = t.info if hasattr(t, "info") else {}
            meta["name"] = info.get("shortName") or info.get("longName") or ticker.upper()
            meta["currency"] = info.get("currency", "USD")
    except Exception as e:
        print(f"[-] yfinance lookup for {ticker}: {e}")
    return meta

def analyze_text_sentiment(text: str, current_price: float = 0.0) -> Tuple[str, float, List[float], List[float]]:
    """Analyzes text for sentiment polarity and explicit target price / percentage predictions."""
    bull_score = sum(text.count(word) for word in BULL_KEYWORDS)
    bear_score = sum(text.count(word) for word in BEAR_KEYWORDS)

    if bull_score + bear_score == 0:
        sentiment = "Neutral"
        conf = 0.5
    elif bull_score > bear_score:
        sentiment = "Bullish"
        conf = min(0.95, 0.55 + 0.1 * (bull_score - bear_score))
    elif bear_score > bull_score:
        sentiment = "Bearish"
        conf = min(0.95, 0.55 + 0.1 * (bear_score - bull_score))
    else:
        sentiment = "Neutral"
        conf = 0.5

    target_prices = []
    price_patterns = [
        r'(?:上看|目標|目标|看到|跌到|回測|下探|漲到|涨到|挑戰|突破)\s*[:：]?\s*[\$¥￥]?\s*([0-9]+(?:\.[0-9]+)?)',
        r'[\$¥￥]\s*([0-9]+(?:\.[0-9]+)?)\s*(?:元|塊|块|刀)?',
        r'([0-9]+(?:\.[0-9]+)?)\s*(?:元|塊|块|刀)\s*(?:出|賣|卖|買|买|接|空)'
    ]
    for pat in price_patterns:
        for m in re.finditer(pat, text):
            try:
                val = float(m.group(1))
                if current_price > 0:
                    if 0.3 * current_price <= val <= 3.0 * current_price:
                        target_prices.append(val)
                elif 2.0 <= val <= 2500.0:
                    target_prices.append(val)
            except ValueError:
                continue

    target_pcts = []
    pct_patterns = [
        r'([+-]?\s*[0-9]+(?:\.[0-9]+)?)\s*%',
        r'(?:漲|涨|跌|回檔|回档)\s*([0-9]+(?:\.[0-9]+)?)\s*%'
    ]
    for pat in pct_patterns:
        for m in re.finditer(pat, text):
            try:
                val = float(m.group(1).replace(" ", ""))
                if -60.0 <= val <= 100.0:
                    target_pcts.append(val)
            except ValueError:
                continue

    return sentiment, conf, list(set(target_prices)), list(set(target_pcts))

# ==========================================
# Caching Subsystem (Daily cache)
# ==========================================
def get_daily_cache_path(cache_dir: str, ticker: str) -> str:
    today_str = datetime.now().strftime("%Y%m%d")
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, f"{ticker.upper()}_{today_str}.json")

def load_from_cache(cache_dir: str, ticker: str, force_refresh: bool) -> Optional[List[Dict]]:
    if force_refresh:
        return None
    cache_file = get_daily_cache_path(cache_dir, ticker)
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("posts")
        except Exception:
            return None
    return None

def save_to_cache(cache_dir: str, ticker: str, posts: List[ForumPost]):
    cache_file = get_daily_cache_path(cache_dir, ticker)
    try:
        data = {
            "ticker": ticker.upper(),
            "cached_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "posts": [asdict(p) for p in posts]
        }
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[-] Cache save failed for {ticker}: {e}")

# ==========================================
# Scrapers
# ==========================================
def scrape_eastmoney_guba(ticker: str, aliases: List[str], current_price: float, max_pages: int = 2) -> List[ForumPost]:
    posts: List[ForumPost] = []
    code = f"us{ticker.lower()}"
    headers = {"User-Agent": USER_AGENT}

    for page in range(1, max_pages + 1):
        url = f"https://guba.eastmoney.com/list,{code}_{page}.html" if page > 1 else f"https://guba.eastmoney.com/list,{code}.html"
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=6) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
            m = re.search(r'var article_list=(\{.*?\});\s*var other_list', html, re.DOTALL)
            if not m:
                continue
            data = json.loads(m.group(1))
            items = data.get("re", [])
            for item in items:
                title = item.get("post_title", "").strip()
                if any(ign in title for ign in ["一览", "研报", "收盘一览", "早报", "晚报", "重要公告"]):
                    continue
                author = item.get("user_nickname", "佚名")
                pub_time = item.get("post_publish_time", "")
                post_id = item.get("post_id", "")
                click_count = item.get("post_click_count", 0)
                reply_count = item.get("post_comment_count", 0)
                post_url = f"https://guba.eastmoney.com/news,{code},{post_id}.html"

                sentiment, conf, t_prices, t_pcts = analyze_text_sentiment(title, current_price)
                posts.append(ForumPost(
                    source="Eastmoney Guba",
                    title=title,
                    author=author,
                    publish_time=pub_time,
                    url=post_url,
                    sentiment=sentiment,
                    confidence=conf,
                    target_prices=t_prices,
                    target_pcts=t_pcts,
                    replies_count=reply_count,
                    views_count=click_count,
                    snippets=[title]
                ))
        except Exception:
            pass
    return posts

def scrape_ptt_stock(ticker: str, aliases: List[str], current_price: float, max_posts: int = 10) -> List[ForumPost]:
    if bs4 is None:
        return []
    posts: List[ForumPost] = []
    headers = {"User-Agent": USER_AGENT, "Cookie": "over18=1"}
    
    search_queries = [ticker]
    for a in aliases:
        if a.upper() != ticker.upper() and len(a) >= 2:
            search_queries.append(a)
            break

    seen_urls = set()
    for q in search_queries:
        encoded_q = urllib.parse.quote(q)
        search_url = f"https://www.ptt.cc/bbs/Stock/search?q={encoded_q}"
        try:
            req = urllib.request.Request(search_url, headers=headers)
            with urllib.request.urlopen(req, timeout=6) as resp:
                html = resp.read()
            soup = bs4.BeautifulSoup(html, "html.parser")
            rent_items = soup.select("div.r-ent")
            for item in rent_items[:max_posts]:
                t_tag = item.select_one("div.title a")
                if not t_tag:
                    continue
                href = t_tag.get("href", "")
                if not href or href in seen_urls:
                    continue
                seen_urls.add(href)
                post_url = f"https://www.ptt.cc{href}"
                title = t_tag.get_text().strip()
                author = item.select_one("div.author").get_text().strip() if item.select_one("div.author") else "PTT鄉民"
                date_str = item.select_one("div.date").get_text().strip() if item.select_one("div.date") else ""

                snippets = [title]
                combined_text = title + "\n"
                reply_count = 0
                try:
                    p_req = urllib.request.Request(post_url, headers=headers)
                    with urllib.request.urlopen(p_req, timeout=5) as p_resp:
                        p_soup = bs4.BeautifulSoup(p_resp.read(), "html.parser")
                    main_c = p_soup.select_one("#main-content")
                    if main_c:
                        combined_text += main_c.get_text()[:500]
                    pushes = p_soup.select("div.push")
                    reply_count = len(pushes)
                    for push in pushes[:10]:
                        c_tag = push.select_one(".push-content")
                        if c_tag:
                            comment = c_tag.get_text().strip().lstrip(": ")
                            snippets.append(comment)
                            combined_text += " " + comment
                except Exception:
                    pass

                sentiment, conf, t_prices, t_pcts = analyze_text_sentiment(combined_text, current_price)
                posts.append(ForumPost(
                    source="PTT Stock",
                    title=title,
                    author=author,
                    publish_time=date_str,
                    url=post_url,
                    sentiment=sentiment,
                    confidence=conf,
                    target_prices=t_prices,
                    target_pcts=t_pcts,
                    replies_count=reply_count,
                    views_count=reply_count * 10,
                    snippets=snippets[:3]
                ))
        except Exception:
            pass
    return posts

def aggregate_sentiment_and_targets(
    posts: List[ForumPost],
    current_price: float
) -> Dict[str, Any]:
    total_posts = len(posts)
    if total_posts == 0:
        return {
            "total_posts": 0,
            "bullish_pct": 0.0,
            "bearish_pct": 0.0,
            "neutral_pct": 0.0,
            "overall_bias": "No Data (無社群討論)",
            "price_range": (round(current_price * 0.95, 2), round(current_price * 1.05, 2)) if current_price else (0.0, 0.0),
            "current_price": round(current_price, 2),
            "target_mentions_count": 0,
            "target_prices": []
        }

    bull_count = sum(1 for p in posts if p.sentiment == "Bullish")
    bear_count = sum(1 for p in posts if p.sentiment == "Bearish")
    neutral_count = sum(1 for p in posts if p.sentiment == "Neutral")

    bull_pct = round(bull_count / total_posts * 100, 1)
    bear_pct = round(bear_count / total_posts * 100, 1)
    neutral_pct = round(neutral_count / total_posts * 100, 1)

    if bull_pct >= bear_pct + 12:
        overall_bias = "Bullish (看多)"
    elif bear_pct >= bull_pct + 12:
        overall_bias = "Bearish (看空)"
    else:
        overall_bias = "Neutral / Mixed (多空震盪)"

    all_targets = []
    for p in posts:
        all_targets.extend(p.target_prices)

    if current_price > 0:
        for p in posts:
            for pct in p.target_pcts:
                calc_price = current_price * (1 + pct / 100.0)
                all_targets.append(calc_price)
        valid_targets = [p for p in all_targets if 0.4 * current_price <= p <= 2.2 * current_price]
    else:
        valid_targets = all_targets

    if valid_targets and len(valid_targets) >= 2:
        valid_targets.sort()
        low_idx = int(len(valid_targets) * 0.15)
        high_idx = int(len(valid_targets) * 0.85)
        expected_low = valid_targets[low_idx]
        expected_high = valid_targets[high_idx]
    elif current_price > 0:
        net_bias = (bull_pct - bear_pct) / 100.0
        drift = net_bias * 0.04
        expected_low = round(current_price * (1.0 + drift - 0.05), 2)
        expected_high = round(current_price * (1.0 + drift + 0.05), 2)
    else:
        expected_low = 0.0
        expected_high = 0.0

    return {
        "total_posts": total_posts,
        "bullish_pct": bull_pct,
        "bearish_pct": bear_pct,
        "neutral_pct": neutral_pct,
        "overall_bias": overall_bias,
        "price_range": (round(expected_low, 2), round(expected_high, 2)),
        "current_price": round(current_price, 2),
        "target_mentions_count": len(valid_targets),
        "target_prices": valid_targets
    }

# ==========================================
# Report Generators: HTML & Markdown
# ==========================================
def generate_html_report(
    results: List[Dict[str, Any]],
    target_friday: datetime,
    output_dir: str
) -> str:
    """Generates an interactive, table-first HTML report."""
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"chinese_forum_sentiment_{timestamp}.html"
    filepath = os.path.join(output_dir, filename)

    fri_str = target_friday.strftime('%Y-%m-%d (%A)')
    gen_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    html = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Chinese Forum Stock Sentiment & Price Range Report</title>
<style>
    :root {{
        --bg: #0f172a;
        --card-bg: #1e293b;
        --text: #f8fafc;
        --text-muted: #94a3b8;
        --border: #334155;
        --bull: #10b981;
        --bear: #ef4444;
        --neutral: #64748b;
        --accent: #38bdf8;
    }}
    body {{
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
        background-color: var(--bg);
        color: var(--text);
        margin: 0;
        padding: 24px;
        line-height: 1.5;
    }}
    .container {{
        max-width: 1400px;
        margin: 0 auto;
    }}
    header {{
        margin-bottom: 24px;
        border-bottom: 1px solid var(--border);
        padding-bottom: 16px;
    }}
    h1 {{
        font-size: 1.8rem;
        margin: 0 0 8px 0;
        color: var(--accent);
    }}
    .meta-bar {{
        display: flex;
        flex-wrap: wrap;
        gap: 16px;
        font-size: 0.9rem;
        color: var(--text-muted);
    }}
    .badge {{
        background: #0ea5e9;
        color: #fff;
        padding: 2px 8px;
        border-radius: 4px;
        font-weight: bold;
    }}
    .card {{
        background-color: var(--card-bg);
        border: 1px solid var(--border);
        border-radius: 8px;
        padding: 20px;
        margin-bottom: 24px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);
    }}
    h2 {{
        font-size: 1.25rem;
        margin-top: 0;
        margin-bottom: 16px;
        border-left: 4px solid var(--accent);
        padding-left: 10px;
    }}
    table {{
        width: 100%;
        border-collapse: collapse;
        margin-bottom: 12px;
        font-size: 0.92rem;
    }}
    th, td {{
        padding: 12px 14px;
        text-align: left;
        border-bottom: 1px solid var(--border);
    }}
    th {{
        background-color: rgba(255, 255, 255, 0.04);
        color: var(--text-muted);
        font-weight: 600;
        text-transform: uppercase;
        font-size: 0.8rem;
        letter-spacing: 0.5px;
    }}
    tr:hover {{
        background-color: rgba(255, 255, 255, 0.02);
    }}
    .tag-bull {{
        color: var(--bull);
        font-weight: bold;
        background: rgba(16, 185, 129, 0.1);
        padding: 4px 8px;
        border-radius: 4px;
        display: inline-block;
    }}
    .tag-bear {{
        color: var(--bear);
        font-weight: bold;
        background: rgba(239, 68, 68, 0.1);
        padding: 4px 8px;
        border-radius: 4px;
        display: inline-block;
    }}
    .tag-neutral {{
        color: #cbd5e1;
        font-weight: bold;
        background: rgba(100, 116, 139, 0.2);
        padding: 4px 8px;
        border-radius: 4px;
        display: inline-block;
    }}
    .tag-nodata {{
        color: #64748b;
        background: rgba(51, 65, 85, 0.5);
        padding: 4px 8px;
        border-radius: 4px;
        display: inline-block;
    }}
    .bar-container {{
        display: flex;
        height: 12px;
        width: 140px;
        background: #334155;
        border-radius: 6px;
        overflow: hidden;
    }}
    .bar-bull {{ background-color: var(--bull); }}
    .bar-bear {{ background-color: var(--bear); }}
    .bar-neutral {{ background-color: var(--neutral); }}
    .price-range {{
        font-family: monospace;
        font-size: 1rem;
        font-weight: bold;
        color: #f1f5f9;
    }}
    .price-delta {{
        font-size: 0.8rem;
        padding-left: 4px;
    }}
    .delta-pos {{ color: var(--bull); }}
    .delta-neg {{ color: var(--bear); }}
    a {{
        color: var(--accent);
        text-decoration: none;
    }}
    a:hover {{
        text-decoration: underline;
    }}
    .notice {{
        background: rgba(56, 189, 248, 0.08);
        border: 1px solid rgba(56, 189, 248, 0.3);
        border-radius: 6px;
        padding: 12px 16px;
        font-size: 0.88rem;
        color: #bae6fd;
    }}
</style>
</head>
<body>
<div class="container">
    <header>
        <h1>📊 Chinese Retail Forum Sentiment & Next-Week Price Target Report</h1>
        <div class="meta-bar">
            <div>Target Close Horizon: <span class="badge">{fri_str}</span></div>
            <div>Generated At: <span>{gen_time}</span></div>
            <div>Sources: <span>Eastmoney Guba (东财股吧), PTT Stock (批踢踢股板)</span></div>
        </div>
    </header>

    <div class="card">
        <h2>1. Stock Comparison & Predicted Target Ranges (Next Week's Friday)</h2>
        <table>
            <thead>
                <tr>
                    <th>Symbol</th>
                    <th>Name</th>
                    <th>Current Price</th>
                    <th>Overall Bias</th>
                    <th>Sentiment Distribution</th>
                    <th>Expected Range (Next Friday)</th>
                    <th>Implied % Move</th>
                    <th>Discussions Scanned</th>
                </tr>
            </thead>
            <tbody>
"""

    for r in results:
        meta = r["meta"]
        agg = r["agg"]
        ticker = meta["ticker"]
        cur_p = meta["price"]
        curr_str = meta["currency"]
        low_p, high_p = agg["price_range"]
        
        # Sentiment Tag
        bias = agg["overall_bias"]
        if "Bullish" in bias:
            bias_html = f'<span class="tag-bull">🟢 {bias}</span>'
        elif "Bearish" in bias:
            bias_html = f'<span class="tag-bear">🔴 {bias}</span>'
        elif "No Data" in bias:
            bias_html = f'<span class="tag-nodata">⚪ {bias}</span>'
        else:
            bias_html = f'<span class="tag-neutral">⚪ {bias}</span>'

        # Sentiment Bar
        b_pct = agg["bullish_pct"]
        be_pct = agg["bearish_pct"]
        n_pct = agg["neutral_pct"]
        bar_html = f"""
        <div style="display:flex; align-items:center; gap:8px;">
            <div class="bar-container" title="Bullish: {b_pct}%, Bearish: {be_pct}%, Neutral: {n_pct}%">
                <div class="bar-bull" style="width: {b_pct}%;"></div>
                <div class="bar-bear" style="width: {be_pct}%;"></div>
                <div class="bar-neutral" style="width: {n_pct}%;"></div>
            </div>
            <span style="font-size:0.8rem; color:var(--text-muted);">{b_pct}% / {be_pct}%</span>
        </div>
        """

        # Range and Deltas
        if cur_p > 0 and low_p > 0:
            d_low = ((low_p - cur_p) / cur_p) * 100
            d_high = ((high_p - cur_p) / cur_p) * 100
            range_html = f'<span class="price-range">${low_p:.2f} ~ ${high_p:.2f}</span>'
            delta_html = f'<span class="price-delta {"delta-pos" if d_low>=0 else "delta-neg"}">{d_low:+.1f}%</span> to <span class="price-delta {"delta-pos" if d_high>=0 else "delta-neg"}">{d_high:+.1f}%</span>'
            cur_price_str = f"<b>${cur_p:.2f}</b> {curr_str}"
        elif cur_p > 0:
            range_html = '<span style="color:var(--text-muted);">N/A</span>'
            delta_html = '<span style="color:var(--text-muted);">-</span>'
            cur_price_str = f"<b>${cur_p:.2f}</b> {curr_str}"
        else:
            range_html = '<span style="color:var(--text-muted);">N/A (No Quote)</span>'
            delta_html = '<span style="color:var(--text-muted);">-</span>'
            cur_price_str = '<span style="color:var(--text-muted);">N/A</span>'

        html += f"""
                <tr>
                    <td><b>{ticker}</b></td>
                    <td>{meta['name']}</td>
                    <td>{cur_price_str}</td>
                    <td>{bias_html}</td>
                    <td>{bar_html}</td>
                    <td>{range_html}</td>
                    <td>{delta_html}</td>
                    <td>{agg['total_posts']} items ({agg['target_mentions_count']} targets)</td>
                </tr>
        """

    html += """
            </tbody>
        </table>
    </div>
"""

    # Section 2: Detailed Thread Breakdown per Stock
    html += """
    <div class="card">
        <h2>2. Detailed Retail Threads & Opinion Highlights</h2>
    """

    for r in results:
        meta = r["meta"]
        posts = r["posts"]
        ticker = meta["ticker"]
        html += f"""
        <h3 style="margin-top:20px; color:var(--accent); font-size:1.1rem;">📌 {ticker} ({meta['name']}) - Recent Forum Activity</h3>
        """
        if not posts:
            html += '<p style="color:var(--text-muted); font-size:0.9rem;">No recent Chinese forum discussions found for this symbol.</p>'
            continue

        html += """
        <table>
            <thead>
                <tr>
                    <th style="width:140px;">Source</th>
                    <th style="width:70px;">Sentiment</th>
                    <th style="width:130px;">Author</th>
                    <th style="width:140px;">Time / Date</th>
                    <th>Discussion / Thread Title</th>
                    <th style="width:80px;">Replies</th>
                    <th style="width:60px;">Link</th>
                </tr>
            </thead>
            <tbody>
        """
        for p in posts[:12]:
            sent_tag = "🟢 多" if p.sentiment == "Bullish" else ("🔴 空" if p.sentiment == "Bearish" else "⚪ 觀望")
            safe_title = p.title.replace("<", "&lt;").replace(">", "&gt;")
            html += f"""
                <tr>
                    <td>{p.source}</td>
                    <td>{sent_tag}</td>
                    <td>{p.author}</td>
                    <td>{p.publish_time}</td>
                    <td>{safe_title}</td>
                    <td>{p.replies_count}</td>
                    <td><a href="{p.url}" target="_blank">Open</a></td>
                </tr>
            """
        html += """
            </tbody>
        </table>
        """

    html += """
    </div>

    <div class="notice">
        <b>💡 Retail Positioning Notice:</b>
        Chinese retail investor forums (Eastmoney Guba & PTT Stock) are high-velocity, emotional communities prone to FOMO during rallies and despair during pullbacks. These crowd metrics highlight short-term retail momentum and contrarian reversal zones rather than fundamental target prices.
    </div>
</div>
</body>
</html>
"""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)
    return filepath

def generate_markdown_report(
    results: List[Dict[str, Any]],
    target_friday: datetime,
    output_dir: str
) -> str:
    """Generates a comprehensive Markdown report table."""
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"sentiment_comparison_{timestamp}.md"
    filepath = os.path.join(output_dir, filename)

    fri_str = target_friday.strftime('%Y-%m-%d (%A)')

    lines = []
    lines.append("# 📊 Chinese Forum Sentiment & Next-Week Price Prediction Summary")
    lines.append(f"**Target Horizon:** Until Next Week's Friday Close (**{fri_str}**)")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    lines.append("## 1. 🎯 Cross-Stock Sentiment & Target Range Table")
    lines.append("| Ticker | Company Name | Current Price | Consensus Bias | Bull / Bear / Neutral % | Expected Next Friday Range | Implied % Shift | Scanned Items |")
    lines.append("|---|---|---|---|---|---|---|---|")

    for r in results:
        meta = r["meta"]
        agg = r["agg"]
        ticker = meta["ticker"]
        cur_p = meta["price"]
        low_p, high_p = agg["price_range"]
        
        if cur_p > 0 and low_p > 0:
            d_low = ((low_p - cur_p) / cur_p) * 100
            d_high = ((high_p - cur_p) / cur_p) * 100
            range_str = f"**${low_p:.2f} ~ ${high_p:.2f}**"
            shift_str = f"`{d_low:+.1f}%` to `{d_high:+.1f}%`"
            p_str = f"${cur_p:.2f}"
        elif cur_p > 0:
            range_str = "N/A"
            shift_str = "-"
            p_str = f"${cur_p:.2f}"
        else:
            range_str = "N/A"
            shift_str = "-"
            p_str = "N/A (Delisted/Unlisted)"

        dist_str = f"{agg['bullish_pct']}% / {agg['bearish_pct']}% / {agg['neutral_pct']}%"
        lines.append(f"| **{ticker}** | {meta['name']} | {p_str} | **{agg['overall_bias']}** | {dist_str} | {range_str} | {shift_str} | {agg['total_posts']} |")

    lines.append("\n## 2. 📢 Retail Forum Activity Notes")
    for r in results:
        meta = r["meta"]
        posts = r["posts"]
        ticker = meta["ticker"]
        lines.append(f"\n### 📌 {ticker} ({meta['name']})")
        if not posts:
            lines.append("- *No active forum posts detected.*")
            continue
        lines.append("| Source | Bias | Author | Date | Title / Snippet | Replies |")
        lines.append("|---|---|---|---|---|---|")
        for p in posts[:6]:
            sent_icon = "🟢 多" if p.sentiment == "Bullish" else ("🔴 空" if p.sentiment == "Bearish" else "⚪ 觀望")
            safe_title = p.title.replace("|", "/")
            lines.append(f"| {p.source} | {sent_icon} | {p.author} | {p.publish_time} | {safe_title} | {p.replies_count} |")

    lines.append("\n---\n*Report generated via Chinese Forum Stock Sentiment Skill.*")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return filepath

# ==========================================
# Main Execution Loop
# ==========================================
def main():
    parser = argparse.ArgumentParser(description="Scan Chinese retail forums for stock sentiment and next-week target ranges.")
    parser.add_argument("symbols", nargs="*", default=["BIDU"], help="List of stock tickers (e.g. BIDU NKE PCG VTKX). Default: BIDU")
    parser.add_argument("--pages", type=int, default=2, help="Max Eastmoney pages to scan (default: 2)")
    parser.add_argument("--ptt-max", type=int, default=10, help="Max PTT Stock threads to scan (default: 10)")
    parser.add_argument("--force-refresh", action="store_true", help="Bypass daily cache and force fresh data scrape")
    parser.add_argument("--no-cache", action="store_true", help="Do not save scraped data to cache")
    parser.add_argument("--output-dir", type=str, default=None, help="Custom output directory")

    args = parser.parse_args()
    symbols = [s.upper().strip() for s in args.symbols if s.strip()]
    if not symbols:
        symbols = ["BIDU"]

    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    output_dir = args.output_dir or os.path.join(project_root, "OUTPUT", "forum_sentiment")
    cache_dir = os.path.join(project_root, "CACHE", "forum_sentiment")

    target_friday = get_next_friday()

    print("=" * 70)
    print(f"  Chinese Forum Stock Sentiment Scanner (Multi-Symbol)")
    print("=" * 70)
    print(f"[+] Target Expiry Horizon: Next Week's Friday ({target_friday.strftime('%Y-%m-%d %A')})")
    print(f"[+] Symbols to scan: {', '.join(symbols)}")
    print(f"[+] Daily Cache: {'ENABLED (' + cache_dir + ')' if not args.no_cache else 'DISABLED'}")
    print("=" * 70)

    results = []

    for sym in symbols:
        print(f"\n>>> Analyzing {sym}...")
        meta = fetch_stock_meta(sym)
        if meta["valid"]:
            print(f"  [+] {meta['name']} | Live Price: ${meta['price']} {meta['currency']}")
        else:
            print(f"  [-] Live quote not found for {sym}; proceeding with forum scans...")

        # 1. Check daily cache
        cached_raw = load_from_cache(cache_dir, sym, args.force_refresh or args.no_cache)
        if cached_raw is not None:
            print(f"  [✓] Loaded {len(cached_raw)} items from daily cache for {sym}.")
            posts = [ForumPost(**p) for p in cached_raw]
        else:
            aliases = COMMON_ALIASES.get(sym, [sym])
            print(f"  [+] Searching Eastmoney Guba & PTT Stock (Aliases: {', '.join(aliases)})...")
            guba_posts = scrape_eastmoney_guba(sym, aliases, meta["price"], max_pages=args.pages)
            ptt_posts = scrape_ptt_stock(sym, aliases, meta["price"], max_posts=args.ptt_max)
            posts = guba_posts + ptt_posts
            print(f"  [+] Fresh scan completed: {len(guba_posts)} Guba posts, {len(ptt_posts)} PTT posts.")

            if not args.no_cache:
                save_to_cache(cache_dir, sym, posts)
                print(f"  [+] Saved {len(posts)} items to daily cache.")

        agg = aggregate_sentiment_and_targets(posts, meta["price"])
        low_p, high_p = agg["price_range"]
        print(f"  [+] Consensus: {agg['overall_bias']} | Bullish: {agg['bullish_pct']}% | Bearish: {agg['bearish_pct']}%")
        if meta["price"] > 0:
            print(f"  [+] Expected Target Range: ${low_p:.2f} ~ ${high_p:.2f} ({(low_p-meta['price'])/meta['price']*100:+.1f}% to {(high_p-meta['price'])/meta['price']*100:+.1f}%)")

        results.append({
            "meta": meta,
            "agg": agg,
            "posts": posts
        })

    # Generate Reports
    print("\n" + "=" * 70)
    print("[+] Generating reports...")
    html_path = generate_html_report(results, target_friday, output_dir)
    md_path = generate_markdown_report(results, target_friday, output_dir)

    print(f"[✓] HTML Report:     {html_path}")
    print(f"[✓] Markdown Report: {md_path}")
    print("=" * 70)

if __name__ == "__main__":
    main()
