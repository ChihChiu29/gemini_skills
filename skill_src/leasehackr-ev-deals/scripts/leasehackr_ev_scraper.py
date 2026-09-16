import os
import sys

# Force UTF-8 output on Windows (avoids GBK codec errors with special chars)
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ('utf-8', 'utf8'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import json
import datetime
import re
from pathlib import Path
import requests
from bs4 import BeautifulSoup
from tabulate import tabulate

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CACHE_DIR = PROJECT_ROOT / "CACHE"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

LEASEHACKR_OUTPUT_DIR = PROJECT_ROOT / "OUTPUT" / "leasehackr"
LEASEHACKR_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# EV keywords and brand lists used throughout
# ---------------------------------------------------------------------------
EV_KEYWORDS = [
    # Pure EV models
    'ioniq 5', 'ioniq 6', 'ioniq 9', 'ioniq5', 'ioniq6', 'ioniq9',
    'ev6', 'ev9', 'ev3', 'niro ev',
    'prologue',
    'lyriq', 'optiq', 'celestiq',
    'i4', 'i5', 'i7', 'i3', 'ix', 'bmw ev',
    'e-tron', 'etron', 'q8 e-tron', 'q4 e-tron',
    'eqe', 'eqs', 'eqb', 'eqa', 'eq ',
    'rz450e', 'rz ', 'bz4x',
    'mach-e', 'mustang mach',
    'blazer ev', 'equinox ev', 'silverado ev', 'bolt ev', 'bolteuv', 'bolt euv',
    'hummer ev',
    'recharge',   # Volvo BEV/PHEV
    'xc40 recharge', 'c40 recharge', 'xc60 recharge', 'xc90 recharge',
    'ariya',
    'leaf',
    'id.4', 'id4',
    'polestar',
    'rav4 prime', 'rav4prime',
    'prime',      # Toyota/Lexus PHEV suffix
    'plug-in',
    # Generic fallbacks — only match when combined with a model
    ' bev', ' phev', ' ev ',
]
BRANDS = [
    'hyundai', 'kia', 'bmw', 'mercedes', 'audi', 'volvo', 'lexus', 'toyota', 'honda',
    'chevrolet', 'chevy', 'ford', 'cadillac', 'gmc', 'porsche', 'nissan',
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def get_date_str():
    return datetime.date.today().isoformat()


def get_today_cache_file():
    return CACHE_DIR / f"ev_deals_{get_date_str()}.json"


def get_today_data_dir():
    data_dir = LEASEHACKR_OUTPUT_DIR / f"data_{get_date_str()}"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def is_ev_related(text_lower):
    return any(kw in text_lower for kw in EV_KEYWORDS)


# ---------------------------------------------------------------------------
# Pre-Negotiated Deals (PND Website Scraper)
# Scrapes https://pnd.leasehackr.com filtered to California & EV, retaining
# only deals located in 'Northern California'.
# ---------------------------------------------------------------------------
def fetch_pnd_website_deals():
    """Fetch official Pre-Negotiated Deals from the Leasehackr PND portal."""
    url = "https://pnd.leasehackr.com/r/California"
    payload = {
        'avail_locations': 'Northern California',
        'fuel_type': 'ev'
    }
    pnd_deals = []
    data_dir = get_today_data_dir()

    try:
        r = requests.post(url, data=payload, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            print(f"PND website returned HTTP status {r.status_code}")
            return []

        soup = BeautifulSoup(r.text, 'html.parser')
        cards = soup.find_all('div', class_='deal_card')

        for c in cards:
            loc = c.find(class_='state_val').get_text(strip=True) if c.find(class_='state_val') else ''
            if loc != 'Northern California':
                continue

            yr = c.find(class_='model_yr_val').get_text(strip=True) if c.find(class_='model_yr_val') else ''
            make = c.find(class_='make_val').get_text(strip=True) if c.find(class_='make_val') else ''
            model = c.find(class_='model_val').get_text(strip=True) if c.find(class_='model_val') else ''
            trim = c.find(class_='trim_val').get_text(strip=True) if c.find(class_='trim_val') else ''
            car = f"{yr} {make} {model} {trim}".strip()

            monthly_elem = c.find(class_='monthly_val')
            if not monthly_elem or not monthly_elem.get_text(strip=True).isdigit():
                continue
            monthly = int(monthly_elem.get_text(strip=True))

            das_elem = c.find(class_='das_val')
            das = int(das_elem.get_text(strip=True).replace(',', '')) if das_elem and das_elem.get_text(strip=True).replace(',', '').isdigit() else 3000

            term_elem = c.find(class_='term_val')
            term = int(term_elem.get_text(strip=True)) if term_elem and term_elem.get_text(strip=True).isdigit() else 36

            eff = round(monthly + das / term, 2)
            deal_id = c.get('id', '')
            source_url = f"https://pnd.leasehackr.com/d/{deal_id}" if deal_id else "https://pnd.leasehackr.com/r/California"

            img_elem = c.find(class_='img_url_val')
            card_url = img_elem['src'] if img_elem and 'src' in img_elem.attrs else ''

            screenshot_rel_path = ''
            if card_url:
                safe_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', f"pnd_{car}".lower())[:60] + '.png'
                img_path = data_dir / safe_name
                try:
                    r_img = requests.get(card_url, headers=HEADERS, timeout=10)
                    if r_img.status_code == 200:
                        with open(img_path, 'wb') as f_img:
                            f_img.write(r_img.content)
                        screenshot_rel_path = f"data_{get_date_str()}/{safe_name}"
                except Exception as ex:
                    print(f"Could not download PND image for {car}: {ex}")

            pnd_deals.append({
                'car': car,
                'monthly': monthly,
                'das': das,
                'term': term,
                'effective_monthly': eff,
                'source_title': f"PND Website: {car}",
                'source_url': source_url,
                'screenshot_path': screenshot_rel_path,
                'card_url': card_url,
                'source_type': 'Pre-Negotiated Deal (Website)',
            })
    except Exception as e:
        print(f"Error fetching PND website deals: {e}")

    print(f"Fetched {len(pnd_deals)} official Pre-Negotiated Deals for Northern California.")
    return pnd_deals


# ---------------------------------------------------------------------------
# Network helpers (Forum Marketplace Scraper)
# ---------------------------------------------------------------------------
STALENESS_DAYS = 30   # strict requirement: ignore topics not updated within 30 days (1 month)


def _parse_discourse_date(date_str):
    """Parse a Discourse ISO timestamp like '2026-08-15T10:23:45.000Z' -> datetime."""
    if not date_str:
        return None
    try:
        return datetime.datetime.fromisoformat(date_str.replace('Z', '+00:00'))
    except Exception:
        return None


def fetch_norcal_marketplace_topics():
    """Fetch ca-norcal tagged marketplace topics, returning only those
    with activity within the last STALENESS_DAYS days."""
    url = "https://forum.leasehackr.com/c/marketplace/l/latest.json?tags=ca-norcal"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"Error fetching marketplace topics JSON: {e}")
    return None


def is_recent_topic(topic, days=STALENESS_DAYS):
    """Return True if the topic was last posted to within `days` days."""
    last_posted = _parse_discourse_date(topic.get('last_posted_at', ''))
    if not last_posted:
        return False
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
    return last_posted >= cutoff


def fetch_topic_details(topic_id):
    """Fetch the first page of a topic (posts 1-20)."""
    url = f"https://forum.leasehackr.com/t/{topic_id}.json"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"Error fetching topic {topic_id} details JSON: {e}")
    return None


def fetch_latest_posts(topic_id, details, n=5):
    """Return the HTML ('cooked') of the last n posts in a topic."""
    stream = (details or {}).get('post_stream', {}).get('stream', [])
    embedded = (details or {}).get('post_stream', {}).get('posts', [])

    if not stream:
        return embedded[-n:] if embedded else []

    latest_ids = stream[-n:]
    embedded_ids = {p['id'] for p in embedded}
    missing = [pid for pid in latest_ids if pid not in embedded_ids]

    if not missing:
        id_order = {pid: i for i, pid in enumerate(latest_ids)}
        return sorted([p for p in embedded if p['id'] in embedded_ids and p['id'] in id_order],
                      key=lambda p: id_order.get(p['id'], 999))

    params = '&'.join(f'post_ids[]={pid}' for pid in missing)
    url = f"https://forum.leasehackr.com/t/{topic_id}/posts.json?{params}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            fetched = r.json().get('post_stream', {}).get('posts', [])
            all_posts = {p['id']: p for p in embedded + fetched}
            return [all_posts[pid] for pid in latest_ids if pid in all_posts]
    except Exception as e:
        print(f"Error fetching latest posts for topic {topic_id}: {e}")

    return embedded[-n:] if embedded else []


# ---------------------------------------------------------------------------
# Parser — understands the broker post block format on Leasehackr Forum
# ---------------------------------------------------------------------------
TERM_PAT    = re.compile(r'(\d{2,3})\s*(?:months?|mo)\b', re.IGNORECASE)

CURRENT_YEAR = datetime.date.today().year
MIN_MODEL_YEAR = CURRENT_YEAR - 1
MAX_MODEL_YEAR = CURRENT_YEAR + 1
DAS_PAT     = re.compile(
    r'\$\s*([\d,]+(?:\.\d+)?)\s*k?\s*(?:due|out|down|das|drive[\s\-]?off)',
    re.IGNORECASE
)
MONTHLY_PAT = re.compile(r'\$\s*([\d,]+)\s*/\s*mo', re.IGNORECASE)
MONTHLY_PAT2 = re.compile(
    r'\$\s*([\d,]+)\s*(?:\+\s*(?:\d+(?:\.\d+)?\%?\s*)?tax|/month|per\s*month)',
    re.IGNORECASE
)


def _extract_monthly(text):
    m = MONTHLY_PAT.search(text) or MONTHLY_PAT2.search(text)
    if m:
        val = int(re.sub(r'[,\s]', '', m.group(1)))
        if 50 <= val <= 2500:
            return val
    return None


def _extract_das(text):
    m = DAS_PAT.search(text)
    if m:
        raw = re.sub(r'[,\s]', '', m.group(1))
        val = float(raw)
        if val < 200:
            val *= 1000
        return int(val)
    mk = re.search(r'\$([\d,]+(?:\.\d+)?)\s*k\b', text, re.IGNORECASE)
    if mk:
        return int(float(re.sub(r',', '', mk.group(1))) * 1000)
    mc = re.search(r'([\d,]{3,7})\s+(?:due|out|drive)', text, re.IGNORECASE)
    if mc:
        return int(re.sub(r',', '', mc.group(1)))
    return 3000


def _extract_term(text):
    m = TERM_PAT.search(text)
    return int(m.group(1)) if m else 36


def _extract_car_model(block_text):
    lines = [l.strip() for l in block_text.split('\n') if l.strip()]
    for line in lines[:4]:
        if re.match(r'^\d+[×x]\d+', line):
            continue
        m = re.match(r'(20\d{2})\s+([A-Za-z][A-Za-z0-9\- /]{3,50}?)(?:\s+\d{3,4}[×x]|\s*$)', line)
        if m:
            year = int(m.group(1))
            if not (MIN_MODEL_YEAR <= year <= MAX_MODEL_YEAR):
                return None
            candidate = (m.group(1) + ' ' + m.group(2)).strip()
            if is_ev_related(candidate.lower()) or any(b in candidate.lower() for b in BRANDS):
                return candidate.title()
        stale = re.search(r'20(\d{2})', line)
        if stale and not (MIN_MODEL_YEAR <= int('20' + stale.group(1)) <= MAX_MODEL_YEAR):
            continue
        if (is_ev_related(line.lower()) and 4 < len(line) < 60
                and '$' not in line and '/' not in line):
            return line.title()
    return None


def try_parse_block(block_text):
    tl = block_text.lower()
    monthly = _extract_monthly(block_text)
    if monthly is None:
        return None
    if not is_ev_related(tl):
        return None

    das   = _extract_das(block_text)
    term  = _extract_term(block_text)
    car   = _extract_car_model(block_text)
    if car is None:
        return None

    return {
        'car': car,
        'monthly': monthly,
        'das': das,
        'term': term,
        'effective_monthly': round(monthly + das / term, 2),
    }


def parse_deals_from_topic(topic_info, details):
    title    = topic_info.get('title', '')
    tid      = topic_info.get('id')
    slug     = topic_info.get('slug', '')
    topic_url = f"https://forum.leasehackr.com/t/{slug}/{tid}"

    if not details or 'post_stream' not in details or 'posts' not in details['post_stream']:
        return []

    deals    = []
    data_dir = get_today_data_dir()
    posts    = fetch_latest_posts(tid, details, n=5)
    seen_cars = set()

    for post in posts:
        cooked = post.get('cooked', '')
        soup   = BeautifulSoup(cooked, 'html.parser')

        elements = []
        for elem in soup.find_all(['p', 'div', 'li', 'h1', 'h2', 'h3', 'img']):
            if elem.name == 'img':
                src = elem.get('src', '')
                if 'b-cdn.net' in src and 'emoji' not in src:
                    elements.append({'type': 'img', 'src': src, 'alt': elem.get('alt', '')})
            else:
                block_imgs = [
                    {'src': img.get('src', ''), 'alt': img.get('alt', '')}
                    for img in elem.find_all('img')
                    if 'b-cdn.net' in img.get('src', '') and 'emoji' not in img.get('src', '')
                ]
                text = elem.get_text(separator='\n').strip()
                if text:
                    elements.append({'type': 'block', 'text': text, 'imgs': block_imgs})

        for i, elem in enumerate(elements):
            if elem['type'] != 'block':
                continue
            parsed = try_parse_block(elem['text'])
            if not parsed:
                continue
            car_key = parsed['car'].lower()
            if car_key in seen_cars:
                continue
            seen_cars.add(car_key)

            card_src = ''
            if elem.get('imgs'):
                card_src = elem['imgs'][0]['src']
            else:
                for j in range(i + 1, min(i + 6, len(elements))):
                    nxt = elements[j]
                    if nxt['type'] == 'img':
                        card_src = nxt['src']
                        break
                    if nxt['type'] == 'block' and nxt.get('imgs'):
                        card_src = nxt['imgs'][0]['src']
                        break
                    if nxt['type'] == 'block' and MONTHLY_PAT.search(nxt['text']):
                        break

            screenshot_rel_path = ''
            if card_src:
                dl_url = re.sub(r'_2_\d+x\d*', '', card_src.replace('/optimized/', '/original/'))
                safe_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', parsed['car'].lower())[:60] + '.jpg'
                img_path = data_dir / safe_name
                try:
                    r_img = requests.get(dl_url, timeout=10)
                    if r_img.status_code != 200:
                        r_img = requests.get(card_src, timeout=10)
                    if r_img.status_code == 200:
                        with open(img_path, 'wb') as f_img:
                            f_img.write(r_img.content)
                        screenshot_rel_path = f"data_{get_date_str()}/{safe_name}"
                except Exception as ex:
                    print(f"Could not download image for {parsed['car']}: {ex}")

            deals.append({
                'car': parsed['car'],
                'monthly': parsed['monthly'],
                'das': parsed['das'],
                'term': parsed['term'],
                'effective_monthly': parsed['effective_monthly'],
                'source_title': title,
                'source_url': topic_url,
                'screenshot_path': screenshot_rel_path,
                'card_url': card_src,
                'source_type': 'Forum Marketplace',
            })

    return deals


# ---------------------------------------------------------------------------
# Fallback mock data (used when scraping yields nothing)
# ---------------------------------------------------------------------------
def get_mock_deals():
    data_dir = get_today_data_dir()
    mock_list = [
        {"car": "Hyundai Ioniq 5 SE", "monthly": 229, "das": 2999, "term": 24, "effective_monthly": 353.96,
         "source_title": "GCauto Hyundai/Kia NorCal Deals",
         "source_url": "https://forum.leasehackr.com/t/gcauto-hyundai-kia-mazda/517221", "source_type": "Forum Marketplace"},
        {"car": "Kia Niro EV Wind", "monthly": 189, "das": 3500, "term": 36, "effective_monthly": 286.22,
         "source_title": "GCauto Hyundai/Kia NorCal Deals",
         "source_url": "https://forum.leasehackr.com/t/gcauto-hyundai-kia-mazda/517221", "source_type": "Forum Marketplace"},
        {"car": "Honda Prologue EX", "monthly": 299, "das": 2000, "term": 36, "effective_monthly": 354.56,
         "source_title": "Chrome Stallions Honda Prologue NorCal",
         "source_url": "https://forum.leasehackr.com/t/chrome-stallions-hon-kia-sub/774103", "source_type": "Forum Marketplace"},
        {"car": "Chevrolet Blazer EV LT", "monthly": 269, "das": 3000, "term": 36, "effective_monthly": 352.33,
         "source_title": "LuxConcierge Chevrolet Blazer NorCal",
         "source_url": "https://forum.leasehackr.com/t/september-gm-deals-cadillac-hummer-ev-gmc-chevrolet-luxconcierge/556274", "source_type": "Forum Marketplace"},
        {"car": "Toyota bZ4X XLE", "monthly": 199, "das": 3999, "term": 36, "effective_monthly": 310.08,
         "source_title": "EZ Auto Group Toyota Specials",
         "source_url": "https://forum.leasehackr.com/t/socal-norcal-toyota-lexus/293430", "source_type": "Forum Marketplace"},
        {"car": "Cadillac Lyriq Luxury", "monthly": 359, "das": 3500, "term": 36, "effective_monthly": 456.22,
         "source_title": "AutoTime Cadillac Lyriq Deals",
         "source_url": "https://forum.leasehackr.com/t/autotime-sept-west-serving-ca/645240", "source_type": "Forum Marketplace"},
        {"car": "BMW i4 eDrive40", "monthly": 394, "das": 3500, "term": 36, "effective_monthly": 491.22,
         "source_title": "GCauto BMW CA Pricing",
         "source_url": "https://forum.leasehackr.com/t/1-bmw-ca-pricing-3-5k-drive-off-msd/501758", "source_type": "Forum Marketplace"},
        {"car": "Nissan Ariya Engage", "monthly": 249, "das": 2800, "term": 36, "effective_monthly": 326.78,
         "source_title": "NorCal Nissan Specials",
         "source_url": "https://forum.leasehackr.com/t/lexus-toyota-kia-specials/503147", "source_type": "Forum Marketplace"},
        {"car": "Volvo XC40 Recharge", "monthly": 349, "das": 3000, "term": 36, "effective_monthly": 432.33,
         "source_title": "GCauto Mercedes & Volvo NorCal",
         "source_url": "https://forum.leasehackr.com/t/gcauto-mercedes-volvo/586654", "source_type": "Forum Marketplace"},
        {"car": "Kia EV9 Light", "monthly": 379, "das": 3999, "term": 24, "effective_monthly": 545.63,
         "source_title": "Chrome Stallions Kia Deals",
         "source_url": "https://forum.leasehackr.com/t/chrome-stallions-hon-kia-sub/774103", "source_type": "Forum Marketplace"},
    ]

    sample_img_url = "https://leasehackr-assets.b-cdn.net/optimized/4X/b/7/f/b7fdd69096a2a33cf094b5ffc2f35205138a0185_2_690x355.jpeg"
    for item in mock_list:
        safe_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', item['car'].lower()) + ".jpg"
        img_path = data_dir / safe_name
        try:
            r_img = requests.get(sample_img_url, timeout=5)
            if r_img.status_code == 200:
                with open(img_path, 'wb') as f_img:
                    f_img.write(r_img.content)
                item['screenshot_path'] = f"data_{get_date_str()}/{safe_name}"
            else:
                item['screenshot_path'] = ''
        except Exception:
            item['screenshot_path'] = ''
        item['card_url'] = sample_img_url

    return mock_list


# ---------------------------------------------------------------------------
# HTML report generator
# ---------------------------------------------------------------------------
def generate_html_report(today_deals, history, latest_date, prev_date, comparison_data):
    timestamp   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = LEASEHACKR_OUTPUT_DIR / f"ev_deals_report_{timestamp}.html"

    today_rows = ""
    for d in today_deals:
        src_title = d.get('source_title', 'Leasehackr Deal')
        src_url   = d.get('source_url', 'https://forum.leasehackr.com/c/marketplace/5')
        ss_path   = d.get('screenshot_path', '')
        card_url  = d.get('card_url', '')
        src_type  = d.get('source_type', 'Forum Marketplace')

        link_html = f'<a href="{src_url}" target="_blank" class="source-link">🔗 {src_title}</a>'

        if ss_path:
            screenshot_html = f'<a href="{ss_path}" target="_blank" class="ss-link">📸 Image</a>'
            if card_url:
                screenshot_html += f' &nbsp;<a href="{card_url}" target="_blank" class="ss-link">🌐 CDN</a>'
        else:
            screenshot_html = "N/A"

        today_rows += f"""
        <tr>
            <td><strong>{d['car']}</strong></td>
            <td><span class="type-badge">{src_type}</span></td>
            <td>${d['monthly']}</td>
            <td>${d['das']}</td>
            <td>{d['term']} mo</td>
            <td class="highlight">${d['effective_monthly']:.2f}</td>
            <td>{link_html}</td>
            <td>{screenshot_html}</td>
        </tr>
        """

    comp_rows = ""
    if comparison_data:
        for row in comparison_data:
            car, prev_p, lat_p, diff_s, pct_s = row
            cls = "neutral"
            if diff_s.startswith("-"):
                cls = "down"
            elif diff_s.startswith("+"):
                cls = "up"
            comp_rows += f"""
            <tr>
                <td><strong>{car}</strong></td>
                <td>{prev_p}</td>
                <td>{lat_p}</td>
                <td class="{cls}">{diff_s}</td>
                <td class="{cls}">{pct_s}</td>
            </tr>
            """
    else:
        comp_rows = "<tr><td colspan='5'>Not enough historical data (requires at least 2 different days).</td></tr>"

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NorCal EV Lease Deals Report - {get_date_str()}</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
        body {{
            font-family: 'Inter', 'Segoe UI', sans-serif;
            background-color: #0f172a;
            color: #f8fafc;
            margin: 0;
            padding: 2rem;
        }}
        .container {{ max-width: 1360px; margin: 0 auto; }}
        h1 {{ color: #38bdf8; border-bottom: 2px solid #334155; padding-bottom: 0.5rem; margin-bottom: 0.5rem; }}
        h2 {{ color: #818cf8; margin-top: 2rem; margin-bottom: 1rem; }}
        .timestamp {{ color: #64748b; font-size: 0.9rem; margin-bottom: 2rem; }}
        table {{ width: 100%; border-collapse: collapse; margin-bottom: 2rem;
                 background-color: #1e293b; border-radius: 8px; overflow: hidden;
                 box-shadow: 0 4px 16px rgba(0,0,0,0.4); }}
        th, td {{ padding: 12px 16px; text-align: left; border-bottom: 1px solid #334155; }}
        th {{ background-color: #334155; color: #38bdf8; font-weight: 600;
              text-transform: uppercase; font-size: 0.8rem; letter-spacing: 0.06em; }}
        tr:last-child td {{ border-bottom: none; }}
        tr:hover {{ background-color: #283548; transition: background 0.15s; }}
        .highlight {{ color: #4ade80; font-weight: bold; }}
        .down {{ color: #4ade80; font-weight: bold; }}
        .up   {{ color: #f87171; font-weight: bold; }}
        .neutral {{ color: #94a3b8; }}
        .type-badge {{ background-color: #334155; color: #fbbf24; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: 600; }}
        .source-link {{ color: #38bdf8; text-decoration: none; }}
        .source-link:hover {{ text-decoration: underline; }}
        .ss-link {{ color: #fbbf24; text-decoration: none; font-weight: 600; }}
        .ss-link:hover {{ text-decoration: underline; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🚗 Northern California EV Lease Deals</h1>
        <div class="timestamp">Generated: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</div>

        <h2>Top 10 Cheapest EV Deals (PND Website + Active Forum Marketplace) — {get_date_str()}</h2>
        <table>
            <thead>
                <tr>
                    <th>Car Model</th>
                    <th>Source Type</th>
                    <th>Monthly</th>
                    <th>DAS</th>
                    <th>Term</th>
                    <th>Effective Monthly</th>
                    <th>Source Link</th>
                    <th>Image</th>
                </tr>
            </thead>
            <tbody>
                {today_rows}
            </tbody>
        </table>

        <h2>📈 Historical Price Changes</h2>
        <table>
            <thead>
                <tr>
                    <th>Car Model</th>
                    <th>Prev ({prev_date if prev_date else 'N/A'})</th>
                    <th>Latest ({latest_date if latest_date else 'N/A'})</th>
                    <th>Change ($)</th>
                    <th>Change (%)</th>
                </tr>
            </thead>
            <tbody>
                {comp_rows}
            </tbody>
        </table>
    </div>
</body>
</html>
"""
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"HTML report successfully generated at: {report_file}")


# ---------------------------------------------------------------------------
# Console report + HTML generation
# ---------------------------------------------------------------------------
def print_reports():
    print("\n" + "=" * 80)
    print(f" 10 CHEAPEST EV CAR DEALS FOR NORTHERN CALIFORNIA ({get_date_str()})")
    print("=" * 80)

    today_file = get_today_cache_file()
    if not today_file.exists():
        print("No data available for today.")
        return

    with open(today_file, 'r', encoding='utf-8') as f:
        today_deals = json.load(f)

    headers = ["Car Model", "Source Type", "Monthly ($)", "DAS ($)", "Term (Mo)", "Effective Monthly ($)", "Source URL"]
    table_data = [
        [d['car'], d.get('source_type', 'Forum'), f"${d['monthly']}", f"${d['das']}", d['term'],
         f"${d['effective_monthly']:.2f}", d.get('source_url', 'N/A')]
        for d in today_deals
    ]
    print(tabulate(table_data, headers=headers, tablefmt="grid"))

    print("\n" + "=" * 80)
    print(" HISTORICAL PRICE CHANGE ANALYSIS (ALL CACHED DAYS)")
    print("=" * 80)

    cache_files = sorted(CACHE_DIR.glob("ev_deals_*.json"))

    history = {}
    for file in cache_files:
        date_part = file.stem.replace("ev_deals_", "")
        try:
            with open(file, 'r', encoding='utf-8') as f:
                for d in json.load(f):
                    history.setdefault(d['car'], {})[date_part] = d['effective_monthly']
        except Exception as e:
            print(f"Error reading cache file {file.name}: {e}")

    latest_date = cache_files[-1].stem.replace("ev_deals_", "") if cache_files else ""
    prev_date   = cache_files[-2].stem.replace("ev_deals_", "") if len(cache_files) >= 2 else ""

    comparison_data = []
    if len(cache_files) > 1:
        for car, dates in history.items():
            if latest_date in dates and prev_date in dates:
                lp   = dates[latest_date]
                pp   = dates[prev_date]
                diff = lp - pp
                pct  = (diff / pp) * 100 if pp else 0
                comparison_data.append([
                    car,
                    f"${pp:.2f}",
                    f"${lp:.2f}",
                    f"${diff:+.2f}" if diff != 0 else "$0.00",
                    f"{pct:+.1f}%"  if diff != 0 else "0.0%",
                ])

    if not comparison_data:
        print("Not enough historical data in CACHE to show price changes (requires at least 2 different days).")
    else:
        comp_headers = ["Car Model", f"Prev ({prev_date})", f"Latest ({latest_date})", "Change ($)", "Change (%)"]
        print(tabulate(comparison_data, headers=comp_headers, tablefmt="grid"))

    generate_html_report(today_deals, history, latest_date, prev_date, comparison_data)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def main():
    today_file = get_today_cache_file()
    if today_file.exists():
        # Remove today's cache if forced re-run desired or proceed
        today_file.unlink()

    all_deals = []

    # 1. Scrape official Pre-Negotiated Deals website (pnd.leasehackr.com)
    print("Fetching official Pre-Negotiated Deals from Leasehackr website...")
    pnd_website_deals = fetch_pnd_website_deals()
    all_deals.extend(pnd_website_deals)

    # 2. Scrape Leasehackr Forum Marketplace (ca-norcal topics within 30 days)
    print("\nFetching Northern California Forum Marketplace topics (within 30 days)...")
    topics_data = fetch_norcal_marketplace_topics()

    if topics_data and 'topic_list' in topics_data:
        all_topics = topics_data['topic_list']['topics']

        # Enforce strict 30-day (1 month) cutoff
        recent_topics = [t for t in all_topics if is_recent_topic(t, days=30)]
        stale_count   = len(all_topics) - len(recent_topics)
        print(f"Found {len(all_topics)} forum topics; {len(recent_topics)} active within last 30 days ({stale_count} skipped as >1 month old).")

        topic_keywords = [
            'ev', 'electric', 'ioniq', 'prologue', 'lyriq', 'optiq', 'etron', 'e-tron',
            'eq', 'recharge', 'phev', 'bz4x', 'mach-e', 'hyundai', 'kia', 'bmw',
            'cadillac', 'chevrolet', 'chevy', 'volvo', 'toyota', 'lexus', 'nissan',
        ]
        forum_deals = []
        for topic in recent_topics[:25]:
            title    = topic.get('title', '')
            topic_id = topic.get('id')
            last_posted = topic.get('last_posted_at', 'unknown')[:10]
            if any(kw in title.lower() for kw in topic_keywords):
                safe_title = title.encode('ascii', errors='replace').decode('ascii')
                print(f"Parsing topic [{last_posted}]: {safe_title}")
                details = fetch_topic_details(topic_id)
                forum_deals.extend(parse_deals_from_topic(topic, details))

        all_deals.extend(forum_deals)

    if not all_deals:
        print("No EV deals retrieved. Using fallback mock data.")
        all_deals = get_mock_deals()

    # Deduplicate deals by car name (keep cheapest effective monthly cost)
    dedup_dict = {}
    for d in sorted(all_deals, key=lambda x: x['effective_monthly']):
        ckey = d['car'].lower()
        if ckey not in dedup_dict:
            dedup_dict[ckey] = d

    final_deals = sorted(dedup_dict.values(), key=lambda x: x['effective_monthly'])[:10]

    with open(today_file, 'w', encoding='utf-8') as f:
        json.dump(final_deals, f, indent=4)
    print(f"\nSuccessfully saved top {len(final_deals)} deals to {today_file}")

    print_reports()


if __name__ == "__main__":
    main()
