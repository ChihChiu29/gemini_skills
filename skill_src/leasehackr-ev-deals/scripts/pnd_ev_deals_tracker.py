"""
Leasehackr Pre-Negotiated Deals (PND) EV Tracker
Filters: California -> Northern California -> EV (Cars)
Extracts the top 6 cheapest choices based on standard advertised pricing
(excluding conditional discounts like "MyFirstEV" or brand loyalty rebates).
Maintains daily JSON cache and produces reports for up to the last 90 days.
"""

import os
import sys
import json
import re
import datetime
from pathlib import Path
import requests
from bs4 import BeautifulSoup

# Fix encoding on Windows stdout
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ('utf-8', 'utf8'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CACHE_DIR = PROJECT_ROOT / "CACHE" / "leasehackr_pnd"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_DIR = PROJECT_ROOT / "OUTPUT" / "leasehackr"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

def get_today_str():
    return datetime.date.today().isoformat()

def get_cache_file(date_str):
    return CACHE_DIR / f"pnd_ev_deals_{date_str}.json"

def fetch_top_deals_from_web():
    """
    Fetch official Pre-Negotiated Deals from Leasehackr PND portal,
    filter for Northern California EV deals, exclude conditional discounts
    such as 'MyFirstEV' for the base price, and return top 6 cheapest deals.
    """
    url = "https://pnd.leasehackr.com/r/California"
    payload = {
        'avail_locations': 'Northern California',
        'fuel_type': 'ev'
    }

    try:
        resp = requests.post(url, data=payload, headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            print(f"Warning: Leasehackr PND returned status {resp.status_code}")
            return []
    except Exception as e:
        print(f"Error requesting Leasehackr PND: {e}")
        return []

    soup = BeautifulSoup(resp.text, 'html.parser')
    cards = soup.find_all('div', class_='deal_card')

    all_deals = []
    for c in cards:
        # Check location
        loc = c.find(class_='state_val').get_text(strip=True) if c.find(class_='state_val') else ''
        if loc != 'Northern California':
            continue

        # Car title
        title = ' '.join(c.find(class_='card_title').stripped_strings) if c.find(class_='card_title') else 'Unknown Vehicle'

        # Monthly payment (standard base advertised, excluding conditional rebates)
        monthly_elem = c.find(class_='monthly_val')
        monthly_str = monthly_elem.get_text(strip=True) if monthly_elem else ''

        # Upfront payment (Due at signing)
        das_elem = c.find(class_='das_val')
        if das_elem:
            das_str = das_elem.get_text(strip=True).replace(',', '')
        else:
            card_das = c.find(class_='card_das')
            das_match = re.search(r'\$([0-9,]+)\s+due\s+at\s+signing', card_das.get_text() if card_das else '')
            das_str = das_match.group(1).replace(',', '') if das_match else '0'

        # Lease term (months)
        term_elem = c.find(class_='term_val')
        term_str = term_elem.get_text(strip=True) if term_elem else ''

        # Allowed mileage per year
        mileage_elem = c.find(class_='mileage_val')
        mileage_str = mileage_elem.get_text(strip=True).replace(',', '') if mileage_elem else '0'

        if not monthly_str.isdigit() or not term_str.isdigit():
            continue

        monthly = int(monthly_str)
        das = int(das_str) if das_str.isdigit() else 0
        term = int(term_str)
        mileage = int(mileage_str) if mileage_str.isdigit() else 0

        # Effective monthly cost: monthly payment + upfront spread over lease term
        effective = round(monthly + (das / term if term > 0 else 0), 2)

        # Notes (e.g. conditional offers like First EV rebate or loyalty, broker fee notes)
        notes_parts = []
        cond_elem = c.find(class_='card_con')
        if cond_elem:
            cond_text = cond_elem.get_text(' ', strip=True)
            if cond_text:
                notes_parts.append(cond_text)

        service_fee = c.find(class_='service_fee_val')
        if service_fee:
            fee_text = service_fee.get_text(strip=True)
            if fee_text.isdigit():
                notes_parts.append(f"${fee_text} broker fee included in upfront")

        deal_id = c.get('id', '')
        link = f"https://pnd.leasehackr.com/d/{deal_id}" if deal_id else url

        notes_str = "; ".join(notes_parts) if notes_parts else "Standard pre-negotiated deal"

        all_deals.append({
            'car': title,
            'monthly': monthly,
            'upfront': das,
            'term': term,
            'mileage_per_year': mileage,
            'effective_monthly': effective,
            'notes': notes_str,
            'url': link
        })

    # Sort strictly by effective monthly cost (cheapest first)
    all_deals.sort(key=lambda d: d['effective_monthly'])

    # Pick top 6
    top_6 = all_deals[:6]
    return top_6

def get_or_fetch_today_data():
    today = get_today_str()
    cache_path = get_cache_file(today)

    if cache_path.exists():
        print(f"Using cached PND data for today ({today}): {cache_path.name}")
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                return today, json.load(f)
        except Exception as e:
            print(f"Error reading today's cache, re-fetching: {e}")

    print(f"Fetching fresh PND EV deals for {today} from Leasehackr...")
    deals = fetch_top_deals_from_web()
    if deals:
        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(deals, f, indent=4, ensure_ascii=False)
            print(f"Cached {len(deals)} deals to {cache_path.name}")
        except Exception as e:
            print(f"Could not save cache: {e}")
    else:
        print("Warning: No deals were fetched.")

    return today, deals

def load_historical_data(days_limit=90):
    """
    Loads up to the last `days_limit` days of cached data from CACHE/leasehackr_pnd.
    Returns a dictionary mapping date_str -> list of deal dicts, sorted descending by date.
    """
    history = {}
    cutoff_date = datetime.date.today() - datetime.timedelta(days=days_limit)

    for file in sorted(CACHE_DIR.glob("pnd_ev_deals_*.json"), reverse=True):
        match = re.search(r'pnd_ev_deals_(\d{4}-\d{2}-\d{2})\.json', file.name)
        if match:
            date_str = match.group(1)
            try:
                file_date = datetime.date.fromisoformat(date_str)
                if file_date < cutoff_date:
                    continue
                with open(file, 'r', encoding='utf-8') as f:
                    history[date_str] = json.load(f)
            except Exception as e:
                print(f"Could not load cache {file.name}: {e}")

    return history

def print_deals_table(date_str, deals):
    print(f"\n=========================================================================================")
    print(f"  TOP 6 CHEAPEST EV LEASE DEALS (NorCal) - {date_str}")
    print(f"  Prices exclude 'first EV' and conditional discounts")
    print(f"=========================================================================================")
    header = f"{'#':<3} | {'Vehicle':<35} | {'Monthly':<9} | {'Upfront':<9} | {'Term':<6} | {'Mileage/Yr':<11} | {'Effective/Mo':<12}"
    print(header)
    print("-" * len(header))
    for i, d in enumerate(deals, 1):
        car = d.get('car', 'Unknown')[:35]
        m = f"${d.get('monthly', 0)}"
        u = f"${d.get('upfront', 0)}"
        t = f"{d.get('term', 0)} mo"
        mi = f"{d.get('mileage_per_year', 0):,} mi"
        eff = f"${d.get('effective_monthly', 0):.2f}"
        print(f"{i:<3} | {car:<35} | {m:<9} | {u:<9} | {t:<6} | {mi:<11} | {eff:<12}")
        if d.get('notes'):
            print(f"    Notes: {d.get('notes')}")
    print("=========================================================================================\n")

def generate_markdown_report(history):
    """
    Generate a markdown report in OUTPUT/leasehackr summarizing up to last 90 days.
    """
    md_path = OUTPUT_DIR / "leasehackr_ev_deals_report.md"
    today_str = get_today_str()

    lines = []
    lines.append(f"# Leasehackr NorCal EV Lease Deals Tracker")
    lines.append(f"\n*Last updated: {today_str} | Tracking up to last 90 days of cached data*\n")
    lines.append("> **Note**: Prices show standard advertised pre-negotiated lease terms (excluding 'First EV' conditional discounts). Effective Monthly Cost is calculated as `Monthly + (Upfront / Term)`.\n")

    if not history:
        lines.append("No data currently available in cache.\n")
    else:
        for date_str, deals in history.items():
            lines.append(f"## Top 6 Deals - {date_str}\n")
            lines.append("| Rank | Vehicle | Monthly | Upfront (DAS) | Term | Allowed Mileage | Effective Cost | Notes |")
            lines.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
            for i, d in enumerate(deals, 1):
                car = d.get('car', 'Unknown')
                m = f"${d.get('monthly', 0)}"
                u = f"${d.get('upfront', 0):,}"
                t = f"{d.get('term', 0)} mo"
                mi = f"{d.get('mileage_per_year', 0):,} mi/yr"
                eff = f"${d.get('effective_monthly', 0):.2f}/mo"
                notes = d.get('notes', '').replace('|', '\\|')
                url = d.get('url', '')
                car_link = f"[{car}]({url})" if url else car
                lines.append(f"| {i} | {car_link} | {m} | {u} | {t} | {mi} | **{eff}** | {notes} |")
            lines.append("")

    with open(md_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))
    print(f"Markdown report written to: {md_path}")
    return md_path

def generate_html_report(history):
    """
    Generate an HTML report in OUTPUT/leasehackr.
    """
    html_path = OUTPUT_DIR / "leasehackr_ev_deals_report.html"
    today_str = get_today_str()

    sections_html = []
    for date_str, deals in history.items():
        rows = []
        for i, d in enumerate(deals, 1):
            car = d.get('car', 'Unknown')
            url = d.get('url', '#')
            rows.append(f"""
            <tr>
                <td style="text-align: center; font-weight: bold;">{i}</td>
                <td><a href="{url}" target="_blank" style="color: #38bdf8; text-decoration: none; font-weight: 600;">{car}</a></td>
                <td style="font-weight: 600;">${d.get('monthly', 0)}</td>
                <td>${d.get('upfront', 0):,}</td>
                <td>{d.get('term', 0)} mo</td>
                <td>{d.get('mileage_per_year', 0):,} mi/yr</td>
                <td style="color: #4ade80; font-weight: bold;">${d.get('effective_monthly', 0):.2f}/mo</td>
                <td style="font-size: 0.85rem; color: #94a3b8;">{d.get('notes', '')}</td>
            </tr>
            """)
        table_body = "\n".join(rows)
        sections_html.append(f"""
        <div class="day-section">
            <h2>Deals on {date_str}</h2>
            <table>
                <thead>
                    <tr>
                        <th style="width: 40px;">#</th>
                        <th>Vehicle</th>
                        <th>Monthly</th>
                        <th>Upfront (DAS)</th>
                        <th>Term</th>
                        <th>Allowed Mileage</th>
                        <th>Effective Monthly</th>
                        <th>Notes / Conditional Info</th>
                    </tr>
                </thead>
                <tbody>
                    {table_body}
                </tbody>
            </table>
        </div>
        """)

    full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Leasehackr NorCal EV Lease Deals Tracker</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            background-color: #0f172a;
            color: #f8fafc;
            margin: 0;
            padding: 2rem;
        }}
        .container {{
            max-width: 1300px;
            margin: 0 auto;
        }}
        h1 {{
            color: #38bdf8;
            margin-bottom: 0.25rem;
        }}
        .subtitle {{
            color: #94a3b8;
            font-size: 0.95rem;
            margin-bottom: 2rem;
            border-bottom: 1px solid #334155;
            padding-bottom: 1rem;
        }}
        .day-section {{
            margin-bottom: 3rem;
        }}
        h2 {{
            color: #818cf8;
            margin-bottom: 0.75rem;
            font-size: 1.3rem;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            background-color: #1e293b;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
        }}
        th, td {{
            padding: 12px 16px;
            text-align: left;
            border-bottom: 1px solid #334155;
        }}
        th {{
            background-color: #334155;
            color: #38bdf8;
            font-weight: 600;
            text-transform: uppercase;
            font-size: 0.8rem;
            letter-spacing: 0.05em;
        }}
        tr:hover {{
            background-color: #283548;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Northern California EV Lease Deals Tracker</h1>
        <div class="subtitle">
            Source: Leasehackr Pre-Negotiated Deals (California &gt; Northern California &gt; EV)<br>
            Standard pricing displayed (excluding 'First EV' discounts). Up to last 90 days historical data.
        </div>
        {"".join(sections_html)}
    </div>
</body>
</html>
"""
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(full_html)
    print(f"HTML report written to: {html_path}")
    return html_path

def main():
    print("=" * 60)
    print("Leasehackr NorCal Top 6 EV Lease Deals Tracker")
    print("=" * 60)

    # 1. Fetch or get today's deals from cache
    today_str, today_deals = get_or_fetch_today_data()

    # 2. Print today's deals in terminal
    if today_deals:
        print_deals_table(today_str, today_deals)
    else:
        print("No deals found for today.")

    # 3. Load up to 90 days of cached data
    history = load_historical_data(days_limit=90)
    # Ensure today is present in history if we got deals
    if today_deals and today_str not in history:
        history[today_str] = today_deals

    # 4. Generate Markdown and HTML tables in OUTPUT/leasehackr
    generate_markdown_report(history)
    generate_html_report(history)
    print("Done!")

if __name__ == '__main__':
    main()
